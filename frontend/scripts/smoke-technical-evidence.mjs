import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright-core";

const baseUrl = process.env.TECH_EVIDENCE_BASE_URL || "http://127.0.0.1:5173";
const artifactDir = path.resolve(
  process.env.TECH_EVIDENCE_ARTIFACT_DIR || "../output/playwright/technical-evidence",
);
const repoRoot = path.resolve("..");
const publicArtifactDir = path.relative(repoRoot, artifactDir).split(path.sep).join("/");
if (!publicArtifactDir || publicArtifactDir.startsWith("../")) {
  throw new Error("Technical evidence artifacts must stay inside the repository");
}
const viewport = {
  width: Number(process.env.TECH_EVIDENCE_VIEWPORT_WIDTH || 1500),
  height: Number(process.env.TECH_EVIDENCE_VIEWPORT_HEIGHT || 980),
};
const candidates = [
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean);
const executablePath = candidates.find((candidate) => fs.existsSync(candidate));
if (!executablePath) throw new Error("No installed Chromium browser found");

fs.mkdirSync(artifactDir, { recursive: true });
const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport });
const consoleErrors = [];
const pageErrors = [];
const httpErrors = [];
const requestFailures = [];
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("pageerror", (error) => pageErrors.push(error.message));
page.on("response", (response) => {
  if (response.status() >= 400) httpErrors.push({ status: response.status(), url: response.url() });
});
page.on("requestfailed", (request) => {
  requestFailures.push({ url: request.url(), error: request.failure()?.errorText || "unknown" });
});

async function contentOverflow() {
  return page.locator(".tech-content").evaluate((node) => ({
    clientWidth: node.clientWidth,
    scrollWidth: node.scrollWidth,
    overflow: node.scrollWidth > node.clientWidth + 2,
  }));
}

