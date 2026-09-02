import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright-core";

const baseUrl = process.env.RAG_BASE_URL || "http://127.0.0.1:5173";
const artifactDir = path.resolve(
  process.env.RAG_ARTIFACT_DIR || "../.codex-artifacts/trusted-rag",
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

try {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const email = `trusted-rag-${Date.now()}@example.com`;
  const authResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/auth/register"),
    { timeout: 120000 },
  );
  const sandboxResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/sandbox/ensure"),
    { timeout: 120000 },
  );
  await page.getByPlaceholder("you@court.edu").fill(email);
  await page.getByPlaceholder("至少 6 位").fill("Trusted-Rag-2026!");
  await page.getByRole("button", { name: "注册并进入" }).click();
  const [auth, sandbox] = await Promise.all([authResponse, sandboxResponse]);
  if (auth.status() !== 200 || sandbox.status() !== 200) {
    throw new Error(`Registration bootstrap failed: ${auth.status()}/${sandbox.status()}`);
  }
  await page.getByRole("button", { name: "可信RAG" }).click();
  const dialog = page.getByRole("dialog", { name: "可信RAG与三个典型问题验证" });
  await dialog.waitFor();
  await page.getByText("刑法可信问答验证台", { exact: true }).waitFor();
  await page.locator(".question-list button").first().waitFor({ timeout: 30000 });
  await page.locator(".rag-score").getByText("3/3", { exact: true }).waitFor();
  const questions = await page.locator(".question-list button").count();
  if (questions !== 3) throw new Error(`Expected 3 typical questions, received ${questions}`);

  const results = [];
  for (let index = 0; index < questions; index += 1) {
    await page.locator(".question-list button").nth(index).click();
    const title = await page.locator(".question-list button").nth(index).locator("strong").innerText();
    const sourceCount = await page.locator(".sources > article").count();
    const citationCount = await page.locator(".citation-proof article").count();
    const gateText = await page.locator(".gate-strip").innerText();
    const expertText = await page.locator(".expert-status").innerText();
    if (!gateText.includes("100%") || !expertText.includes("待复核") || sourceCount < 1 || citationCount < 1) {
      throw new Error(
        `Question ${index + 1} incomplete: sources=${sourceCount} citations=${citationCount}`,
      );
    }
    results.push({ title, source_count: sourceCount, citation_count: citationCount });
    await page.screenshot({
      path: path.join(artifactDir, `0${index + 1}-question.png`),
      fullPage: false,
    });
  }

  await page.getByRole("button", { name: /演示错误引用检查/ }).click();
  await page.getByText("2/2 条错误已发现", { exact: true }).waitFor();
  const badRows = await page.locator(".bad-audit-result article").count();
  if (badRows !== 2) throw new Error(`Expected 2 rejected citation rows, received ${badRows}`);
  const evidenceTutor = page.locator(".evidence-tutor .ai-tutor");
  await evidenceTutor.waitFor();
  const evidenceTutorText = await evidenceTutor.innerText();
  if (!evidenceTutorText.includes("AI助教·形成性反馈") || !evidenceTutorText.includes("引用不能直接采信")) {
    throw new Error(`Evidence tutor incomplete: ${evidenceTutorText}`);
  }
  await page.screenshot({ path: path.join(artifactDir, "04-bad-citation-gate.png"), fullPage: false });

  const privateLeaks = await dialog.evaluate((body) => {
    const text = (body.textContent || "").toLowerCase();
    return [
      "api_key",
      "teacher_reference_private",
      "expected_points_private",
      "sha-256",
      "sha256",
      "evidence id",
      "not_gold",
      "pending_model_delivery",
    ].filter(
      (value) => text.includes(value),
    );
  });
  const output = {
    questions: results,
    citation_checks: "3/3",
    expert_review: "pending",
    rejected_bad_citations: badRows,
    evidence_tutor: evidenceTutorText,
    private_leaks: privateLeaks,
    console_errors: consoleErrors,
    page_errors: pageErrors,
    http_errors: httpErrors,
    request_failures: requestFailures,
    artifact_dir: artifactDir,
  };
  console.log(JSON.stringify(output));
  if (
    privateLeaks.length
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
