import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright-core";

const baseUrl = process.env.JOURNEY_BASE_URL || "http://127.0.0.1:5173";
const screenshotPath = path.resolve(
  process.env.JOURNEY_SCREENSHOT || "../.codex-artifacts/learning-journey.png",
);
const reviewScreenshotPath = path.resolve(
  process.env.JOURNEY_REVIEW_SCREENSHOT || "../.codex-artifacts/learning-journey-review.png",
);
const reportPath = path.resolve(
  process.env.JOURNEY_REPORT || path.join(path.dirname(screenshotPath), "learning-phases-report.json"),
);
const supportScreenshotPath = path.resolve(
  process.env.JOURNEY_SUPPORT_SCREENSHOT || "../.codex-artifacts/learning-support-panel.png",
);
const viewport = {
  width: Number(process.env.JOURNEY_VIEWPORT_WIDTH || 1500),
  height: Number(process.env.JOURNEY_VIEWPORT_HEIGHT || 980),
};
const executableCandidates = [
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean);
const executablePath = executableCandidates.find((candidate) => fs.existsSync(candidate));

if (!executablePath) {
  throw new Error("No installed Chromium browser found; set PLAYWRIGHT_CHROMIUM_EXECUTABLE");
}

fs.mkdirSync(path.dirname(screenshotPath), { recursive: true });
fs.mkdirSync(path.dirname(reviewScreenshotPath), { recursive: true });
fs.mkdirSync(path.dirname(reportPath), { recursive: true });
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
  if (response.status() >= 400) {
    httpErrors.push({ status: response.status(), url: response.url() });
  }
});
page.on("requestfailed", (request) => {
  requestFailures.push({ url: request.url(), error: request.failure()?.errorText || "unknown" });
});

