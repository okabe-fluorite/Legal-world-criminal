import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright-core";

const baseUrl = process.env.TEACHER_BASE_URL || "http://127.0.0.1:5173";
const teacherEmail = process.env.TEACHER_SMOKE_EMAIL || "teacher-smoke@example.com";
const screenshotPath = path.resolve(
  process.env.TEACHER_SCREENSHOT || "../.codex-artifacts/teacher-dashboard.png",
);
const analyticsScreenshotPath = path.resolve(
  process.env.TEACHER_ANALYTICS_SCREENSHOT || "../.codex-artifacts/teacher-analytics.png",
);
const viewport = {
  width: Number(process.env.TEACHER_VIEWPORT_WIDTH || 1500),
  height: Number(process.env.TEACHER_VIEWPORT_HEIGHT || 980),
};
const candidates = [
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean);
const executablePath = candidates.find((candidate) => fs.existsSync(candidate));
if (!executablePath) throw new Error("No installed Chromium browser found");

fs.mkdirSync(path.dirname(screenshotPath), { recursive: true });
const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport });
const consoleErrors = [];
const pageErrors = [];
const httpErrors = [];
const requestFailures = [];
page.on("console", (message) => {
  if (message.type() === "error") {
    consoleErrors.push({ text: message.text(), location: message.location() });
  }
});
page.on("pageerror", (error) => pageErrors.push(error.message));
page.on("response", (response) => {
  if (response.status() >= 400) httpErrors.push({ status: response.status(), url: response.url() });
});
page.on("requestfailed", (request) => {
  requestFailures.push({ url: request.url(), error: request.failure()?.errorText || "unknown" });
});

async function register(email) {
  await page.getByPlaceholder("you@court.edu").fill(email);
  await page.getByPlaceholder("至少 6 位").fill("Teacher-Smoke-2026!");
  await page.getByRole("button", { name: "注册并进入" }).click();
  await page.getByRole("button", { name: "自主学习" }).waitFor({ state: "visible" });
}

try {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const studentEmail = `teacher-student-${Date.now()}@example.com`;
  await register(studentEmail);
  await page.getByRole("button", { name: "自主学习" }).click();
  await page.getByRole("dialog", { name: "刑法自主学习卷宗" }).waitFor();
  await page.locator(".option-row").first().click();
  await page.getByRole("button", { name: "提交取证" }).click();
  await page.locator(".feedback-sheet").waitFor();
  await page.getByRole("button", { name: "填写" }).click();
  await page.getByPlaceholder("具体写下你卡住的条件、事实或证据……").fill(
    "teacher-smoke-private-confusion-note",
  );
  await page.getByRole("button", { name: "归入证据账本" }).click();
  await page.getByText("困惑已进入证据账本，后续任务会优先回应。").waitFor();
  await page.getByRole("button", { name: "关闭自主学习" }).click();
  await page.getByRole("button", { name: "退出" }).click();
  await page.getByRole("button", { name: "注册并进入" }).waitFor();

  await register(teacherEmail);
  await page.getByRole("button", { name: "教师驾驶舱" }).waitFor({ state: "visible" });
  await page.getByRole("button", { name: "教师驾驶舱" }).click();
  await page.getByRole("dialog", { name: "教师教学驾驶舱" }).waitFor();

  await page.getByRole("button", { name: "+ 新建" }).click();
  const uniqueClass = `刑法试点班-${Date.now().toString().slice(-6)}`;
  await page.getByLabel("班级名称").fill(uniqueClass);
  await page.getByLabel("学期").fill("2026秋");
  await page.getByRole("button", { name: "建立班级" }).click();
  await page.getByText("班级已建立。").waitFor();
  await page.getByLabel("学生邮箱").fill(studentEmail);
  await page.getByRole("button", { name: "加入班级" }).click();
  await page.getByText(/学生已加入班级/).waitFor();

  const metricValues = await page.locator(".metric-strip b").allTextContents();
  if (metricValues.slice(0, 5).join(",") !== "1,1,2,1,1") {
    throw new Error(`Unexpected teacher metrics: ${metricValues.join(",")}`);
  }
  const bodyText = await page.locator(".teacher-board").innerText();
  const privacyLeaks = [studentEmail, "teacher-smoke-private-confusion-note"].filter((value) =>
    bodyText.includes(value),
  );
  await page.screenshot({ path: analyticsScreenshotPath, fullPage: false });

  await page.getByRole("button", { name: /内容复核/ }).click();
  await page.locator(".review-table article").first().waitFor();
  await page.locator(".review-table article").first().getByRole("button", { name: "复核" }).click();
  await page.getByRole("dialog", { name: "提交教师内容复核" }).waitFor();
  await page.getByPlaceholder("写明法源、理论口径、题干或教学风险……").fill(
    "法源与课程基础口径一致，同意本学期低风险试用。",
  );
  await page.getByRole("button", { name: "写入审核台账" }).click();
  await page.getByText("审核意见已写入不可变台账。").waitFor();
  await page.screenshot({ path: screenshotPath, fullPage: false });

  const result = {
    teacher_role_entry_visible: true,
    viewport: `${viewport.width}x${viewport.height}`,
    class_name: uniqueClass,
    metrics: metricValues,
    privacy_leaks: privacyLeaks,
    review_event_recorded: true,
    console_errors: consoleErrors,
    page_errors: pageErrors,
    http_errors: httpErrors,
    request_failures: requestFailures,
    screenshot: screenshotPath,
    analytics_screenshot: analyticsScreenshotPath,
  };
  console.log(JSON.stringify(result));
  if (
    privacyLeaks.length ||
    consoleErrors.length ||
    pageErrors.length ||
    httpErrors.length ||
    requestFailures.length
  ) {
    process.exitCode = 1;
  }
} finally {
  await browser.close();
}
