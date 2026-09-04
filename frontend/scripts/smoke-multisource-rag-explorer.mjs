import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright-core";

const baseUrl = process.env.MULTISOURCE_RAG_BASE_URL || "http://127.0.0.1:5173";
const artifactDir = path.resolve(
  process.env.MULTISOURCE_RAG_ARTIFACT_DIR || "../.codex-artifacts/multisource-rag-explorer",
);
const browserCandidates = [
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean);
const executablePath = browserCandidates.find((candidate) => fs.existsSync(candidate));
if (!executablePath) throw new Error("No installed Chromium browser found");
const viewport = {
  width: Number(process.env.MULTISOURCE_RAG_VIEWPORT_WIDTH || 1500),
  height: Number(process.env.MULTISOURCE_RAG_VIEWPORT_HEIGHT || 980),
};

fs.mkdirSync(artifactDir, { recursive: true });
const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport });
const errors = { console: [], page: [], http: [], request: [] };
page.on("console", (message) => { if (message.type() === "error") errors.console.push(message.text()); });
page.on("pageerror", (error) => errors.page.push(error.message));
page.on("response", (response) => { if (response.status() >= 400) errors.http.push(`${response.status()} ${response.url()}`); });
page.on("requestfailed", (request) => {
  if (!request.url().startsWith("blob:")) errors.request.push(`${request.url()} ${request.failure()?.errorText || "failed"}`);
});

const checks = [];
let noAnswerAbstention = false;
let repealedSourceGuard = false;

