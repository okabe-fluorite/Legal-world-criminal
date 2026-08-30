import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright-core";

const baseUrl = process.env.TEACHER_BASE_URL || "http://127.0.0.1:5173";
const teacherEmail = process.env.TEACHER_SMOKE_EMAIL || "teacher-smoke@example.com";
const studentEmail = process.env.TEACHER_STUDENT_EMAIL || `teacher-student-${Date.now()}@example.com`;
const smokePassword = process.env.TEACHER_SMOKE_PASSWORD || "Teacher-Smoke-2026!";
const configuredClassName = process.env.TEACHER_CLASS_NAME || "";
const resultJsonPath = process.env.TEACHER_RESULT_JSON
  ? path.resolve(process.env.TEACHER_RESULT_JSON)
  : "";
const screenshotPath = path.resolve(
  process.env.TEACHER_SCREENSHOT || "../.codex-artifacts/teacher-dashboard.png",
);
const analyticsScreenshotPath = path.resolve(
  process.env.TEACHER_ANALYTICS_SCREENSHOT || "../.codex-artifacts/teacher-analytics.png",
);
const subjectiveScreenshotPath = path.resolve(
  process.env.TEACHER_SUBJECTIVE_SCREENSHOT || "../.codex-artifacts/teacher-subjective-review.png",
);
const subjectiveAfterScreenshotPath = path.resolve(
  process.env.TEACHER_SUBJECTIVE_AFTER_SCREENSHOT || "../.codex-artifacts/teacher-subjective-after.png",
);
const subjectiveDialogScreenshotPath = path.resolve(
  process.env.TEACHER_SUBJECTIVE_DIALOG_SCREENSHOT || "../.codex-artifacts/teacher-subjective-dialog.png",
);
const studentSubjectiveScreenshotPath = path.resolve(
  process.env.STUDENT_SUBJECTIVE_SCREENSHOT || "../.codex-artifacts/student-subjective-feedback.png",
);
const studentTeacherFeedbackScreenshotPath = path.resolve(
  process.env.STUDENT_TEACHER_FEEDBACK_SCREENSHOT || "../.codex-artifacts/student-teacher-feedback.png",
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

for (const target of [
  screenshotPath,
  analyticsScreenshotPath,
  subjectiveScreenshotPath,
  subjectiveAfterScreenshotPath,
  subjectiveDialogScreenshotPath,
  studentSubjectiveScreenshotPath,
  studentTeacherFeedbackScreenshotPath,
]) {
  fs.mkdirSync(path.dirname(target), { recursive: true });
}
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
  const registerResponsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/api/auth/register") && response.request().method() === "POST",
    { timeout: 120000 },
  );
  const sandboxResponsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/api/sandbox/ensure") && response.request().method() === "POST",
    { timeout: 120000 },
  );
  await page.getByPlaceholder("you@court.edu").fill(email);
  await page.getByPlaceholder("至少 6 位").fill(smokePassword);
  await page.getByRole("button", { name: "注册并进入" }).click();
  const [registerResponse, sandboxResponse] = await Promise.all([
    registerResponsePromise,
    sandboxResponsePromise,
  ]);
  if (registerResponse.status() !== 200 || sandboxResponse.status() !== 200) {
    throw new Error(
      `Registration bootstrap failed: auth=${registerResponse.status()} sandbox=${sandboxResponse.status()}`,
    );
  }
  await page.getByRole("button", { name: "自主学习" }).waitFor({ state: "visible" });
}

