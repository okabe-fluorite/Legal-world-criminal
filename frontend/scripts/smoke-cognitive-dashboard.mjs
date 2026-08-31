import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright-core";

const baseUrl = process.env.COGNITIVE_BASE_URL || "http://127.0.0.1:5173";
const artifactDir = path.resolve(
  process.env.COGNITIVE_ARTIFACT_DIR || "../.codex-artifacts/cognitive-dashboard",
);
const repoRoot = path.resolve("..");
const publicArtifactDir = path.relative(repoRoot, artifactDir).split(path.sep).join("/");
if (!publicArtifactDir || publicArtifactDir.startsWith("../")) {
  throw new Error("Cognitive artifacts must stay inside the repository");
}
const verificationAudio = path.resolve(
  process.env.COGNITIVE_IFLYTEK_AUDIO
    || "../competition_submission/03-Demo/iflytek-speech/iflytek-tts-verification.wav",
);
const viewport = {
  width: Number(process.env.COGNITIVE_VIEWPORT_WIDTH || 1500),
  height: Number(process.env.COGNITIVE_VIEWPORT_HEIGHT || 980),
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
  if (request.url().startsWith("blob:")) return;
  requestFailures.push({ url: request.url(), error: request.failure()?.errorText || "unknown" });
});

try {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const email = `cognitive-${Date.now()}@example.com`;
  const authResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/auth/register"),
    { timeout: 120000 },
  );
  const sandboxResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/sandbox/ensure"),
    { timeout: 120000 },
  );
  await page.getByPlaceholder("you@court.edu").fill(email);
  await page.getByPlaceholder("至少 6 位").fill("Cognitive-Smoke-2026!");
  await page.getByRole("button", { name: "注册并进入" }).click();
  const [auth, sandbox] = await Promise.all([authResponse, sandboxResponse]);
  if (auth.status() !== 200 || sandbox.status() !== 200) {
    throw new Error(`Registration bootstrap failed: ${auth.status()}/${sandbox.status()}`);
  }
  await page.locator(".case__version").first().waitFor({ timeout: 60000 });

  await page.getByRole("button", { name: "自主学习" }).click();
  await page.getByRole("dialog", { name: "刑法自主学习卷宗" }).waitFor();
  await page.locator(".option-row").first().waitFor({ timeout: 60000 });
  await page.locator(".option-row").first().click();
  await page.getByRole("button", { name: "提交取证" }).click();
  await page.locator(".feedback-sheet").waitFor();
  await page.getByRole("button", { name: "填写" }).click();
  await page.getByPlaceholder("具体写下你卡住的条件、事实或证据……").fill(
    "我不确定该规范的边界条件如何对应题目事实，需要进一步比较。",
  );
  await page.getByRole("button", { name: "归入证据账本" }).click();
  await page.getByText("困惑已进入证据账本，后续任务会优先回应。").waitFor();
  await page.getByRole("button", { name: "关闭自主学习" }).click();

  await page.getByRole("button", { name: "认知诊断" }).click();
  const dialog = page.getByRole("dialog", { name: "认知诊断与个性化路径驾驶舱" });
  await dialog.waitFor();
  await page.getByText("Evidence-KT / V0 保守画像", { exact: true }).waitFor();
  const knowledgeRows = await page.locator(".knowledge-table article").count();
  const timelineRows = await page.locator(".timeline li").count();
  if (knowledgeRows !== 10 || timelineRows !== 2) {
    throw new Error(`Unexpected diagnosis rows: knowledge=${knowledgeRows} timeline=${timelineRows}`);
  }
  await page.screenshot({ path: path.join(artifactDir, "01-diagnosis.png"), fullPage: false });

  await page.getByRole("button", { name: "ORCDF SHADOW" }).click();
  await page.getByText("ORCDF真实训练实验，不进入当前刑法学生画像", { exact: true }).waitFor();
  const versions = await page.locator(".orcdf-versions article").count();
  const heatCells = await page.locator(".heat-cell").count();
  if (versions !== 3 || heatCells !== 48) {
    throw new Error(`Unexpected ORCDF rendering: versions=${versions} heatCells=${heatCells}`);
  }
  await page.screenshot({ path: path.join(artifactDir, "02-orcdf-shadow.png"), fullPage: false });

  await page.getByRole("button", { name: "个性化路径" }).click();
  await page.getByText("从证据薄弱点到下一条LearningEvent", { exact: true }).waitFor();
  const pathNodes = await page.locator(".path-map article").count();
  const pathTutor = page.locator(".path-tutor .ai-tutor");
  await pathTutor.waitFor();
  const pathTutorLabel = await pathTutor.innerText();
  const pathTutorImage = await pathTutor.locator("img").evaluate((image) => ({
    naturalWidth: image.naturalWidth,
    naturalHeight: image.naturalHeight,
  }));
  if (!pathTutorLabel.includes("AI助教·形成性反馈") || pathTutorImage.naturalWidth !== 768) {
    throw new Error(`Path tutor incomplete: ${pathTutorLabel} ${JSON.stringify(pathTutorImage)}`);
  }
  if (pathNodes !== 7) throw new Error(`Expected 7 path nodes, received ${pathNodes}`);
  await page.screenshot({ path: path.join(artifactDir, "03-personal-path.png"), fullPage: false });

  await page.getByRole("button", { name: "知识 / 论证图" }).click();
  await page.getByText("课程先修图与法律论证模板", { exact: true }).waitFor();
  const knowledgeNodes = await page.locator(".knowledge-node").count();
  const knowledgeEdges = await page.locator(".knowledge-edge").count();
  const argumentNodes = await page.locator(".argument-chain article").count();
  if (knowledgeNodes !== 10 || knowledgeEdges !== 10 || argumentNodes !== 6) {
    throw new Error(
      `Unexpected graph rendering: nodes=${knowledgeNodes} edges=${knowledgeEdges} argument=${argumentNodes}`,
    );
  }
  await page.screenshot({ path: path.join(artifactDir, "04-knowledge-argument-graphs.png"), fullPage: false });

  await page.getByRole("button", { name: "模型路由" }).click();
  await page.getByText("基础模型 / Prompt / RAG / RAG+微调", { exact: true }).waitFor();
  const routeCards = await page.locator(".route-grid article").count();
  const modelText = await page.locator(".model-status").innerText();
  if (routeCards !== 4) throw new Error(`Expected 4 model routes, received ${routeCards}`);
  await page.screenshot({ path: path.join(artifactDir, "05-model-routes.png"), fullPage: false });

  await page.getByRole("button", { name: "多模态 / 数字人" }).click();
  await page.getByText("实时语音多模态与数字人边界", { exact: true }).waitFor();
  const mediaCapabilities = await page.locator(".media-capability-grid article").count();
  if (mediaCapabilities !== 5) {
    throw new Error(`Expected 5 media capabilities, received ${mediaCapabilities}`);
  }
  await page.getByRole("button", { name: "生成讯飞WAV" }).click();
  await page.getByText(/讯飞TTS真实生成/).waitFor({ timeout: 60000 });
  await page.locator("audio[aria-label='讯飞AI合成音频']").waitFor();
  await page.getByRole("button", { name: "将WAV送入ASR" }).click();
  await page.getByText(/讯飞ASR已返回真实转写/).waitFor({ timeout: 60000 });
  const roundTripStatus = await page.locator(".media-result").innerText();
  if (
    !roundTripStatus.includes("iflytek_websocket")
    || !roundTripStatus.includes("needs_review")
    || !roundTripStatus.includes("罪刑法定")
  ) {
    throw new Error(`iFlytek UI round trip incomplete: ${roundTripStatus}`);
  }
  await page.screenshot({ path: path.join(artifactDir, "06-iflytek-tts-asr.png"), fullPage: false });
  await page.locator(".media-upload input").setInputFiles(verificationAudio);
  await page.getByText(/讯飞ASR已生成真实转写/).waitFor({ timeout: 60000 });
  const mediaProofRows = await page.locator(".media-proof div").count();
  if (mediaProofRows !== 3) throw new Error(`Expected 3 media proof rows, received ${mediaProofRows}`);
  const availableCapabilities = await page.locator(".media-capability-grid article.ready").count();
  if (availableCapabilities !== 3) {
    throw new Error(`Expected upload/ASR/TTS available, received ${availableCapabilities}`);
  }
  await page.getByRole("button", { name: "调用预留接口验证状态" }).click();
  await page.getByText(/数字人异步契约已真实调用/).waitFor();
  const mediaStatus = await page.locator(".media-result").innerText();
  if (!mediaStatus.includes("not_connected")) {
    throw new Error(`Media provider boundary missing: ${mediaStatus}`);
  }
  await page.screenshot({ path: path.join(artifactDir, "07-media-avatar-boundary.png"), fullPage: false });

  const privateLeaks = await page.locator(".cog-board").evaluate((body) => {
    const text = body.textContent || "";
    return ["answer_private", "rationale_private", "api_key", "source_response_sha256", "storage_root"].filter(
      (key) => text.includes(key),
    );
  });
  const result = {
    viewport: `${viewport.width}x${viewport.height}`,
    knowledge_rows: knowledgeRows,
    timeline_rows: timelineRows,
    orcdf_versions: versions,
    heatmap_cells: heatCells,
    path_nodes: pathNodes,
    path_tutor: { label: pathTutorLabel, image: pathTutorImage },
    knowledge_graph_nodes: knowledgeNodes,
    knowledge_graph_edges: knowledgeEdges,
    argument_template_nodes: argumentNodes,
    model_routes: routeCards,
    model_status: modelText,
    media_capabilities: mediaCapabilities,
    media_available_capabilities: availableCapabilities,
    media_proof_rows: mediaProofRows,
    iflytek_round_trip: roundTripStatus,
    media_status: mediaStatus,
    private_leaks: privateLeaks,
    console_errors: consoleErrors,
    page_errors: pageErrors,
    http_errors: httpErrors,
    request_failures: requestFailures,
    artifact_dir: publicArtifactDir,
  };
  fs.writeFileSync(
    path.join(artifactDir, "report.json"),
    `${JSON.stringify({ generated_at: new Date().toISOString(), ...result }, null, 2)}\n`,
    "utf8",
  );
  console.log(JSON.stringify(result));
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
