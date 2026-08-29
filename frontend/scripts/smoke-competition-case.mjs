import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright-core";

const baseUrl = process.env.CASE_BASE_URL || "http://127.0.0.1:5173";
const artifactDir = path.resolve(process.env.CASE_ARTIFACT_DIR || "../.codex-artifacts/competition-case");
const candidates = [
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean);
const executablePath = candidates.find((value) => fs.existsSync(value));
if (!executablePath) throw new Error("No installed Chromium browser found");
fs.mkdirSync(artifactDir, { recursive: true });
const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport: { width: 1500, height: 980 } });
const consoleErrors = [];
const pageErrors = [];
const httpErrors = [];
const requestFailures = [];
page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
page.on("pageerror", (error) => pageErrors.push(error.message));
page.on("response", (response) => { if (response.status() >= 400) httpErrors.push({ status: response.status(), url: response.url() }); });
page.on("requestfailed", (request) => requestFailures.push({ url: request.url(), error: request.failure()?.errorText || "unknown" }));

try {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const authResponse = page.waitForResponse((response) => response.url().endsWith("/api/auth/register"), { timeout: 120000 });
  const sandboxResponse = page.waitForResponse((response) => response.url().endsWith("/api/sandbox/ensure"), { timeout: 120000 });
  await page.getByPlaceholder("you@court.edu").fill(`case-showcase-${Date.now()}@example.com`);
  await page.getByPlaceholder("至少 6 位").fill("Case-Showcase-2026!");
  await page.getByRole("button", { name: "注册并进入" }).click();
  const [auth, sandbox] = await Promise.all([authResponse, sandboxResponse]);
  if (auth.status() !== 200 || sandbox.status() !== 200) throw new Error(`bootstrap=${auth.status()}/${sandbox.status()}`);
  const caseCard = page.locator(".case--competition");
  await caseCard.waitFor({ timeout: 60000 });
  const cardText = await caseCard.innerText();
  if (!cardText.includes("指导案例144号") || !cardText.includes("PR不起诉分支")) {
    throw new Error(`Competition case card is incomplete: ${cardText}`);
  }
  await page.screenshot({ path: path.join(artifactDir, "01-case-picker.png"), fullPage: false });
  await caseCard.getByRole("button", { name: /进入标杆案/ }).click();
  await page.getByText("张那木拉特殊防卫 · 比赛标杆路线", { exact: true }).waitFor();
  const guideText = await page.locator(".competition-guide").innerText();
  if (!guideText.includes("真实E2E 379.0s") || !guideText.includes("3/3 Agent退场") || !guideText.includes("0 runtime issue")) {
    throw new Error(`Competition guide lacks real audit labels: ${guideText}`);
  }
  await page.screenshot({ path: path.join(artifactDir, "02-mode-guide.png"), fullPage: false });
  const output = {
    competition_case: "case_3",
    branch: "LC->INV->PR->non_prosecution",
    real_e2e_seconds: 379.0,
    card_visible: true,
    guide_visible: true,
    console_errors: consoleErrors,
    page_errors: pageErrors,
    http_errors: httpErrors,
    request_failures: requestFailures,
    artifact_dir: artifactDir,
  };
  console.log(JSON.stringify(output));
  if (consoleErrors.length || pageErrors.length || httpErrors.length || requestFailures.length) process.exitCode = 1;
} finally {
  await browser.close();
}
