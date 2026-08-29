/** Capture secret-free browser video segments from a frozen demo database.
 *
 * Login happens in non-recorded contexts. Recorded actions are read-only except
 * the local citation-audit request, which does not update the learner profile.
 * The script never starts or restarts a case and deletes temporary auth state.
 */

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "..", "..");
const require = createRequire(import.meta.url);
const { chromium } = require(path.join(repo, "frontend", "node_modules", "playwright-core"));

const baseUrl = process.env.DEMO_CAPTURE_BASE_URL || "http://127.0.0.1:5173";
const studentEmail = process.env.DEMO_STUDENT_EMAIL || "";
const teacherEmail = process.env.DEMO_TEACHER_EMAIL || "";
const password = process.env.DEMO_ACCOUNT_PASSWORD || "";
const outputDir = path.resolve(
  process.env.DEMO_CAPTURE_DIR
    || path.join(repo, "competition_submission", "offline_backup", "video-capture"),
);
const viewport = { width: 1600, height: 900 };
const ffmpeg = process.env.DEMO_FFMPEG || "ffmpeg";

if (!studentEmail.endsWith("@example.com") || !teacherEmail.endsWith("@example.com") || !password) {
  throw new Error("synthetic student/teacher emails and DEMO_ACCOUNT_PASSWORD are required");
}

const candidates = [
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
].filter(Boolean);
const executablePath = candidates.find((candidate) => fs.existsSync(candidate));
if (!executablePath) throw new Error("No installed Chromium browser found");

if (fs.existsSync(outputDir) && fs.readdirSync(outputDir).length) {
  throw new Error(`capture output must be empty: ${outputDir}`);
}
fs.mkdirSync(outputDir, { recursive: true });

const browser = await chromium.launch({ executablePath, headless: true });

async function loginInsideContext(context, email) {
  const recordStartedAt = Date.now();
  const page = await context.newPage();
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const toggle = page.getByRole("button", { name: "已有账号? 登录" });
  if (await toggle.isVisible().catch(() => false)) await toggle.click();
  await page.getByPlaceholder("you@court.edu").fill(email);
  await page.getByPlaceholder("至少 6 位").fill(password);
  const loginResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/auth/login") && response.request().method() === "POST",
    { timeout: 60000 },
  );
  await page.getByRole("button", { name: "登录", exact: true }).click();
  if ((await loginResponse).status() !== 200) throw new Error("demo login failed");
  await page.getByRole("button", { name: "自主学习" }).waitFor({ timeout: 60000 });
  await page.waitForTimeout(500);
  return { page, trimSeconds: (Date.now() - recordStartedAt) / 1000 + 0.35 };
}

async function addLabel(page, primary, secondary) {
  await page.evaluate(({ primary, secondary }) => {
    document.getElementById("competition-record-label")?.remove();
    const label = document.createElement("div");
    label.id = "competition-record-label";
    label.setAttribute("aria-hidden", "true");
    label.style.cssText = [
      "position:fixed", "top:14px", "right:18px", "z-index:2147483647",
      "background:#002FA7", "color:#fff", "padding:10px 14px", "max-width:440px",
      "font:600 14px/1.35 'Microsoft YaHei UI',sans-serif", "letter-spacing:.03em",
      "border:1px solid rgba(255,255,255,.55)", "box-shadow:none", "border-radius:0",
      "pointer-events:none",
    ].join(";");
    label.innerHTML = `<div>${primary}</div><div style="font-weight:400;opacity:.82;margin-top:2px">${secondary}</div>`;
    document.body.appendChild(label);
  }, { primary, secondary });
}

const wait = (page, ms) => page.waitForTimeout(ms);
const results = [];

async function record(name, email, label, action) {
  const context = await browser.newContext({
    viewport,
    recordVideo: { dir: outputDir, size: viewport },
  });
  const { page, trimSeconds } = await loginInsideContext(context, email);
  const errors = { console: [], page: [], http: [], request: [] };
  page.on("console", (message) => { if (message.type() === "error") errors.console.push(message.text()); });
  page.on("pageerror", (error) => errors.page.push(error.message));
  page.on("response", (response) => { if (response.status() >= 400) errors.http.push(`${response.status()} ${response.url()}`); });
  page.on("requestfailed", (request) => errors.request.push(`${request.url()} ${request.failure()?.errorText || "failed"}`));

  await addLabel(page, label, "冻结演示库 · 仅证明软件行为");
  await wait(page, 1200);
  await action(page);
  await wait(page, 1200);
  const video = page.video();
  await context.close();
  const raw = await video.path();
  const target = path.join(outputDir, `${name}.webm`);
  const encoded = spawnSync(
    ffmpeg,
    [
      "-loglevel", "error", "-y", "-ss", trimSeconds.toFixed(3), "-i", raw,
      "-an", "-c:v", "libvpx-vp9", "-crf", "28", "-b:v", "0", target,
    ],
    { encoding: "utf8" },
  );
  fs.rmSync(raw, { force: true });
  if (encoded.status !== 0) {
    throw new Error(`ffmpeg trim failed for ${name}: ${encoded.stderr || encoded.stdout}`);
  }
  results.push({ name, file: path.basename(target), bytes: fs.statSync(target).size, errors });
}

