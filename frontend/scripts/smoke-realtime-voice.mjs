import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright-core";

const baseUrl = process.env.REALTIME_VOICE_BASE_URL || "http://127.0.0.1:5173";
const audioFixture = path.resolve(
  process.env.REALTIME_VOICE_AUDIO
    || "../competition_submission/03-Demo/iflytek-speech/iflytek-tts-verification.wav",
);
const artifactDir = path.resolve(
  process.env.REALTIME_VOICE_ARTIFACT_DIR
    || "../.codex-artifacts/realtime-voice",
);
const roundCount = Number(process.env.REALTIME_VOICE_ROUNDS || 2);
const viewport = {
  width: Number(process.env.REALTIME_VOICE_VIEWPORT_WIDTH || 1500),
  height: Number(process.env.REALTIME_VOICE_VIEWPORT_HEIGHT || 980),
};
if (!Number.isInteger(roundCount) || roundCount < 1 || roundCount > 3) {
  throw new Error(`REALTIME_VOICE_ROUNDS must be 1-3, received ${roundCount}`);
}
const repoRoot = path.resolve("..");
const publicArtifactDir = path.relative(repoRoot, artifactDir).split(path.sep).join("/");
if (!publicArtifactDir || publicArtifactDir.startsWith("../")) {
  throw new Error("Realtime voice artifacts must stay inside the repository");
}
if (!fs.existsSync(audioFixture)) throw new Error(`Audio fixture not found: ${audioFixture}`);

const executableCandidates = [
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean);
const executablePath = executableCandidates.find((candidate) => fs.existsSync(candidate));
if (!executablePath) throw new Error("No installed Chromium browser found");

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
const page = await browser.newPage({ viewport });
const consoleErrors = [];
const pageErrors = [];
const httpErrors = [];
const requestFailures = [];
const voiceFrames = [];

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
page.on("websocket", (socket) => {
  if (!socket.url().includes("/ws/realtime-voice")) return;
  socket.on("framereceived", (event) => {
    if (typeof event.payload !== "string") return;
    try {
      const message = JSON.parse(event.payload);
      voiceFrames.push({
        type: message.type,
        turn_id: message.turn_id || "",
        transcript: message.transcript || "",
        reply_text: message.reply_text || "",
        source: message.source || "",
        coverage_status: message.coverage_status || "",
        audio: message.audio ? {
          size_bytes: message.audio.size_bytes,
          sha256: message.audio.sha256,
          duration_seconds: message.audio.duration_seconds,
          ai_generated_disclosure: message.audio.ai_generated_disclosure,
        } : null,
        evidence_eligibility: message.evidence_eligibility || null,
        code: message.code || "",
      });
    } catch {
      voiceFrames.push({ type: "invalid_json_frame" });
    }
  });
});

async function timelineCount() {
  return page.evaluate(async () => {
    const token = localStorage.getItem("lw.token");
    const response = await fetch("/api/adaptive/evidence-timeline", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) throw new Error(`timeline ${response.status}`);
    const payload = await response.json();
    return Array.isArray(payload.events) ? payload.events.length : -1;
  });
}