async function runPreset(index, expected) {
  const responsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/api/knowledge/search") && response.request().method() === "POST",
    { timeout: 180000 },
  );
  await page.locator(".explorer-presets button").nth(index).click();
  const response = await responsePromise;
  if (response.status() !== 200) throw new Error(`Preset ${index} HTTP ${response.status()}`);
  await page.locator(".source-role-answer").waitFor({ timeout: 180000 });
  await page.getByText(expected.role, { exact: true }).waitFor();
  const marks = page.locator(`.source-role-answer ${expected.selector}`);
  await marks.first().waitFor();
  const count = await marks.count();
  await marks.first().hover();
  const tooltip = page.locator(".evidence-tooltip");
  await tooltip.waitFor();
  const tooltipText = await tooltip.innerText();
  if (!tooltipText.includes("点击展开完整证据") || tooltipText.length > 260) {
    throw new Error(`Preset ${index} tooltip invalid: ${tooltipText}`);
  }
  await marks.first().click();
  const drawer = page.locator(".evidence-drawer");
  await drawer.waitFor();
  const drawerText = await drawer.innerText();
  for (const needle of expected.drawer) {
    if (!drawerText.includes(needle)) throw new Error(`Preset ${index} drawer missing: ${needle}`);
  }
  if (/SHA-256|Evidence ID|EVID_[A-Z0-9]+|retrieval_id|fallback_to_/i.test(drawerText)) {
    throw new Error(`Preset ${index} exposed internal fields`);
  }
  await page.screenshot({
    path: path.join(artifactDir, `${String(index + 1).padStart(2, "0")}-${expected.name}.png`),
  });
  await drawer.getByRole("button", { name: "关闭完整证据" }).click();
  checks.push({
    source: expected.name,
    citation_marks: count,
    tooltip_concise: true,
    drawer_fields_verified: expected.drawer,
  });
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
  await page.getByPlaceholder("you@court.edu").fill(`multisource-rag-${Date.now()}@example.com`);
  await page.getByPlaceholder("至少 6 位").fill("Multisource-Rag-2026!");
  await page.getByRole("button", { name: "注册并进入" }).click();
  const [auth, sandbox] = await Promise.all([authResponse, sandboxResponse]);
  if (auth.status() !== 200 || sandbox.status() !== 200) {
    throw new Error(`Registration bootstrap failed: ${auth.status()}/${sandbox.status()}`);
  }
  await page.locator(".case__version").first().waitFor({ timeout: 60000 });
  await page.getByRole("button", { name: "可信RAG" }).click();
  await page.getByRole("dialog", { name: "可信RAG与三个典型问题验证" }).waitFor();
  await page.getByRole("button", { name: "自由检索" }).click();
  await page.getByText("输入问题，查看不同法源各自能做什么", { exact: true }).waitFor();

  await runPreset(0, {
    name: "law",
    selector: ".citation-mark--law",
    role: "规范依据",
    drawer: ["法律", "规范依据", "已核实当前版本"],
  });
  const graphText = await page.locator(".graph-context").innerText();
  if (!graphText.includes("正当防卫与防卫过当") || !graphText.includes("犯罪概念与但书")) {
    throw new Error(`Knowledge graph context incomplete: ${graphText}`);
  }

  await runPreset(1, {
    name: "judicial",
    selector: ".citation-mark--judicial",
    role: "司法适用",
    drawer: ["司法解释 / 司法文件", "司法适用依据", "效力尚未完全核实", "最高人民检察院"],
  });
  await runPreset(2, {
    name: "case",
    selector: ".citation-mark--case",
    role: "案例参考",
    drawer: ["指导性 / 典型案例", "裁判参考 / 事实示例", "CASE PARENT CONTEXT"],
  });
  await runPreset(3, {
    name: "textbook",
    selector: ".citation-mark--course",
    role: "教材解释",
    drawer: ["教材解释", "课堂与学理解释", "教材版次待补充", "教材解释不能替代现行法"],
  });
  await runPreset(4, {
    name: "resource",
    selector: ".citation-mark--resource",
    role: "下一步练习",
    drawer: ["公开学习资源", "相似题 / 练习推荐", "学习资源不适用法律效力状态"],
  });

  const missingResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/knowledge/search") && response.request().method() === "POST",
    { timeout: 180000 },
  );
  await page.locator("#rag-free-query").fill("请查找《不存在的测试法》第九百九十九条");
  await page.getByRole("button", { name: "检索多来源Evidence →" }).click();
  if ((await missingResponse).status() !== 200) throw new Error("Missing-law query failed");
  await page.getByText("当前证据不足", { exact: true }).waitFor();
  noAnswerAbstention = (await page.locator(".source-role-answer .citation-mark").count()) === 0;
  if (!noAnswerAbstention) throw new Error("Missing-law query returned a visible citation");

  const repealedResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/knowledge/search") && response.request().method() === "POST",
    { timeout: 180000 },
  );
  await page.locator("#rag-free-query").fill("《中华人民共和国噪声污染防治法》现在还能否作为现行法依据？");
  await page.getByRole("button", { name: "检索多来源Evidence →" }).click();
  if ((await repealedResponse).status() !== 200) throw new Error("Repealed-law query failed");
  const repealedCitation = page.getByRole("button", { name: /噪声污染防治法.*点击查看完整证据/ }).first();
  await repealedCitation.waitFor();
  await repealedCitation.click();
  const repealedDrawer = page.locator(".evidence-drawer");
  const repealedText = await repealedDrawer.innerText();
  repealedSourceGuard = repealedText.includes("已废止")
    && repealedText.includes("已废止，不得作为现行法依据");
  if (!repealedSourceGuard) throw new Error(`Repealed-law guard missing: ${repealedText}`);
  await repealedDrawer.getByRole("button", { name: "关闭完整证据" }).click();

  const boardText = await page.locator(".rag-board").innerText();
  const privateLeaks = [
    "answer_private",
    "rationale_private",
    "misconceptions_private",
    "teacher_reference_private",
    "EVID_",
    "SHA-256",
    "retrieval_id",
  ].filter((value) => boardText.includes(value));
  const horizontalOverflow = await page.locator(".rag-board").evaluate((node) => ({
    clientWidth: node.clientWidth,
    scrollWidth: node.scrollWidth,
    overflow: node.scrollWidth > node.clientWidth + 2,
  }));
  const report = {
    viewport: `${viewport.width}x${viewport.height}`,
    checks,
    graph_context_verified: true,
    no_answer_abstention: noAnswerAbstention,
    repealed_source_guard: repealedSourceGuard,
    private_leaks: privateLeaks,
    horizontal_overflow: horizontalOverflow,
    errors,
  };
  fs.writeFileSync(
    path.join(artifactDir, "report.json"),
    `${JSON.stringify({ generated_at: new Date().toISOString(), ...report }, null, 2)}\n`,
    "utf8",
  );
  console.log(JSON.stringify(report));
  if (
    checks.length !== 5
    || !noAnswerAbstention
    || !repealedSourceGuard
    || privateLeaks.length
    || horizontalOverflow.overflow
    || Object.values(errors).some((rows) => rows.length)
  ) process.exitCode = 1;
} catch (error) {
  console.error(JSON.stringify({
    smoke_error: error instanceof Error ? error.message : String(error),
    url: page.url(),
    checks,
    errors,
  }));
  throw error;
} finally {
  await browser.close();
}