async function login(email) {
  const toggle = page.getByRole("button", { name: "已有账号? 登录" });
  if (await toggle.isVisible().catch(() => false)) await toggle.click();
  const loginResponsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/api/auth/login") && response.request().method() === "POST",
    { timeout: 120000 },
  );
  const sandboxResponsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/api/sandbox/ensure") && response.request().method() === "POST",
    { timeout: 120000 },
  );
  await page.getByPlaceholder("you@court.edu").fill(email);
  await page.getByPlaceholder("至少 6 位").fill(smokePassword);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  const [loginResponse, sandboxResponse] = await Promise.all([
    loginResponsePromise,
    sandboxResponsePromise,
  ]);
  if (loginResponse.status() !== 200 || sandboxResponse.status() !== 200) {
    throw new Error(
      `Login bootstrap failed: auth=${loginResponse.status()} sandbox=${sandboxResponse.status()}`,
    );
  }
  await page.getByRole("button", { name: "自主学习" }).waitFor({ state: "visible" });
}

async function waitForMetricPrefix(expected, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  let values = [];
  while (Date.now() < deadline) {
    values = await page.locator(".metric-strip b").allTextContents();
    if (values.slice(0, expected.length).join(",") === expected.join(",")) return values;
    await page.waitForTimeout(200);
  }
  throw new Error(`Unexpected teacher metrics after ${timeoutMs}ms: ${values.join(",")}`);
}

