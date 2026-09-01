import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright-core";

const baseUrl = process.env.EVIDENCE_VOICE_BASE_URL || "http://127.0.0.1:5173";
const audioFixture = path.resolve(process.env.EVIDENCE_VOICE_AUDIO || "../competition_submission/03-Demo/iflytek-speech/iflytek-tts-verification.wav");
const artifactDir = path.resolve(process.env.EVIDENCE_VOICE_ARTIFACT_DIR || "../.codex-artifacts/evidence-citations-voice");
const candidates = [
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
].filter(Boolean);
const executablePath = candidates.find((candidate) => fs.existsSync(candidate));
if (!executablePath || !fs.existsSync(audioFixture)) throw new Error("Browser or microphone fixture missing");
fs.mkdirSync(artifactDir, { recursive: true });

const browser = await chromium.launch({
  executablePath,
  headless: true,
  args: [
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
    `--use-file-for-fake-audio-capture=${audioFixture}`,
    "--autoplay-policy=no-user-gesture-required",
  ],
});
const page = await browser.newPage({ viewport: { width: 1500, height: 980 } });
const errors = { console: [], page: [], http: [], request: [] };
const received = [];
const sent = [];
const fileUploads = [];
page.on("console", (message) => { if (message.type() === "error") errors.console.push(message.text()); });
page.on("pageerror", (error) => errors.page.push(error.message));
page.on("response", (response) => { if (response.status() >= 400) errors.http.push(`${response.status()} ${response.url()}`); });
page.on("requestfailed", (request) => { if (!request.url().startsWith("blob:")) errors.request.push(`${request.url()} ${request.failure()?.errorText || "failed"}`); });
page.on("request", (request) => { if (request.method() === "POST" && request.url().includes("/api/multimodal/assets")) fileUploads.push(request.url()); });
page.on("websocket", (socket) => {
  if (!socket.url().includes("/ws/realtime-voice")) return;
  socket.on("framesent", (event) => { if (typeof event.payload === "string") { try { sent.push(JSON.parse(event.payload)); } catch { /* audited below */ } } });
  socket.on("framereceived", (event) => { if (typeof event.payload === "string") { try { const row = JSON.parse(event.payload); received.push({ type: row.type, voice: row.audio?.voice || "", preferred: row.audio?.preferred_voice_used, evidence_count: row.evidences?.length || 0 }); } catch { /* audited below */ } } });
});

async function timelineCount() {
  return page.evaluate(async () => {
    const token = localStorage.getItem("lw.token");
    const response = await fetch("/api/adaptive/evidence-timeline", { headers: { Authorization: `Bearer ${token}` } });
    return (await response.json()).events.length;
  });
}

