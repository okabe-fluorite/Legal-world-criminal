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
  await page.getByRole("button", { name: "技术证据" }).click();
  const dialog = page.getByRole("dialog", { name: "学科技术证据总账" });
  await dialog.waitFor();
  await page.getByText("刑法学科技术证据总账", { exact: true }).waitFor();
  await page.locator(".pipeline article").first().waitFor({ timeout: 30000 });

  const overviewPipeline = await page.locator(".pipeline article").count();
  const overviewCards = await page.locator(".overview-grid article").count();
  const overviewText = await page.locator(".tech-content").innerText();
  if (
    overviewPipeline !== 5
    || overviewCards !== 4
    || !overviewText.includes("4,173")
    || !overviewText.includes("813")
    || !overviewText.includes("100题")
    || !overviewText.includes("PENDING")
  ) {
    throw new Error(`Overview incomplete: pipeline=${overviewPipeline} cards=${overviewCards}`);
  }
  const overflow = { overview: await contentOverflow() };
  await page.screenshot({ path: path.join(artifactDir, "01-overview.png") });

  await page.getByRole("button", { name: "数据治理" }).click();
  await page.getByText("文件库存与正式Evidence严格分层", { exact: true }).waitFor();
  const ledgerRows = await page.locator(".data-ledger article").count();
  const dataText = await page.locator(".tech-content").innerText();
  if (
    ledgerRows !== 4
    || !dataText.includes("2024-03-01")
    || !dataText.includes("7/7")
    || !dataText.includes("493/505")
    || !dataText.includes("拒绝")
  ) {
    throw new Error(`Data governance incomplete: rows=${ledgerRows}`);
  }
  overflow.data = await contentOverflow();
  await page.screenshot({ path: path.join(artifactDir, "02-data-governance.png") });

  await page.getByRole("button", { name: "推理 / 评测" }).click();
  await page.getByText("结构化推理与100题评测共用Evidence纪律", { exact: true }).waitFor();
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
    || !reasoningText.includes("not_gold")
    || !reasoningText.includes("pending_model_delivery")
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
    || !agentText.includes("FAIL→ID归一")
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
  const output = {
    viewport: `${viewport.width}x${viewport.height}`,
    overview_pipeline: overviewPipeline,
    overview_cards: overviewCards,
    data_ledger_rows: ledgerRows,
    reasoning_checks: checks,
    negative_fixtures: fixtures,
    eval_types: evalTypes,
    eval_routes: evalRoutes,
    agent_conditions: conditions,
    pending_rows: pendingRows,
    horizontal_overflow: overflow,
    private_leaks: privateLeaks,
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