try {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const subjectiveResponse =
    "《刑法》第三条要求只有法律明文规定为犯罪的行为才能定罪处罚。成立例是行为发生时刑法已明确规定构成犯罪，且行为事实逐项满足构成要件；不成立例是仅有社会危害性评价，却找不到明确罪名和构成条件。判断时应先确认行为时有效规范，再把主体、行为、结果和主观方面分别对应，不能用价值判断替代明文规定。";
  await register(studentEmail);
  const studentUserId = await page.evaluate(() => {
    const token = localStorage.getItem("lw.token");
    if (!token) return "";
    const payload = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return String(JSON.parse(atob(payload)).sub || "");
  });
  // The governed case list is populated only after sandbox initialization.
  // Waiting here prevents the learning catalog request from racing that first-start write.
  await page.locator(".case__version").first().waitFor({ state: "visible", timeout: 60000 });
  await page.getByRole("button", { name: "自主学习" }).click();
  await page.getByRole("dialog", { name: "刑法自主学习卷宗" }).waitFor();
  await page.getByText("知识卷宗", { exact: true }).waitFor();
  await page.locator(".option-row").first().waitFor({ state: "visible", timeout: 60000 });
  await page.locator(".option-row").first().click();
  await page.getByRole("button", { name: "提交取证" }).click();
  await page.locator(".feedback-sheet").waitFor();
  await page.getByRole("button", { name: "填写" }).click();
  await page.getByPlaceholder("具体写下你卡住的条件、事实或证据……").fill(
    "teacher-smoke-private-confusion-note",
  );
  await page.getByRole("button", { name: "归入证据账本" }).click();
  await page.getByText("困惑已进入证据账本，后续任务会优先回应。").waitFor();

  await page.getByRole("button", { name: /进入主观论证与角色互换/ }).click();
  await page.getByRole("dialog", { name: "刑法主观论证训练" }).waitFor();
  await page.getByPlaceholder(/先写争点/).fill(subjectiveResponse);
  await page.getByRole("button", { name: /提交教师复核/ }).click();
  await page.locator(".formative-review").waitFor({ timeout: 210000 });
  const studentSubjectiveStatus = await page.locator(".formative-review").innerText();
  const subjectiveTeacherGateVisible =
    studentSubjectiveStatus.includes("needs_teacher_review")
    && studentSubjectiveStatus.includes("教师复核");
  if (!subjectiveTeacherGateVisible) {
    throw new Error(`Subjective attempt did not enter teacher gate: ${studentSubjectiveStatus}`);
  }
  await page.locator(".formative-review").scrollIntoViewIfNeeded();
  await page.screenshot({ path: studentSubjectiveScreenshotPath, fullPage: false });
  await page.getByRole("button", { name: "关闭主观论证训练" }).click();
  await page.getByRole("button", { name: "关闭自主学习" }).click();
  await page.getByRole("button", { name: "退出" }).click();
  await page.getByRole("button", { name: "注册并进入" }).waitFor();

  await register(teacherEmail);
  await page.getByRole("button", { name: "教师驾驶舱" }).waitFor({ state: "visible" });
  await page.getByRole("button", { name: "教师驾驶舱" }).click();
  await page.getByRole("dialog", { name: "教师教学驾驶舱" }).waitFor();

  await page.getByRole("button", { name: "+ 新建" }).click();
  const uniqueClass = configuredClassName || `刑法试点班-${Date.now().toString().slice(-6)}`;
  await page.getByLabel("班级名称").fill(uniqueClass);
  await page.getByLabel("学期").fill("2026秋");
  await page.getByRole("button", { name: "建立班级" }).click();
  await page.getByText("班级已建立。").waitFor();
  await page.locator(".class-list button.active").filter({ hasText: uniqueClass }).waitFor();
  await page.getByLabel("学生邮箱").waitFor({ state: "visible" });
  await page.getByLabel("学生邮箱").fill(studentEmail);
  await page.getByRole("button", { name: "加入班级" }).click();
  await page.getByText(/学生已加入班级/).waitFor();

  const metricValues = await waitForMetricPrefix(["1", "1", "2", "1", "1"]);
  const bodyText = await page.locator(".teacher-board").innerText();
  const privacyLeaks = [studentEmail, studentUserId, "teacher-smoke-private-confusion-note"].filter((value) =>
    value &&
    bodyText.includes(value),
  );
  await page.screenshot({ path: analyticsScreenshotPath, fullPage: false });

  await page.getByRole("button", { name: /内容复核/ }).click();
  await page.locator(".review-table article").first().waitFor();
  const reviewCounts = await page.locator(".review-counts dd").allTextContents();
  if (reviewCounts.slice(0, 4).join(",") !== "3,10,30,0") {
    throw new Error(`Unexpected governed review counts: ${reviewCounts.join(",")}`);
  }
  await page.locator(".review-table article").first().getByRole("button", { name: "复核" }).click();
  await page.getByRole("dialog", { name: "提交教师内容复核" }).waitFor();
  await page.getByText("指导要点（教师参考）").waitFor();
  await page.getByPlaceholder("写明法源、理论口径、题干或教学风险……").fill(
    "法源与课程基础口径一致，同意本学期低风险试用。",
  );
  await page.getByRole("button", { name: "写入审核台账" }).click();
  await page.getByText("审核意见已写入不可变台账。").waitFor();
  await page.screenshot({ path: screenshotPath, fullPage: false });

  await page.getByRole("button", { name: /主观复核/ }).click();
  await page.locator(".subjective-review-row").waitFor({ timeout: 30000 });
  const subjectiveQueueBefore = await page.locator(".subjective-review-row").count();
  if (subjectiveQueueBefore !== 1) {
    throw new Error(`Expected one class-scoped subjective attempt, received ${subjectiveQueueBefore}`);
  }
  const subjectiveBoardText = await page.locator(".teacher-board").innerText();
  const subjectivePrivacyLeaks = [studentEmail, studentUserId].filter(
    (value) => value && subjectiveBoardText.includes(value),
  );
  await page.locator(".subjective-review-row footer button").scrollIntoViewIfNeeded();
  await page.screenshot({ path: subjectiveScreenshotPath, fullPage: false });
  await page.locator(".subjective-review-row").getByRole("button", { name: /打开匿名稿件复核/ }).click();
  const subjectiveDialog = page.getByRole("dialog", { name: "教师主观稿件复核" });
  await subjectiveDialog.waitFor();
  await subjectiveDialog.locator("select").first().selectOption("request_revision");
  await subjectiveDialog.getByPlaceholder(/指出规范/).fill(
    "请保留罪刑法定的对照事实，并在下一稿补充行为时法与裁判时法发生变化时的比较步骤。",
  );
  await subjectiveDialog.getByPlaceholder(/构成要件遗漏/).fill("时间效力比较不足；边界论证待展开");
  await page.screenshot({ path: subjectiveDialogScreenshotPath, fullPage: false });
  await subjectiveDialog.getByRole("button", { name: "写入教师决定" }).click();
  await page.getByText(/已退回学生修订/).waitFor({ timeout: 30000 });
  await page.getByText("当前没有待复核稿件").waitFor();
  const subjectiveQueueAfterRevisionRequest = await page.locator(".subjective-review-row").count();
  await page.screenshot({ path: subjectiveAfterScreenshotPath, fullPage: false });

  await page.getByRole("button", { name: "关闭教师驾驶舱" }).click();
  await page.getByRole("button", { name: "退出" }).click();
  await page.getByRole("button", { name: /登录|注册并进入/ }).first().waitFor();
  await login(studentEmail);
  await page.getByRole("button", { name: "自主学习" }).click();
  await page.getByRole("dialog", { name: "刑法自主学习卷宗" }).waitFor();
  await page.getByRole("button", { name: /进入主观论证与角色互换/ }).click();
  await page.getByRole("dialog", { name: "刑法主观论证训练" }).waitFor();
  const revisionReturn = page.locator(".teacher-return--request_revision");
  await revisionReturn.waitFor({ timeout: 30000 });
  const revisionFeedbackText = await revisionReturn.innerText();
  const revisionFeedbackVisible =
    revisionFeedbackText.includes("退回修订")
    && revisionFeedbackText.includes("行为时法与裁判时法");
  await revisionReturn.getByRole("button", { name: /带入原文开始修订/ }).click();
  const revisionTextarea = page.getByPlaceholder(/先写争点/);
  const revisionPrefilled = (await revisionTextarea.inputValue()).includes("《刑法》第三条");
  await revisionTextarea.fill(
    `${subjectiveResponse} 进一步依据《刑法》第十二条比较行为时法与裁判时法：原则上适用行为时法；新法不认为是犯罪或者处刑较轻时，依从旧兼从轻规则适用更有利的规范。`,
  );
  await page.getByRole("button", { name: /提交教师复核/ }).click();
  await page.locator(".formative-review").waitFor({ timeout: 210000 });
  const revisedStudentGateVisible = (await page.locator(".formative-review").innerText()).includes(
    "needs_teacher_review",
  );
  await page.getByRole("button", { name: "关闭主观论证训练" }).click();
  await page.getByRole("button", { name: "关闭自主学习" }).click();
  await page.getByRole("button", { name: "退出" }).click();
  await login(teacherEmail);
  await page.getByRole("button", { name: "教师驾驶舱" }).click();
  await page.getByRole("dialog", { name: "教师教学驾驶舱" }).waitFor();
  await page.getByRole("button", { name: /主观复核/ }).click();
  await page.locator(".subjective-review-row").waitFor({ timeout: 30000 });
  const subjectiveQueueBeforeApproval = await page.locator(".subjective-review-row").count();
  await page.locator(".subjective-review-row").getByRole("button", { name: /打开匿名稿件复核/ }).click();
  await subjectiveDialog.waitFor();
  await subjectiveDialog.locator('input[type="number"]').fill("0.82");
  await subjectiveDialog.locator("select").nth(1).selectOption("partial");
  await subjectiveDialog.getByPlaceholder(/指出规范/).fill(
    "修订稿已补充新旧法比较步骤，批准进入形成性证据画像；仍需继续练习边界事实。",
  );
  await subjectiveDialog.getByPlaceholder(/构成要件遗漏/).fill("边界事实仍需展开");
  await subjectiveDialog.getByRole("button", { name: "批准并写入形成性证据" }).click();
  await page.getByText(/教师复核已入账，已生成形成性证据/).waitFor({ timeout: 30000 });
  await page.getByText("当前没有待复核稿件").waitFor();
  const subjectiveQueueAfter = await page.locator(".subjective-review-row").count();

  await page.getByRole("button", { name: "班级学情" }).click();
  await page.waitForFunction(() => document.querySelectorAll(".metric-strip b")[2]?.textContent === "3");
  const metricsAfterApproval = await page.locator(".metric-strip b").allTextContents();

  await page.getByRole("button", { name: "关闭教师驾驶舱" }).click();
  await page.getByRole("button", { name: "退出" }).click();
  await login(studentEmail);
  await page.getByRole("button", { name: "自主学习" }).click();
  await page.getByRole("dialog", { name: "刑法自主学习卷宗" }).waitFor();
  await page.getByRole("button", { name: /进入主观论证与角色互换/ }).click();
  await page.getByRole("dialog", { name: "刑法主观论证训练" }).waitFor();
  const approvalReturn = page.locator(".teacher-return--approve");
  await approvalReturn.waitFor({ timeout: 30000 });
  const approvalFeedbackText = await approvalReturn.innerText();
  const studentApprovalVisible =
    approvalFeedbackText.includes("批准为形成性证据")
    && approvalFeedbackText.includes("evt_subjective_");
  await approvalReturn.scrollIntoViewIfNeeded();
  await page.screenshot({ path: studentTeacherFeedbackScreenshotPath, fullPage: false });

  const result = {
    teacher_role_entry_visible: true,
    viewport: `${viewport.width}x${viewport.height}`,
    class_name: uniqueClass,
    metrics: metricValues,
    metrics_after_subjective_approval: metricsAfterApproval,
    review_counts: reviewCounts,
    privacy_leaks: privacyLeaks,
    subjective_privacy_leaks: subjectivePrivacyLeaks,
    subjective_queue_before: subjectiveQueueBefore,
    subjective_queue_after_revision_request: subjectiveQueueAfterRevisionRequest,
    revision_feedback_visible: revisionFeedbackVisible,
    revision_prefilled_original: revisionPrefilled,
    revised_student_gate_visible: revisedStudentGateVisible,
    subjective_queue_before_approval: subjectiveQueueBeforeApproval,
    subjective_queue_after: subjectiveQueueAfter,
    subjective_student_gate_visible: subjectiveTeacherGateVisible,
    student_approval_visible: studentApprovalVisible,
    review_event_recorded: true,
    subjective_review_event_recorded: metricsAfterApproval[2] === "3",
    console_errors: consoleErrors,
    page_errors: pageErrors,
    http_errors: httpErrors,
    request_failures: requestFailures,
    screenshot: screenshotPath,
    analytics_screenshot: analyticsScreenshotPath,
    student_subjective_screenshot: studentSubjectiveScreenshotPath,
    subjective_queue_screenshot: subjectiveScreenshotPath,
    subjective_dialog_screenshot: subjectiveDialogScreenshotPath,
    subjective_after_screenshot: subjectiveAfterScreenshotPath,
    student_teacher_feedback_screenshot: studentTeacherFeedbackScreenshotPath,
  };
  if (resultJsonPath) {
    fs.mkdirSync(path.dirname(resultJsonPath), { recursive: true });
    fs.writeFileSync(resultJsonPath, JSON.stringify(result, null, 2), "utf8");
  }
  console.log(JSON.stringify(result));
  if (
    privacyLeaks.length ||
    subjectivePrivacyLeaks.length ||
    subjectiveQueueAfterRevisionRequest !== 0 ||
    !revisionFeedbackVisible ||
    !revisionPrefilled ||
    !revisedStudentGateVisible ||
    subjectiveQueueBeforeApproval !== 1 ||
    subjectiveQueueAfter !== 0 ||
    !studentApprovalVisible ||
    metricsAfterApproval[2] !== "3" ||
    consoleErrors.length ||
    pageErrors.length ||
    httpErrors.length ||
    requestFailures.length
  ) {
    process.exitCode = 1;
  }
} catch (error) {
  console.error(JSON.stringify({
    smoke_error: error instanceof Error ? error.message : String(error),
    url: page.url(),
    console_errors: consoleErrors,
    page_errors: pageErrors,
    http_errors: httpErrors,
    request_failures: requestFailures,
  }));
  throw error;
} finally {
  await browser.close();
}