try {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const email = `journey-${Date.now()}@example.com`;
  await page.getByPlaceholder("you@court.edu").fill(email);
  await page.getByPlaceholder("至少 6 位").fill("Journey-Smoke-2026!");
  await page.getByRole("button", { name: "注册并进入" }).click();
  await page.getByRole("button", { name: "自主学习" }).waitFor({ state: "visible" });
  await page.locator(".case__version").first().waitFor({ state: "visible" });
  const governedCaseCount = await page.locator(".case__version").count();
  const caseEvidenceCount = await page.locator(".case__evidence").count();
  if (governedCaseCount !== 3 || caseEvidenceCount !== 3) {
    throw new Error(
      `Expected 3 governed case entries, got versions=${governedCaseCount} evidence=${caseEvidenceCount}`,
    );
  }
  await page.getByRole("button", { name: "自主学习" }).click();
  await page.getByRole("dialog", { name: "刑法自主学习卷宗" }).waitFor({ state: "visible" });
  await page.getByText("本课知识地图", { exact: true }).waitFor();

  const knowledgeCount = await page.locator(".knowledge-tab").count();
  const optionCount = await page.locator(".option-row").count();
  if (knowledgeCount !== 10) throw new Error(`Expected 10 knowledge cards, received ${knowledgeCount}`);
  if (optionCount < 2) throw new Error(`Expected executable task options, received ${optionCount}`);

  await page.locator(".option-row").first().click();
  await page.getByRole("button", { name: "完成课前摸底" }).click();
  await page.locator(".feedback-sheet").waitFor({ state: "visible" });
  const feedbackVisible = await page.locator(".feedback-sheet__rationale").isVisible();
  const nextTaskVisible = await page.getByRole("button", { name: /进入下一任务/ }).isVisible();

  await page.getByRole("button", { name: "填写" }).click();
  await page.getByPlaceholder(/写下.*条件、事实或证据|写下.*规则边界、错因或证据缺口/).fill(
    "我不确定规范条件如何适用于题目中的具体事实。",
  );
  await page.getByRole("button", { name: "加入课前问题单" }).click();
  await page.getByText("困惑已进入证据账本，后续任务会优先回应。").waitFor();

  let learningSupport = { tested: false, source: "not_requested", layers: 0, tutor: false };
  if (process.env.JOURNEY_TEST_SUPPORT === "1") {
    await page.getByRole("button", { name: /开始分层解惑/ }).click();
    await page.getByRole("dialog", { name: "AI分层解惑" }).waitFor();
    await page.getByPlaceholder(/请先写出你的判断依据/).fill(
      "我认为应先找出题目中的关键事实，再把该事实与法条列出的每个条件逐项对应，但我还不确定边界事实如何评价。",
    );
    await page.getByRole("button", { name: /生成分层解释/ }).click();
    await page.getByText("规范原文", { exact: true }).waitFor({ timeout: 210000 });
    const diagnosisText = await page.locator(".diagnosis-strip").innerText();
    const tutor = page.locator(".support-main .ai-tutor");
    await tutor.waitFor();
    const tutorText = await tutor.innerText();
    const tutorButtonLocator = tutor.getByRole("button", { name: "朗读本段" });
    const tutorButton = await tutorButtonLocator.isVisible();
    let mouthAnimation = "not_requested";
    if (process.env.JOURNEY_TEST_TUTOR_SPEECH === "1") {
      const idleSource = await tutor.locator("img").getAttribute("src");
      await tutorButtonLocator.click();
      await tutor.getByRole("button", { name: "停止朗读" }).waitFor({ timeout: 10000 });
      await page.waitForTimeout(190);
      const speakingSource = await tutor.locator("img").getAttribute("src");
      if (!speakingSource || speakingSource === idleSource) {
        throw new Error(`Tutor mouth did not switch: ${idleSource} -> ${speakingSource}`);
      }
      mouthAnimation = "verified_state_switch";
      await tutor.getByRole("button", { name: "停止朗读" }).click();
    }
    learningSupport = {
      tested: true,
      source: diagnosisText.includes("DETERMINISTIC FALLBACK")
        ? "deterministic_fallback"
        : "llm_governed_evidence",
      layers: await page.locator(".layer-card").count(),
      tutor: tutorText.includes("AI助教·形成性反馈") && tutorButton,
      mouth_animation: mouthAnimation,
    };
    if (!learningSupport.tutor) throw new Error(`Learning tutor incomplete: ${tutorText}`);
    await page.screenshot({ path: supportScreenshotPath, fullPage: false });
    await page.getByRole("button", { name: "关闭分层解惑" }).click();
  }

  const profileMetrics = await page.locator(".ledger-metrics b").allTextContents();
  const privateFieldLeaks = await page.locator("body").evaluate((body) => {
    const text = body.textContent || "";
    return ["answer_private", "rationale_private", "misconceptions_private"].filter((key) =>
      text.includes(key),
    );
  });
  const prestudyTitle = await page.locator(".phase-story__copy h3").innerText();
  const prestudyAccent = await page.locator(".phase-story").evaluate((node) => getComputedStyle(node).borderBottomColor);
  const stemFontSize = Number.parseFloat(await page.locator(".task-sheet__stem").evaluate((node) => getComputedStyle(node).fontSize));
  const optionFontSize = Number.parseFloat(await page.locator(".option-row__text").first().evaluate((node) => getComputedStyle(node).fontSize));
  await page.locator(".journey").evaluate((root) => root.querySelectorAll(".index-pane, .task-pane, .ledger-pane").forEach((node) => { node.scrollTop = 0; }));
  await page.screenshot({ path: screenshotPath, fullPage: false });

  await page.getByRole("button", { name: "课后复习" }).click();
  await page.locator(".journey--review").waitFor();
  const reviewScrollReset = await page.locator(".journey").evaluate((root) => [...root.querySelectorAll(".index-pane, .task-pane, .ledger-pane")].map((node) => node.scrollTop));
  await page.getByText("用证据完成一次课后复盘", { exact: true }).waitFor();
  await page.getByText("错因与知识清单", { exact: true }).waitFor();
  await page.getByText("巩固与再测队列", { exact: true }).waitFor();
  const reviewTitle = await page.locator(".phase-story__copy h3").innerText();
  const reviewAccent = await page.locator(".phase-story").evaluate((node) => getComputedStyle(node).borderBottomColor);
  const reviewJourneyClass = await page.locator(".journey").getAttribute("class");
  if (
    prestudyTitle === reviewTitle
    || prestudyAccent === reviewAccent
    || !reviewJourneyClass?.includes("journey--review")
    || reviewScrollReset.some((value) => value > 1)
    || stemFontSize < 18
    || optionFontSize < 15
  ) {
    throw new Error(`Journey phases are not visually distinct/readable: ${JSON.stringify({ prestudyTitle, reviewTitle, prestudyAccent, reviewAccent, reviewJourneyClass, reviewScrollReset, stemFontSize, optionFontSize })}`);
  }
  await page.screenshot({ path: reviewScreenshotPath, fullPage: false });

  const result = {
    url: page.url(),
    viewport: `${viewport.width}x${viewport.height}`,
    knowledge_cards: knowledgeCount,
    governed_case_entries: governedCaseCount,
    option_count: optionCount,
    feedback_visible: feedbackVisible,
    next_task_visible: nextTaskVisible,
    profile_metrics: profileMetrics,
    phase_design: {
      prestudy_title: prestudyTitle,
      review_title: reviewTitle,
      prestudy_accent: prestudyAccent,
      review_accent: reviewAccent,
      stem_font_px: stemFontSize,
      option_font_px: optionFontSize,
      review_scroll_reset: reviewScrollReset,
      distinct: true,
    },
    learning_support: learningSupport,
    private_field_leaks: privateFieldLeaks,
    console_errors: consoleErrors,
    page_errors: pageErrors,
    http_errors: httpErrors,
    request_failures: requestFailures,
    screenshot: screenshotPath,
    review_screenshot: reviewScreenshotPath,
    support_screenshot: learningSupport.tested ? supportScreenshotPath : null,
  };
  const repoRoot = path.resolve("..");
  const publicPath = (value) => path.relative(repoRoot, value).split(path.sep).join("/");
  const publicResult = {
    ...result,
    screenshot: publicPath(screenshotPath),
    review_screenshot: publicPath(reviewScreenshotPath),
    support_screenshot: learningSupport.tested ? publicPath(supportScreenshotPath) : null,
  };
  fs.writeFileSync(reportPath, `${JSON.stringify({ generated_at: new Date().toISOString(), ...publicResult }, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(result));
  const unexpectedRequestFailures = requestFailures.filter(
    (failure) => !failure.url.startsWith("ws://") && !failure.url.startsWith("wss://"),
  );
  if (
    privateFieldLeaks.length ||
    consoleErrors.length ||
    pageErrors.length ||
    httpErrors.length ||
    unexpectedRequestFailures.length
  ) {
    process.exitCode = 1;
  }
} finally {
  await browser.close();
}
