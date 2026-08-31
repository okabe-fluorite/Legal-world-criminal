/** Record a real browser microphone-stream → iFlytek IAT → Evidence → TTS turn. */

import crypto from "node:crypto";
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
const baseUrl = process.env.IFLYTEK_VIDEO_BASE_URL || "http://127.0.0.1:5173";
const outputDir = path.resolve(process.env.IFLYTEK_VIDEO_CAPTURE_DIR || path.join(repo, "competition_submission", "offline_backup", "iflytek-realtime-video-capture"));
const publicAudit = path.resolve(process.env.IFLYTEK_VIDEO_PUBLIC_AUDIT || path.join(repo, "competition_submission", "03-Demo", "IFLYTEK_BROWSER_VIDEO_SEGMENT_AUDIT.json"));
const audioFixture = path.resolve(process.env.IFLYTEK_VIDEO_AUDIO || path.join(repo, "competition_submission", "03-Demo", "iflytek-speech", "iflytek-tts-verification.wav"));
const viewport = { width: 1600, height: 900 };
const ffmpeg = process.env.DEMO_FFMPEG || "ffmpeg";
const ffprobe = process.env.DEMO_FFPROBE || "ffprobe";

function relativeInsideRepo(value, label) {
  const relative = path.relative(repo, value).split(path.sep).join("/");
  if (!relative || relative.startsWith("../")) throw new Error(`${label} must stay inside the repository`);
  return relative;
}
function run(command, args) {
  const result = spawnSync(command, args, { encoding: "utf8" });
  if (result.status !== 0) throw new Error(`${command} failed: ${result.stderr || result.stdout || result.status}`);
  return result.stdout;
}
function sha256(file) { return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex"); }

const relativeOutput = relativeInsideRepo(outputDir, "capture output");
const relativeAudit = relativeInsideRepo(publicAudit, "public audit");
if (!fs.existsSync(audioFixture) || !fs.statSync(audioFixture).isFile()) throw new Error("realtime microphone fixture is missing");
if (fs.existsSync(outputDir) && fs.readdirSync(outputDir).length) throw new Error(`capture output must be empty: ${relativeOutput}`);
fs.mkdirSync(outputDir, { recursive: true });
fs.mkdirSync(path.dirname(publicAudit), { recursive: true });
const candidates = [process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe", "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"].filter(Boolean);
const executablePath = candidates.find((candidate) => fs.existsSync(candidate));
if (!executablePath) throw new Error("No installed Chromium browser found");

async function addLabel(page) {
  await page.evaluate(() => {
    const label = document.createElement("div");
    label.id = "competition-record-label";
    label.setAttribute("aria-hidden", "true");
    label.style.cssText = ["position:fixed", "top:14px", "right:18px", "z-index:2147483647", "background:#002FA7", "color:#fff", "padding:10px 14px", "max-width:520px", "font:600 14px/1.35 'Microsoft YaHei UI',sans-serif", "letter-spacing:.03em", "border:1px solid rgba(255,255,255,.55)", "border-radius:0", "pointer-events:none"].join(";");
    label.innerHTML = "<div>实时操作 · 浏览器麦克风 → 讯飞IAT/TTS</div><div style=\"font-weight:400;opacity:.84;margin-top:2px\">PCM持续分片 · ASR需复核 · LearningEvent 0</div>";
    document.body.appendChild(label);
  });
}

const browser = await chromium.launch({ executablePath, headless: true, args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", `--use-file-for-fake-audio-capture=${audioFixture}`, "--autoplay-policy=no-user-gesture-required"] });
const context = await browser.newContext({ viewport, recordVideo: { dir: outputDir, size: viewport } });
const recordStartedAt = Date.now();
const page = await context.newPage();
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
  socket.on("framesent", (event) => { if (typeof event.payload === "string") { try { sent.push(JSON.parse(event.payload)); } catch { sent.push({ type: "invalid_json" }); } } });
  socket.on("framereceived", (event) => {
    if (typeof event.payload !== "string") return;
    try {
      const message = JSON.parse(event.payload);
      received.push({ type: message.type, transcript: message.transcript || "", reply_text: message.reply_text || "", source: message.source || "", coverage_status: message.coverage_status || "", audio: message.audio ? { size_bytes: message.audio.size_bytes, duration_seconds: message.audio.duration_seconds, ai_generated_disclosure: message.audio.ai_generated_disclosure } : null, eligibility: message.evidence_eligibility || null });
    } catch { received.push({ type: "invalid_json" }); }
  });
});

async function timelineCount() {
  return page.evaluate(async () => {
    const token = localStorage.getItem("lw.token");
    const response = await fetch("/api/adaptive/evidence-timeline", { headers: { Authorization: `Bearer ${token}` } });
    return (await response.json()).events.length;
  });
}

let rawVideo;
try {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const stamp = Date.now();
  const authResponse = page.waitForResponse((response) => response.url().endsWith("/api/auth/register"), { timeout: 120000 });
  const sandboxResponse = page.waitForResponse((response) => response.url().endsWith("/api/sandbox/ensure"), { timeout: 120000 });
  await page.getByPlaceholder("you@court.edu").fill(`iflytek-realtime-${stamp}@example.com`);
  await page.getByPlaceholder("至少 6 位").fill(`Iflytek-Realtime-${stamp}!`);
  await page.getByRole("button", { name: "注册并进入" }).click();
  const [auth, sandbox] = await Promise.all([authResponse, sandboxResponse]);
  if (auth.status() !== 200 || sandbox.status() !== 200) throw new Error(`registration failed: ${auth.status()}/${sandbox.status()}`);
  await page.locator(".case__version").first().waitFor({ timeout: 60000 });
  const trimSeconds = (Date.now() - recordStartedAt) / 1000 + 0.4;
  await addLabel(page);
  await page.getByRole("button", { name: "认知诊断" }).click();
  await page.getByRole("dialog", { name: "认知诊断与个性化路径驾驶舱" }).waitFor();
  await page.getByRole("button", { name: "多模态 / 数字人" }).click();
  await page.getByText("实时语音多模态与数字人边界", { exact: true }).waitFor();
  const timelineBefore = await timelineCount();
  const voicePanel = page.locator(".voice-console");
  await voicePanel.getByRole("button", { name: "● 开始实时提问" }).click();
  await voicePanel.getByText(/正在聆听/).waitFor({ timeout: 30000 });
  await voicePanel.locator(".voice-turn .partial").waitFor({ timeout: 30000 });
  await page.waitForTimeout(6500);
  await voicePanel.getByRole("button", { name: "■ 结束本轮并发送" }).click();
  await voicePanel.locator("audio[aria-label='讯飞AI形成性回复音频']").waitFor({ timeout: 240000 });
  await voicePanel.locator(".voice-runtime strong").getByText("AI语音播放中", { exact: true }).waitFor({ timeout: 30000 });
  await page.waitForTimeout(3500);
  const timelineAfter = await timelineCount();
  const capabilities = await page.locator(".media-capability-grid article.ready").count();
  const digitalHumanText = await page.locator(".media-capability-grid article").filter({ hasText: "digital_human" }).innerText();
  const count = (rows, type) => rows.filter((row) => row.type === type).length;
  const final = received.find((row) => row.type === "voice_transcript_final");
  const reply = received.find((row) => row.type === "voice_reply");
  const visibleChecks = {
    browser_voice_start: count(sent, "voice_start"), browser_pcm_frames: count(sent, "voice_audio"), browser_voice_stop: count(sent, "voice_stop"), file_upload_requests: fileUploads.length,
    partial_results: count(received, "voice_transcript_partial"), final_results: count(received, "voice_transcript_final"), final_transcript_contains_legal_term: String(final?.transcript || "").includes("罪刑法定"),
    governed_reply_results: count(received, "voice_reply"), governed_reply_source: reply?.source || "", coverage_status: reply?.coverage_status || "", tts_audio_player: true,
    tts_audio_bytes: Number(reply?.audio?.size_bytes || 0), tts_audio_duration_seconds: Number(reply?.audio?.duration_seconds || 0), ai_generated_disclosure: reply?.audio?.ai_generated_disclosure === true,
    available_capabilities: capabilities, asr_status: "needs_review", digital_human_status: digitalHumanText.includes("not_connected") ? "not_connected" : "unknown",
    learning_event_before: timelineBefore, learning_event_after: timelineAfter, learning_event_created: timelineBefore !== timelineAfter,
  };
  if (visibleChecks.browser_voice_start !== 1 || visibleChecks.browser_pcm_frames < 100 || visibleChecks.browser_voice_stop !== 1 || visibleChecks.file_upload_requests !== 0 || visibleChecks.partial_results < 1 || visibleChecks.final_results !== 1 || !visibleChecks.final_transcript_contains_legal_term || visibleChecks.governed_reply_results !== 1 || visibleChecks.governed_reply_source !== "llm_governed_evidence" || !visibleChecks.tts_audio_bytes || visibleChecks.available_capabilities !== 3 || visibleChecks.digital_human_status !== "not_connected" || visibleChecks.learning_event_created) throw new Error(`realtime voice capture gate failed: ${JSON.stringify(visibleChecks)}`);

  const video = page.video();
  await context.close();
  rawVideo = await video.path();
  const target = path.join(outputDir, "iflytek-realtime-voice.webm");
  run(ffmpeg, ["-loglevel", "error", "-y", "-ss", trimSeconds.toFixed(3), "-i", rawVideo, "-an", "-c:v", "libvpx-vp9", "-crf", "27", "-b:v", "0", target]);
  fs.rmSync(rawVideo, { force: true });
  rawVideo = undefined;
  const metadata = JSON.parse(run(ffprobe, ["-v", "error", "-show_entries", "format=duration,size:stream=codec_name,width,height,avg_frame_rate", "-of", "json", target]));
  const stream = metadata.streams[0];
  const errorCounts = Object.fromEntries(Object.entries(errors).map(([key, values]) => [key, values.length]));
  const audit = {
    schema: "competition-iflytek-realtime-voice-video-segment-audit-v2", source_git_commit: run("git", ["-C", repo, "rev-parse", "HEAD"]).trim(), file: path.basename(target),
    duration_seconds: Number(Number(metadata.format.duration).toFixed(3)), bytes: fs.statSync(target).size, sha256: sha256(target), media: { codec: stream.codec_name, resolution: `${stream.width}x${stream.height}`, fps: stream.avg_frame_rate, audio: false },
    visible_checks: visibleChecks, browser_error_counts: errorCounts,
    qa: { browser_error_total: Object.values(errorCounts).reduce((sum, value) => sum + value, 0), login_prefix_removed_by_reencode: true, raw_recording_deleted: true, synthetic_account_only: true, credential_or_token_published: false, microphone_fixture_uses_realtime_browser_media_clock: true, student_raw_microphone_audio_published: false },
    evidence_boundary: "real browser media stream sends PCM frames to iFlytek streaming IAT, then governed Evidence reply and iFlytek TTS; the deterministic audio fixture verifies protocol timing, not multi-speaker classroom ASR accuracy; digital human remains not_connected",
  };
  fs.writeFileSync(path.join(outputDir, "segment-private-manifest.json"), `${JSON.stringify({ ...audit, browser_errors: errors }, null, 2)}\n`, "utf8");
  fs.writeFileSync(publicAudit, `${JSON.stringify(audit, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ ...audit, public_audit: relativeAudit }, null, 2));
  if (audit.qa.browser_error_total) process.exitCode = 2;
} finally {
  if (rawVideo) fs.rmSync(rawVideo, { force: true });
  await context.close().catch(() => undefined);
  for (const name of fs.readdirSync(outputDir)) if (/^page@.+\.webm$/u.test(name)) fs.rmSync(path.join(outputDir, name), { force: true });
  await browser.close();
}
