/** Record a credential-free technical-evidence segment for the competition video.
 *
 * Registration happens before the retained clip. FFmpeg trims that prefix and
 * the raw Playwright video is deleted. The public audit contains counts and
 * hashes only; no synthetic account, token, absolute path, or response body.
 */

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

const baseUrl = process.env.TECH_VIDEO_BASE_URL || "http://127.0.0.1:5173";
const outputDir = path.resolve(
  process.env.TECH_VIDEO_CAPTURE_DIR
    || path.join(repo, "competition_submission", "offline_backup", "technical-evidence-capture"),
);
const publicAudit = path.resolve(
  process.env.TECH_VIDEO_PUBLIC_AUDIT
    || path.join(
      repo,
      "competition_submission",
      "03-Demo",
      "TECHNICAL_EVIDENCE_VIDEO_SEGMENT_AUDIT.json",
    ),
);
const viewport = { width: 1600, height: 900 };
const ffmpeg = process.env.DEMO_FFMPEG || "ffmpeg";
const ffprobe = process.env.DEMO_FFPROBE || "ffprobe";

const relativeOutput = path.relative(repo, outputDir).split(path.sep).join("/");
const relativeAudit = path.relative(repo, publicAudit).split(path.sep).join("/");
if (!relativeOutput || relativeOutput.startsWith("../")) {
  throw new Error("capture output must stay inside the repository");
}
if (!relativeAudit || relativeAudit.startsWith("../")) {
  throw new Error("public audit must stay inside the repository");
}
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
    document.getElementById("competition-record-label")?.remove();
    const label = document.createElement("div");
    label.id = "competition-record-label";
    label.setAttribute("aria-hidden", "true");
    label.style.cssText = [
      "position:fixed", "top:14px", "right:18px", "z-index:2147483647",
      "background:#002FA7", "color:#fff", "padding:10px 14px", "max-width:460px",
      "font:600 14px/1.35 'Microsoft YaHei UI',sans-serif", "letter-spacing:.03em",
      "border:1px solid rgba(255,255,255,.55)", "box-shadow:none", "border-radius:0",
      "pointer-events:none",
    ].join(";");
    label.innerHTML = [
      "<div>实时操作 · 技术说明</div>",
      "<div style=\"font-weight:400;opacity:.82;margin-top:2px\">机器审计投影 · 仅证明软件行为</div>",
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
  await page.getByPlaceholder("you@court.edu").fill(`tech-video-${stamp}@example.com`);
  await page.getByPlaceholder("至少 6 位").fill(`Tech-Video-${stamp}!`);
  await page.getByRole("button", { name: "注册并进入" }).click();
  const [auth, sandbox] = await Promise.all([authResponse, sandboxResponse]);
  if (auth.status() !== 200 || sandbox.status() !== 200) {
    throw new Error(`registration bootstrap failed: ${auth.status()}/${sandbox.status()}`);
  }
  await page.locator(".case__version").first().waitFor({ timeout: 60000 });
  const trimSeconds = (Date.now() - recordStartedAt) / 1000 + 0.45;

  await addLabel(page);
  await page.waitForTimeout(900);
  await page.getByRole("button", { name: "技术说明" }).click();
  const dialog = page.getByRole("dialog", { name: "学科技术说明" });
  await dialog.waitFor();
  await page.locator(".pipeline article").first().waitFor({ timeout: 30000 });
  const visibleChecks = {
    overview_pipeline: await page.locator(".pipeline article").count(),
    overview_cards: await page.locator(".overview-grid article").count(),
  };
  await page.waitForTimeout(2600);

  await page.getByRole("button", { name: "数据治理" }).click();
  await page.getByText("候选资料与正式法源分层", { exact: true }).waitFor();
  visibleChecks.data_ledger_rows = await page.locator(".data-ledger article").count();
  await page.waitForTimeout(3200);

  await page.getByRole("button", { name: "推理 / 评测" }).click();
  await page.getByText("结构化推理与100题评测共用来源检查", { exact: true }).waitFor();
  visibleChecks.reasoning_checks = await page.locator(".check-grid span").count();
  visibleChecks.negative_fixtures = await page.locator(".fixture-list article").count();
  visibleChecks.eval_types = await page.locator(".eval-types article").count();
  visibleChecks.eval_routes = await page.locator(".eval-matrix article").count();
  await page.waitForTimeout(3800);

  await page.getByRole("button", { name: "Agent / 边界" }).click();
  await page.getByText("增加反方的收益，必须与成本一起展示", { exact: true }).waitFor();
  visibleChecks.agent_conditions = await page.locator(".condition").count();
  visibleChecks.pending_rows = await page.locator(".pending-list article").count();
  await page.waitForTimeout(4300);

  const video = page.video();
  await context.close();
  rawVideo = await video.path();
  const target = path.join(outputDir, "technical-evidence.webm");
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
  const expectedChecks = {
    overview_pipeline: 5,
    overview_cards: 4,
    data_ledger_rows: 4,
    reasoning_checks: 11,
    negative_fixtures: 6,
    eval_types: 5,
    eval_routes: 4,
    agent_conditions: 2,
    pending_rows: 4,
  };
  const visibleChecksPass = Object.entries(expectedChecks).every(
    ([key, expected]) => visibleChecks[key] === expected,
  );
  const sourceCommit = run("git", ["-C", repo, "rev-parse", "HEAD"]).trim();
  const audit = {
    schema: "competition-technical-evidence-video-segment-audit-v1",
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
    visible_checks: visibleChecks,
    browser_error_counts: errorCounts,
    qa: {
      expected_visible_checks_pass: visibleChecksPass,
      browser_error_total: Object.values(errorCounts).reduce((sum, value) => sum + value, 0),
      login_prefix_removed_by_reencode: true,
      raw_recording_deleted: true,
      synthetic_account_only: true,
      credential_or_token_published: false,
      public_audit_uses_relative_paths_only: true,
    },
    video_mapping: {
      segment: "技术说明→数据治理→推理/评测→Agent/边界",
      ppt_pages: [4, 6, 7, 8],
      scoring: ["技术实现", "技术先进性", "内容质量"],
    },
    evidence_boundary: (
      "real browser interaction from a synthetic local account; automatic gates are software "
      + "evidence rather than expert legal accuracy; candidate benchmark items remain not_gold; "
      + "the segment is silent source material and not the final team-approved video"
    ),
  };
  fs.writeFileSync(
    path.join(outputDir, "segment-private-manifest.json"),
    `${JSON.stringify({ ...audit, browser_errors: errors }, null, 2)}\n`,
    "utf8",
  );
  fs.writeFileSync(publicAudit, `${JSON.stringify(audit, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ ...audit, public_audit: relativeAudit }, null, 2));
  if (!visibleChecksPass || audit.qa.browser_error_total) process.exitCode = 2;
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
