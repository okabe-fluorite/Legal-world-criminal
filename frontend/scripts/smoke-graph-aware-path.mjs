import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright-core";

const baseUrl = process.env.GRAPH_PATH_BASE_URL || "http://127.0.0.1:5173";
const artifactDir = path.resolve(
  process.env.GRAPH_PATH_ARTIFACT_DIR || "../.codex-artifacts/graph-aware-path",
);
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
const page = await browser.newPage({ viewport: { width: 1500, height: 980 } });
const errors = { console: [], page: [], http: [], request: [] };
page.on("console", (message) => { if (message.type() === "error") errors.console.push(message.text()); });
page.on("pageerror", (error) => errors.page.push(error.message));
page.on("response", (response) => { if (response.status() >= 400) errors.http.push(`${response.status()} ${response.url()}`); });
page.on("requestfailed", (request) => {
  if (!request.url().startsWith("blob:")) errors.request.push(`${request.url()} ${request.failure()?.errorText || "failed"}`);
});

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
  await page.getByPlaceholder("you@court.edu").fill(`graph-path-${Date.now()}@example.com`);
  await page.getByPlaceholder("至少 6 位").fill("Graph-Path-2026!");
  await page.getByRole("button", { name: "注册并进入" }).click();
  const [auth, sandbox] = await Promise.all([authResponse, sandboxResponse]);
  if (auth.status() !== 200 || sandbox.status() !== 200) {
    throw new Error(`Registration bootstrap failed: ${auth.status()}/${sandbox.status()}`);
  }
  await page.locator(".case__version").first().waitFor({ timeout: 60000 });

  await page.getByRole("button", { name: "自主学习" }).click();
  const journey = page.getByRole("dialog", { name: "刑法自主学习卷宗" });
  await journey.waitFor();
  await journey.locator(".knowledge-tab").filter({ hasText: "故意、过失与意外事件" }).click();
  await journey.locator(".task-sheet").waitFor();
  const options = journey.locator(".option-row");
  const optionCount = await options.count();
  if (optionCount < 2) throw new Error(`Unexpected option count: ${optionCount}`);
  for (let index = 0; index < optionCount; index += 1) await options.nth(index).click();

  const attemptResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/adaptive/attempts") && response.request().method() === "POST",
    { timeout: 120000 },
  );
  await journey.getByRole("button", { name: "完成课前摸底" }).click();
  const response = await attemptResponse;
  if (response.status() !== 200) throw new Error(`Attempt HTTP ${response.status()}`);
  const payload = await response.json();
  const first = payload.recommendations?.[0];
  if (
    payload.learning_event?.grading?.knowledge_status !== "missing"
    || payload.policy_version !== "graph-aware-evidence-cold-start-v2"
    || first?.knowledge_name !== "罪刑法定原则"
    || first?.reason_code !== "prerequisite_for_observed_gap"
    || first?.path_action !== "diagnose_or_reinforce_prerequisite"
    || !first?.supports_target_knowledge_names?.includes("故意、过失与意外事件")
    || first?.prerequisite_path_names?.[0]?.join(" → ") !== "罪刑法定原则 → 犯罪概念与但书 → 故意、过失与意外事件"
  ) throw new Error(`Graph-aware response incomplete: ${JSON.stringify({ policy: payload.policy_version, first })}`);

  await journey.locator(".feedback-sheet").waitFor();
  const firstQueue = journey.locator(".queue-list button").first();
  const queueText = await firstQueue.innerText();
  if (!queueText.includes("罪刑法定原则") || !queueText.includes("罪刑法定原则 → 犯罪概念与但书 → 故意、过失与意外事件")) {
    throw new Error(`Queue did not expose prerequisite rationale: ${queueText}`);
  }
  await page.screenshot({ path: path.join(artifactDir, "01-prerequisite-reordered-queue.png") });
  await journey.getByRole("button", { name: "进入下一任务 →" }).click();
  await journey.locator(".knowledge-brief h3").filter({ hasText: "罪刑法定原则" }).waitFor();
  const nextReason = await journey.locator(".task-sheet__reason").innerText();
  if (!nextReason.includes("先诊断或补强先修") || !nextReason.includes("罪刑法定原则 → 犯罪概念与但书 → 故意、过失与意外事件")) {
    throw new Error(`Next-task rationale incomplete: ${nextReason}`);
  }
  await page.screenshot({ path: path.join(artifactDir, "02-prerequisite-next-task.png") });
  await page.getByRole("button", { name: "关闭自主学习" }).click();

  await page.getByRole("button", { name: "认知诊断" }).click();
  const cognitive = page.getByRole("dialog", { name: "认知诊断与个性化路径驾驶舱" });
  await cognitive.waitFor();
  await cognitive.getByRole("button", { name: "个性化路径" }).click();
  const pathCards = cognitive.locator(".path-map .path-card");
  await pathCards.first().waitFor();
  const diagnosisText = await pathCards.nth(0).innerText();
  const prerequisiteText = await pathCards.nth(1).innerText();
  const nextTaskText = await pathCards.nth(2).innerText();
  if (
    !diagnosisText.includes("故意、过失与意外事件")
    || !prerequisiteText.includes("罪刑法定原则 → 犯罪概念与但书 → 故意、过失与意外事件")
    || !prerequisiteText.includes("3事件/2题门槛")
    || !nextTaskText.includes("目标知识的先修证据不足")
  ) throw new Error(`Path cards incomplete: ${JSON.stringify({ diagnosisText, prerequisiteText, nextTaskText })}`);
  await page.screenshot({ path: path.join(artifactDir, "03-diagnosis-prerequisite-task-path.png") });

  const privateLeaks = await page.locator("body").evaluate((body) => {
    const text = body.textContent || "";
    return ["answer_private", "rationale_private", "misconceptions_private", "source_response_sha256"].filter(
      (value) => text.includes(value),
    );
  });
  const report = {
    policy_version: payload.policy_version,
    observed_gap: "故意、过失与意外事件",
    recommended_prerequisite: first.knowledge_name,
    prerequisite_path: first.prerequisite_path_names?.[0],
    prerequisite_reason: first.reason_code,
    supports_target: first.supports_target_knowledge_names,
    option_count: optionCount,
    queue_reason_visible: true,
    path_cards: 7,
    private_leaks: privateLeaks,
    errors,
  };
  fs.writeFileSync(
    path.join(artifactDir, "report.json"),
    `${JSON.stringify({ generated_at: new Date().toISOString(), ...report }, null, 2)}\n`,
    "utf8",
  );
  console.log(JSON.stringify(report));
  if (privateLeaks.length || Object.values(errors).some((rows) => rows.length)) process.exitCode = 1;
} catch (error) {
  console.error(JSON.stringify({
    smoke_error: error instanceof Error ? error.message : String(error),
    url: page.url(),
    errors,
  }));
  throw error;
} finally {
  await browser.close();
}
