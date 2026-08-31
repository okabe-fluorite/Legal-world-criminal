/** Record the verified iFlytek TTS -> IAT UI journey without login footage. */

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
const outputDir = path.resolve(
  process.env.IFLYTEK_VIDEO_CAPTURE_DIR
    || path.join(repo, "competition_submission", "offline_backup", "iflytek-video-capture"),
);
const publicAudit = path.resolve(
  process.env.IFLYTEK_VIDEO_PUBLIC_AUDIT
    || path.join(
      repo,
      "competition_submission",
      "03-Demo",
      "IFLYTEK_BROWSER_VIDEO_SEGMENT_AUDIT.json",
    ),
);
const viewport = { width: 1600, height: 900 };
const ffmpeg = process.env.DEMO_FFMPEG || "ffmpeg";
const ffprobe = process.env.DEMO_FFPROBE || "ffprobe";

function relativeInsideRepo(value, label) {
  const relative = path.relative(repo, value).split(path.sep).join("/");
  if (!relative || relative.startsWith("../")) {
    throw new Error(`${label} must stay inside the repository`);
  }
  return relative;
}

const relativeOutput = relativeInsideRepo(outputDir, "capture output");
const relativeAudit = relativeInsideRepo(publicAudit, "public audit");
if (fs.existsSync(outputDir) && fs.readdirSync(outputDir).length) {
  throw new Error(`capture output must be empty: ${relativeOutput}`);
}
fs.mkdirSync(outputDir, { recursive: true });
fs.mkdirSync(path.dirname(publicAudit), { recursive: true });

const candidates = [
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
].filter(Boolean);
const executablePath = candidates.find((candidate) => fs.existsSync(candidate));
if (!executablePath) throw new Error("No installed Chromium browser found");

function run(command, args) {
  const result = spawnSync(command, args, { encoding: "utf8" });
  if (result.status !== 0) {
    throw new Error(`${command} failed: ${result.stderr || result.stdout || result.status}`);
  }
  return result.stdout;
}