try {
  await record("01-diagnosis-orcdf-path-model", studentEmail, "实时操作", async (page) => {
    await page.getByRole("button", { name: "认知诊断" }).click();
    const dialog = page.getByRole("dialog", { name: "认知诊断与个性化路径驾驶舱" });
    await dialog.waitFor();
    await page.getByText("Evidence-KT / V0 保守画像", { exact: true }).waitFor();
    await wait(page, 3200);
    await page.getByRole("button", { name: "ORCDF SHADOW" }).click();
    await page.getByText("ORCDF真实训练实验，不进入当前刑法学生画像", { exact: true }).waitFor();
    await wait(page, 4200);
    await page.getByRole("button", { name: "个性化路径" }).click();
    await page.getByText("从证据薄弱点到下一条LearningEvent", { exact: true }).waitFor();
    await wait(page, 3800);
    await page.getByRole("button", { name: "模型路由" }).click();
    await page.getByText("基础模型 / Prompt / RAG / RAG+微调", { exact: true }).waitFor();
    await wait(page, 3600);
  });

  await record("02-trusted-rag", studentEmail, "实时操作", async (page) => {
    await page.getByRole("button", { name: "可信RAG" }).click();
    await page.getByRole("dialog", { name: "可信RAG与三个典型问题验证" }).waitFor();
    await page.locator(".rag-score").getByText("3/3", { exact: true }).waitFor({ timeout: 30000 });
    await wait(page, 2600);
    const questions = page.locator(".question-list button");
    for (let index = 0; index < Math.min(3, await questions.count()); index += 1) {
      await questions.nth(index).click();
      await wait(page, 2400);
    }
    await page.getByRole("button", { name: /运行错误引用门禁/ }).click();
    await page.getByText("2/2 已拒绝", { exact: true }).waitFor();
    await wait(page, 3200);
  });

  await record("03-student-teacher-feedback", studentEmail, "预先验收状态", async (page) => {
    await page.getByRole("button", { name: "自主学习" }).click();
    await page.getByRole("dialog", { name: "刑法自主学习卷宗" }).waitFor();
    await page.getByRole("button", { name: /进入主观论证与角色互换/ }).click();
    await page.getByRole("dialog", { name: "刑法主观论证训练" }).waitFor();
    await page.getByRole("button", { name: /退回修订 · 课前/ }).click();
    const revision = page.locator(".teacher-return--request_revision");
    const approval = page.locator(".teacher-return--approve");
    await revision.waitFor({ timeout: 30000 });
    await revision.scrollIntoViewIfNeeded();
    await wait(page, 3000);
    await page.getByRole("button", { name: /教师批准 · 课前/ }).click();
    await approval.waitFor({ timeout: 30000 });
    await approval.scrollIntoViewIfNeeded();
    await wait(page, 3600);
  });

  await record("04-teacher-dashboard", teacherEmail, "预先验收状态", async (page) => {
    await page.getByRole("button", { name: "教师驾驶舱" }).click();
    await page.getByRole("dialog", { name: "教师教学驾驶舱" }).waitFor();
    await wait(page, 3200);
    await page.getByRole("button", { name: /主观复核/ }).click();
    await page.getByText("当前没有待复核稿件").waitFor();
    await wait(page, 3000);
    await page.getByRole("button", { name: "班级学情" }).click();
    await wait(page, 2800);
  });

  await record("05-case3-card-and-evidence", studentEmail, "真实E2E审计快照 · 固定脚本回答 · 非用户数据", async (page) => {
    const card = page.locator(".case--competition");
    await card.waitFor({ timeout: 60000 });
    await card.scrollIntoViewIfNeeded();
    await wait(page, 3800);
    await page.getByRole("button", { name: "认知诊断" }).click();
    await page.getByRole("dialog", { name: "认知诊断与个性化路径驾驶舱" }).waitFor();
    await page.getByText("Evidence-KT / V0 保守画像", { exact: true }).waitFor();
    await wait(page, 4200);
  });
} finally {
  await browser.close();
}

const manifest = {
  schema: "competition-demo-video-segments-v1",
  viewport: `${viewport.width}x${viewport.height}`,
  segments: results,
  evidence_boundary: (
    "silent browser interaction material from a synthetic frozen demo database; " +
    "not a finished narrated video and not evidence of target-user approval or learning gain"
  ),
};
fs.writeFileSync(path.join(outputDir, "segments-manifest.json"), JSON.stringify(manifest, null, 2), "utf8");
console.log(JSON.stringify(manifest, null, 2));

if (results.some((row) => Object.values(row.errors).some((items) => items.length))) {
  process.exitCode = 2;
}