try {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const authResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/auth/register"),
    { timeout: 120000 },
  );
  const sandboxResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/sandbox/ensure"),
    { timeout: 120000 },
  );
  await page.getByPlaceholder("you@court.edu").fill(`tech-evidence-${Date.now()}@example.com`);
  await page.getByPlaceholder("至少 6 位").fill("Tech-Evidence-Smoke-2026!");
  await page.getByRole("button", { name: "注册并进入" }).click();
  const [auth, sandbox] = await Promise.all([authResponse, sandboxResponse]);
  if (auth.status() !== 200 || sandbox.status() !== 200) {
    throw new Error(`Registration bootstrap failed: ${auth.status()}/${sandbox.status()}`);
  }
  await page.locator(".case__version").first().waitFor({ timeout: 60000 });
  await page.getByRole("button", { name: "技术说明" }).click();
  const dialog = page.getByRole("dialog", { name: "学科技术说明" });
  await dialog.waitFor();
  await page.getByText("刑法学科技术说明", { exact: true }).waitFor();
  await page.locator(".pipeline article").first().waitFor({ timeout: 30000 });
  const purposeText = await page.locator(".tech-purpose").innerText();
  if (
    !purposeText.includes("比赛 / 答辩只读视图")
    || !purposeText.includes("不参与学生作答、评分、LearningEvent或长期画像")
  ) throw new Error(`Technical evidence purpose is unclear: ${purposeText}`);

  const overviewPipeline = await page.locator(".pipeline article").count();
  const overviewCards = await page.locator(".overview-grid article").count();
  const readability = {
    tab_font_px: Number.parseFloat(await page.locator(".tech-tabs button").first().evaluate((node) => getComputedStyle(node).fontSize)),
    pipeline_note_font_px: Number.parseFloat(await page.locator(".pipeline p").first().evaluate((node) => getComputedStyle(node).fontSize)),
    boundary_font_px: Number.parseFloat(await page.locator(".global-boundary p").first().evaluate((node) => getComputedStyle(node).fontSize)),
  };
  const overviewText = await page.locator(".tech-content").innerText();
  if (
    overviewPipeline !== 6
    || overviewCards !== 4
    || !overviewText.includes("4,173")
    || !overviewText.includes("813")
    || !overviewText.includes("100题")
    || !overviewText.includes("待完成")
  ) {
    throw new Error(`Overview incomplete: pipeline=${overviewPipeline} cards=${overviewCards}`);
  }
  if (readability.tab_font_px < 12 || readability.pipeline_note_font_px < 10.5 || readability.boundary_font_px < 10) {
    throw new Error(`Technical evidence text too small for recording: ${JSON.stringify(readability)}`);
  }
  const overflow = { overview: await contentOverflow() };
  await page.screenshot({ path: path.join(artifactDir, "01-overview.png") });

  await page.getByRole("button", { name: "数据治理" }).click();
  await page.getByText("候选资料与正式法源分层", { exact: true }).waitFor();
  const ledgerRows = await page.locator(".data-ledger article").count();
  const dataText = await page.locator(".tech-content").innerText();
  if (
    ledgerRows !== 5
    || !dataText.includes("2024-03-01")
    || !dataText.includes("7/7")
    || !dataText.includes("493/505")
    || !dataText.includes("57,051")
    || !dataText.includes("拒绝")
  ) {
    throw new Error(`Data governance incomplete: rows=${ledgerRows}`);
  }
  overflow.data = await contentOverflow();
  await page.screenshot({ path: path.join(artifactDir, "02-data-governance.png") });

  await page.getByRole("button", { name: "推理 / 评测" }).click();
  await page.getByText("结构化推理与100题评测共用来源检查", { exact: true }).waitFor();
  const checks = await page.locator(".check-grid span").count();
  const fixtures = await page.locator(".fixture-list article").count();
  const evalTypes = await page.locator(".eval-types article").count();
  const evalRoutes = await page.locator(".eval-matrix article").count();
  const reasoningText = await page.locator(".tech-content").innerText();
  if (
    checks !== 11
    || fixtures !== 6
    || evalTypes !== 5
    || evalRoutes !== 4
    || !reasoningText.includes("候选Recall@5")
    || !reasoningText.includes("0.8600")
    || !reasoningText.includes("不存在法条误返回")
    || !reasoningText.includes("候选评测集")
    || !reasoningText.includes("待模型交付")
  ) {
    throw new Error(
      `Reasoning/eval incomplete: checks=${checks} fixtures=${fixtures} types=${evalTypes} routes=${evalRoutes}`,
    );
  }
  overflow.reasoning = await contentOverflow();
  await page.screenshot({ path: path.join(artifactDir, "03-reasoning-eval.png") });

  await page.getByRole("button", { name: "Agent / 边界" }).click();
  await page.getByText("增加反方的收益，必须与成本一起展示", { exact: true }).waitFor();
  const conditions = await page.locator(".condition").count();
  const pendingRows = await page.locator(".pending-list article").count();
  const agentText = await page.locator(".tech-content").innerText();
  if (
    conditions !== 2
    || pendingRows !== 4
    || !agentText.includes("×5.7753")
    || !agentText.includes("×2.7167")
    || !agentText.includes("已自动整理格式")
    || !agentText.includes("画像更新0")
  ) {
    throw new Error(`Agent/boundary incomplete: conditions=${conditions} pending=${pendingRows}`);
  }
  overflow.agent = await contentOverflow();
  await page.screenshot({ path: path.join(artifactDir, "04-agent-boundary.png") });

  const privateLeaks = await dialog.evaluate((body) => {
    const text = (body.textContent || "").toLowerCase();
    return [
      "teacher_reference_private",
      "reference_private",
      "typical_errors_private",
      "answer_private",
      "internal_label_mapping",
      '"api_key":',
      "authorization",
      "c:\\users\\",
      "d:\\code\\",
      "e:\\guabangjieshuai",
    ].filter((value) => text.includes(value));
  });
  const technicalLeaks = await dialog.evaluate((body) => {
    const text = (body.textContent || "").toLowerCase();
    return ["sha256", "sha-256", "not_gold", "pending_model_delivery", "fail→id", "artifact_id"]
      .filter((value) => text.includes(value));
  });
  const output = {
    viewport: `${viewport.width}x${viewport.height}`,
    overview_pipeline: overviewPipeline,
    overview_cards: overviewCards,
    purpose_visible: true,
    readability,
    data_ledger_rows: ledgerRows,
    reasoning_checks: checks,
    negative_fixtures: fixtures,
    eval_types: evalTypes,
    eval_routes: evalRoutes,
    agent_conditions: conditions,
    pending_rows: pendingRows,
    horizontal_overflow: overflow,
    private_leaks: privateLeaks,
    technical_leaks: technicalLeaks,
    console_errors: consoleErrors,
    page_errors: pageErrors,
    http_errors: httpErrors,
    request_failures: requestFailures,
    artifact_dir: publicArtifactDir,
  };
  fs.writeFileSync(
    path.join(artifactDir, "report.json"),
    `${JSON.stringify({ generated_at: new Date().toISOString(), ...output }, null, 2)}\n`,
    "utf8",
  );
  console.log(JSON.stringify(output));
  if (
    Object.values(overflow).some((row) => row.overflow)
    || privateLeaks.length
    || technicalLeaks.length
    || consoleErrors.length
    || pageErrors.length
    || httpErrors.length
    || requestFailures.length
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