try {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.getByPlaceholder("you@court.edu").fill(`evidence-voice-${Date.now()}@example.com`);
  await page.getByPlaceholder("至少 6 位").fill("Evidence-Voice-2026!");
  await page.getByRole("button", { name: "注册并进入" }).click();
  await page.locator(".case__version").first().waitFor({ timeout: 60000 });
  const beforeEvents = await timelineCount();

  await page.getByRole("button", { name: "可信RAG" }).click();
  await page.getByRole("dialog", { name: "可信RAG与三个典型问题验证" }).waitFor();
  await page.locator(".question-list button").nth(1).click();
  const marks = page.locator(".ai-answer .citation-mark");
  await marks.first().waitFor();
  const ragCitationMarks = await marks.count();
  if (ragCitationMarks < 2) throw new Error("Special-defense answer must expose law and case citations");
  await marks.first().hover();
  const tooltip = page.locator(".evidence-tooltip");
  await tooltip.waitFor();
  const tooltipText = await tooltip.innerText();
  if (!tooltipText.includes("点击展开完整证据") || tooltipText.length > 240) throw new Error(`Citation tooltip is not concise: ${tooltipText}`);
  await marks.nth(1).click();
  const drawer = page.getByRole("dialog", { name: /指导案例144号/ });
  await drawer.waitFor();
  const drawerText = await drawer.innerText();
  if (!drawerText.includes("FULL GOVERNED EXCERPT") || !drawerText.includes("Evidence ID") || !drawerText.includes("检索相关不等于法律蕴含")) throw new Error("Evidence drawer governance fields missing");
  const originalLink = drawer.getByRole("link", { name: /打开原始来源/ });
  const originalHref = await originalLink.getAttribute("href");
  if (!originalHref?.startsWith("https://")) throw new Error("Case source link missing");
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(artifactDir, "01-case-evidence-drawer.png") });
  await drawer.getByRole("button", { name: "关闭完整证据" }).click();
  await page.getByRole("button", { name: "关闭可信RAG验证" }).click();

  await page.getByRole("button", { name: "认知诊断" }).click();
  await page.getByRole("button", { name: "多模态 / 数字人" }).click();
  const voice = page.locator(".voice-console");
  await voice.getByText(/ASR 已配置 · 待本轮握手|ASR 已连接/, { exact: true }).waitFor();
  await voice.getByText(/TTS 已配置 · 待首轮合成|TTS 已连接 · 小露女声/, { exact: true }).waitFor();
  const initialAsrText = await voice.locator(".voice-health > span").first().innerText();
  const initialTtsText = await voice.locator(".voice-health > span").nth(1).innerText();
  await voice.getByRole("button", { name: "● 开始实时提问" }).click();
  await voice.getByText("ASR 已连接", { exact: true }).waitFor({ timeout: 30000 });
  await voice.getByText(/麦克风权限 granted/).waitFor({ timeout: 30000 });
  await voice.getByText(/正在聆听/).waitFor({ timeout: 30000 });
  await page.waitForFunction(() => {
    const level = document.querySelector(".voice-console .input-level i");
    const width = Number.parseFloat(level?.style.width || "0");
    const device = document.querySelector(".voice-health strong")?.textContent || "";
    return width > 0 && !device.includes("尚未授权");
  }, undefined, { timeout: 30000 });
  await voice.locator(".voice-turn .partial").waitFor({ timeout: 30000 });
  await page.waitForTimeout(6800);
  await voice.getByRole("button", { name: "■ 结束本轮并发送" }).click();
  await voice.locator("audio[aria-label='讯飞AI形成性回复音频']").waitFor({ timeout: 240000 });
  await voice.getByText("TTS 已连接 · 小露女声", { exact: true }).waitFor({ timeout: 30000 });
  await voice.getByText(/x4_yezi（小露女声）/).waitFor();
  const voiceCitation = voice.locator(".citation-mark").first();
  await voiceCitation.click();
  await page.locator(".evidence-drawer").waitFor();
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(artifactDir, "02-voice-evidence-natural-tts.png") });
  const afterEvents = await timelineCount();

  const count = (rows, type) => rows.filter((row) => row.type === type).length;
  const reply = received.find((row) => row.type === "voice_reply");
  const report = {
    rag_citation_marks: ragCitationMarks,
    rag_tooltip_concise: true,
    rag_case_drawer_complete: true,
    case_source_href_present: true,
    asr_initial_status: initialAsrText,
    tts_initial_status: initialTtsText,
    asr_after_handshake: "available",
    microphone_level_observed: true,
    microphone_device_visible: true,
    sent_pcm_frames: count(sent, "voice_audio"),
    partial_results: count(received, "voice_transcript_partial"),
    final_results: count(received, "voice_transcript_final"),
    tts_voice: reply?.voice,
    preferred_voice_used: reply?.preferred,
    reply_evidence_count: reply?.evidence_count,
    file_upload_requests: fileUploads.length,
    learning_event_before: beforeEvents,
    learning_event_after: afterEvents,
    errors,
  };
  if (report.sent_pcm_frames < 100 || report.partial_results < 1 || report.final_results !== 1 || report.tts_voice !== "x4_yezi" || report.preferred_voice_used !== true || report.reply_evidence_count < 1 || report.file_upload_requests || beforeEvents !== afterEvents || Object.values(errors).some((rows) => rows.length)) throw new Error(`Integrated evidence/voice gate failed: ${JSON.stringify(report)}`);
  fs.writeFileSync(path.join(artifactDir, "report.json"), `${JSON.stringify({ generated_at: new Date().toISOString(), ...report }, null, 2)}\n`);
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
}