function sha256(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

async function addLabel(page) {
  await page.evaluate(() => {
    const label = document.createElement("div");
    label.id = "competition-record-label";
    label.setAttribute("aria-hidden", "true");
    label.style.cssText = [
      "position:fixed", "top:14px", "right:18px", "z-index:2147483647",
      "background:#002FA7", "color:#fff", "padding:10px 14px", "max-width:500px",
      "font:600 14px/1.35 'Microsoft YaHei UI',sans-serif", "letter-spacing:.03em",
      "border:1px solid rgba(255,255,255,.55)", "border-radius:0", "pointer-events:none",
    ].join(";");
    label.innerHTML = [
      "<div>实时操作 · 讯飞ASR/TTS</div>",
      "<div style=\"font-weight:400;opacity:.84;margin-top:2px\">合成验收句 · 非课堂数据 · 数字人后置</div>",
    ].join("");
    document.body.appendChild(label);
  });
}

const browser = await chromium.launch({ executablePath, headless: true });
const context = await browser.newContext({
  viewport,
  recordVideo: { dir: outputDir, size: viewport },
});
const recordStartedAt = Date.now();
const page = await context.newPage();
const errors = { console: [], page: [], http: [], request: [] };
page.on("console", (message) => {
  if (message.type() === "error") errors.console.push(message.text());
});
page.on("pageerror", (error) => errors.page.push(error.message));
page.on("response", (response) => {
  if (response.status() >= 400) errors.http.push(`${response.status()} ${response.url()}`);
});
page.on("requestfailed", (request) => {
  if (request.url().startsWith("blob:")) return;
  errors.request.push(`${request.url()} ${request.failure()?.errorText || "failed"}`);
});

let rawVideo;
try {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const stamp = Date.now();
  const authResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/auth/register"),
    { timeout: 120000 },
  );
  const sandboxResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/sandbox/ensure"),
    { timeout: 120000 },
  );
  await page.getByPlaceholder("you@court.edu").fill(`iflytek-video-${stamp}@example.com`);
  await page.getByPlaceholder("至少 6 位").fill(`Iflytek-Video-${stamp}!`);
  await page.getByRole("button", { name: "注册并进入" }).click();
  const [auth, sandbox] = await Promise.all([authResponse, sandboxResponse]);
  if (auth.status() !== 200 || sandbox.status() !== 200) {
    throw new Error(`registration bootstrap failed: ${auth.status()}/${sandbox.status()}`);
  }
  await page.locator(".case__version").first().waitFor({ timeout: 60000 });
  const trimSeconds = (Date.now() - recordStartedAt) / 1000 + 0.45;

  await addLabel(page);
  await page.waitForTimeout(600);
  await page.getByRole("button", { name: "认知诊断" }).click();
  await page.getByRole("dialog", { name: "认知诊断与个性化路径驾驶舱" }).waitFor();
  await page.getByRole("button", { name: "多模态 / 数字人" }).click();
  await page.getByText("多模态与数字人能力总线", { exact: true }).waitFor();
  await page.waitForTimeout(1300);

  await page.getByRole("button", { name: "生成讯飞WAV" }).click();
  await page.getByText(/讯飞TTS真实生成/).waitFor({ timeout: 60000 });
  const audio = page.locator("audio[aria-label='讯飞AI合成音频']");
  await audio.waitFor();
  const audioDuration = await audio.evaluate((element) => element.duration);
  await page.waitForTimeout(2200);

  await page.getByRole("button", { name: "将WAV送入ASR" }).click();
  await page.getByText(/讯飞ASR已返回真实转写/).waitFor({ timeout: 60000 });
  const roundTripText = await page.locator(".media-result").innerText();
  await page.waitForTimeout(3300);

  const capabilities = await page.locator(".media-capability-grid article.ready").count();
  await page.getByRole("button", { name: "调用预留接口验证状态" }).click();
  await page.getByText(/数字人异步契约已真实调用/).waitFor();
  const avatarText = await page.locator(".media-result").innerText();
  await page.waitForTimeout(2500);

  if (
    capabilities !== 3
    || !roundTripText.includes("iflytek_websocket")
    || !roundTripText.includes("needs_review")
    || !roundTripText.includes("罪刑法定")
    || !avatarText.includes("not_connected")
  ) {
    throw new Error("iFlytek video journey did not expose all required states");
  }

  const video = page.video();
  await context.close();
  rawVideo = await video.path();
  const target = path.join(outputDir, "iflytek-tts-iat.webm");
  run(ffmpeg, [
    "-loglevel", "error", "-y", "-ss", trimSeconds.toFixed(3), "-i", rawVideo,
    "-an", "-c:v", "libvpx-vp9", "-crf", "27", "-b:v", "0", target,
  ]);
  fs.rmSync(rawVideo, { force: true });
  rawVideo = undefined;

  const metadata = JSON.parse(run(ffprobe, [
    "-v", "error", "-show_entries",
    "format=duration,size:stream=codec_name,width,height,avg_frame_rate",
    "-of", "json", target,
  ]));
  const stream = metadata.streams[0];
  const errorCounts = Object.fromEntries(
    Object.entries(errors).map(([key, values]) => [key, values.length]),
  );
  const sourceCommit = run("git", ["-C", repo, "rev-parse", "HEAD"]).trim();
  const audit = {
    schema: "competition-iflytek-browser-video-segment-audit-v1",
    source_git_commit: sourceCommit,
    file: path.basename(target),
    duration_seconds: Number(Number(metadata.format.duration).toFixed(3)),
    bytes: fs.statSync(target).size,
    sha256: sha256(target),
    media: {
      codec: stream.codec_name,
      resolution: `${stream.width}x${stream.height}`,
      fps: stream.avg_frame_rate,
      audio: false,
    },
    visible_checks: {
      available_capabilities: capabilities,
      tts_private_audio_player: true,
      tts_audio_duration_seconds: Number.isFinite(audioDuration)
        ? Number(audioDuration.toFixed(3))
        : null,
      asr_provider: "iflytek_websocket",
      asr_status: "needs_review",
      asr_transcript_contains_legal_term: roundTripText.includes("罪刑法定"),
      digital_human_status: "not_connected",
      learning_event_created: false,
    },
    browser_error_counts: errorCounts,
    qa: {
      browser_error_total: Object.values(errorCounts).reduce((sum, value) => sum + value, 0),
      login_prefix_removed_by_reencode: true,
      raw_recording_deleted: true,
      synthetic_account_only: true,
      credential_or_token_published: false,
    },
    evidence_boundary: (
      "real product UI calling iFlytek TTS and IAT with a synthetic verification sentence; "
      + "not classroom data, not ASR accuracy evidence, and not digital-human completion"
    ),
  };
  fs.writeFileSync(
    path.join(outputDir, "segment-private-manifest.json"),
    `${JSON.stringify({ ...audit, browser_errors: errors }, null, 2)}\n`,
    "utf8",
  );
  fs.writeFileSync(publicAudit, `${JSON.stringify(audit, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ ...audit, public_audit: relativeAudit }, null, 2));
  if (audit.qa.browser_error_total) process.exitCode = 2;
} finally {
  if (rawVideo) fs.rmSync(rawVideo, { force: true });
  await context.close().catch(() => undefined);
  for (const name of fs.readdirSync(outputDir)) {
    if (/^page@.+\.webm$/u.test(name)) {
      fs.rmSync(path.join(outputDir, name), { force: true });
    }
  }
  await browser.close();
}