try {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const email = `realtime-voice-${Date.now()}@example.com`;
  await page.getByPlaceholder("you@court.edu").fill(email);
  await page.getByPlaceholder("至少 6 位").fill("Realtime-Voice-2026!");
  await page.getByRole("button", { name: "注册并进入" }).click();
  await page.locator(".case__version").first().waitFor({ timeout: 60000 });
  const beforeEvents = await timelineCount();

  await page.getByRole("button", { name: "认知诊断" }).click();
  await page.getByRole("dialog", { name: "认知诊断与个性化路径驾驶舱" }).waitFor();
  await page.getByRole("button", { name: "多模态 / 数字人" }).click();
  await page.getByText("实时语音多模态与数字人边界", { exact: true }).waitFor();
  const voicePanel = page.locator(".voice-console");
  await voicePanel.waitFor();

  for (let index = 1; index <= roundCount; index += 1) {
    await voicePanel.getByRole("button", { name: "● 开始实时提问" }).click();
    await voicePanel.getByText(/正在聆听/).waitFor({ timeout: 30000 });
    const partialBefore = voiceFrames.filter((row) => row.type === "voice_transcript_partial").length;
    await page.waitForFunction(
      ({ count }) => {
        const partial = document.querySelector(".voice-turn .partial");
        return Boolean(partial?.textContent?.trim()) || count < 0;
      },
      { count: partialBefore },
      { timeout: 30000 },
    );
    await page.waitForTimeout(6800);
    await voicePanel.getByRole("button", { name: "■ 结束本轮并发送" }).click();
    await voicePanel.locator("audio[aria-label='讯飞AI形成性回复音频']").waitFor({ timeout: 240000 });
    await voicePanel.locator(".voice-runtime strong").getByText("AI语音播放中", { exact: true }).waitFor({ timeout: 30000 });
    const completedText = await voicePanel.locator(".voice-runtime").innerText();
    if (!completedText.includes(`${index}轮已完成`)) {
      throw new Error(`Round ${index} completion counter mismatch: ${completedText}`);
    }
    if (index < roundCount) {
      await page.waitForFunction(
        () => {
          const audio = document.querySelector(".voice-console audio");
          return audio instanceof HTMLAudioElement && audio.ended;
        },
        undefined,
        { timeout: 120000 },
      );
      await voicePanel.getByRole("button", { name: "● 开始实时提问" }).waitFor();
    } else {
      await page.waitForFunction(
        () => {
          const audio = document.querySelector(".voice-console audio");
          return audio instanceof HTMLAudioElement && audio.currentTime > 0.5;
        },
        undefined,
        { timeout: 30000 },
      );
    }
  }

  const afterEvents = await timelineCount();
  const typeCounts = Object.fromEntries(
    [...new Set(voiceFrames.map((row) => row.type))]
      .sort()
      .map((type) => [type, voiceFrames.filter((row) => row.type === type).length]),
  );
  const replies = voiceFrames.filter((row) => row.type === "voice_reply");
  const finals = voiceFrames.filter((row) => row.type === "voice_transcript_final");
  const partials = voiceFrames.filter((row) => row.type === "voice_transcript_partial");
  const errors = voiceFrames.filter((row) => row.type === "voice_error");
  if (replies.length !== roundCount || finals.length !== roundCount || partials.length < roundCount || errors.length) {
    throw new Error(`Realtime protocol incomplete: ${JSON.stringify(typeCounts)}`);
  }
  if (beforeEvents !== afterEvents) {
    throw new Error(`Realtime voice changed LearningEvent timeline: ${beforeEvents} -> ${afterEvents}`);
  }
  if (replies.some((row) => !row.audio?.ai_generated_disclosure || !row.audio?.size_bytes)) {
    throw new Error("TTS audio proof or AI disclosure missing");
  }
  if (replies.some((row) => row.evidence_eligibility?.learning_event_created !== false)) {
    throw new Error("Realtime reply did not preserve LearningEvent=0 boundary");
  }
  const transcriptText = finals.map((row) => row.transcript).join("\n");
  if (!transcriptText.includes("罪刑法定")) {
    throw new Error(`Legal phrase missing from final transcripts: ${transcriptText}`);
  }
  await page.waitForFunction(
    () => document.querySelectorAll(".media-capability-grid article.ready").length >= 3,
    undefined,
    { timeout: 30000 },
  );
  const availableCapabilities = await page.locator(".media-capability-grid article.ready").count();

  await voicePanel.screenshot({ path: path.join(artifactDir, "01-realtime-voice-two-rounds.png") });
  const visibleText = await voicePanel.innerText();
  const privateLeaks = ["api_key", "api_secret", "authorization=", "storage_root", "Bearer "]
    .filter((value) => visibleText.includes(value));
  const result = {
    viewport: `${viewport.width}x${viewport.height}`,
    rounds: roundCount,
    type_counts: typeCounts,
    final_transcripts: finals.map((row) => row.transcript),
    reply_sources: replies.map((row) => row.source),
    coverage_statuses: replies.map((row) => row.coverage_status),
    tts_audio: replies.map((row) => row.audio),
    learning_event_timeline_before: beforeEvents,
    learning_event_timeline_after: afterEvents,
    available_capabilities_after_live_voice: availableCapabilities,
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
  ) process.exitCode = 1;
} catch (error) {
  console.error(JSON.stringify({
    smoke_error: error instanceof Error ? error.message : String(error),
    url: page.url(),
    voice_frames: voiceFrames.map((row) => ({ type: row.type, code: row.code || "" })),
    console_errors: consoleErrors,
    page_errors: pageErrors,
    http_errors: httpErrors,
    request_failures: requestFailures,
  }));
  throw error;
} finally {
  await browser.close();
}
