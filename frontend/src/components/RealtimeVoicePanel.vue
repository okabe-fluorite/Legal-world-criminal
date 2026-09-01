<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue";
import {
  RealtimeVoiceClient,
  type RealtimeVoiceMessage,
  type RealtimeVoicePhase,
} from "../lib/realtimeVoice";
import EvidenceCitations from "./EvidenceCitations.vue";
import { toEvidenceReference } from "../lib/evidence";

const props = withDefaults(defineProps<{ asrStatus?: string; ttsStatus?: string }>(), {
  asrStatus: "not_configured",
  ttsStatus: "not_configured",
});

const emit = defineEmits<{ verified: [] }>();

interface VoiceTurnView {
  turnId: string;
  partial: string;
  transcript: string;
  replyText: string;
  evidences: NonNullable<RealtimeVoiceMessage["evidences"]>;
  source: string;
  coverageStatus: string;
  audioUrl: string;
  audioBytes: number;
  durationSeconds: number;
  voice: string;
  preferredVoiceUsed: boolean;
  status: "listening" | "recognizing" | "generating" | "ready" | "failed";
  error: string;
}

const phase = ref<RealtimeVoicePhase>("idle");
const turns = ref<VoiceTurnView[]>([]);
const activeTurnId = ref("");
const panelError = ref("");
const playbackState = ref<"idle" | "playing" | "manual" | "ended">("idle");
const audioRef = ref<HTMLAudioElement | null>(null);
let elapsedTimer = 0;
const elapsedSeconds = ref(0);
const microphoneLevel = ref(0);
const microphonePeak = ref(0);
const microphoneName = ref("尚未授权设备");
const microphoneWarning = ref("");
const permissionState = ref("prompt");
let signalTimer = 0;

function emptyTurn(id: string): VoiceTurnView {
  return {
    turnId: id,
    partial: "",
    transcript: "",
    replyText: "",
    evidences: [],
    source: "",
    coverageStatus: "",
    audioUrl: "",
    audioBytes: 0,
    durationSeconds: 0,
    voice: "",
    preferredVoiceUsed: true,
    status: "listening",
    error: "",
  };
}

function resolveTurn(id: string): VoiceTurnView {
  let turn = turns.value.find((row) => row.turnId === id);
  if (!turn) {
    turn = emptyTurn(id);
    turns.value.push(turn);
  }
  return turn;
}

function base64AudioUrl(base64: string, contentType: string): string {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return URL.createObjectURL(new Blob([bytes], { type: contentType }));
}

function stopElapsedTimer(): void {
  window.clearInterval(elapsedTimer);
  elapsedTimer = 0;
}

async function autoPlayTurn(turn: VoiceTurnView): Promise<void> {
  await nextTick();
  const audio = audioRef.value;
  if (!audio || !turn.audioUrl) return;
  try {
    await audio.play();
    playbackState.value = "playing";
  } catch {
    playbackState.value = "manual";
    panelError.value = "浏览器阻止了自动播放，请点击下方音频控件播放AI回复。";
  }
}

function handleMessage(message: RealtimeVoiceMessage): void {
  const id = String(message.turn_id || activeTurnId.value || "");
  if (message.type === "voice_error") {
    panelError.value = message.message || "实时语音处理失败。";
    if (id) {
      const turn = resolveTurn(id);
      turn.error = panelError.value;
      turn.status = "failed";
    }
    activeTurnId.value = "";
    stopElapsedTimer();
    return;
  }
  if (!id) return;
  const turn = resolveTurn(id);
  if (message.type === "voice_session_ready") {
    turn.status = "listening";
    activeTurnId.value = id;
    microphoneName.value = client.activeMicrophoneName;
    emit("verified");
  } else if (message.type === "voice_transcript_partial") {
    turn.partial = String(message.transcript || "");
  } else if (message.type === "voice_transcript_final") {
    turn.transcript = String(message.transcript || "");
    turn.partial = "";
    turn.status = "recognizing";
  } else if (message.type === "voice_reply_generating" || message.type === "voice_reply_text") {
    turn.replyText = String(message.reply_text || turn.replyText);
    turn.evidences = message.evidences ?? turn.evidences;
    turn.source = String(message.source || turn.source);
    turn.coverageStatus = String(message.coverage_status || turn.coverageStatus);
    turn.status = "generating";
  } else if (message.type === "voice_reply" && message.audio) {
    if (turn.audioUrl) URL.revokeObjectURL(turn.audioUrl);
    turn.replyText = String(message.reply_text || "");
    turn.evidences = message.evidences ?? [];
    turn.source = String(message.source || "");
    turn.coverageStatus = String(message.coverage_status || "");
    turn.audioUrl = base64AudioUrl(message.audio.base64, message.audio.content_type);
    turn.audioBytes = Number(message.audio.size_bytes || 0);
    turn.durationSeconds = Number(message.audio.duration_seconds || 0);
    turn.voice = String(message.audio.voice || "");
    turn.preferredVoiceUsed = Boolean(message.audio.preferred_voice_used);
    turn.status = "ready";
    activeTurnId.value = "";
    playbackState.value = "idle";
    emit("verified");
    void autoPlayTurn(turn);
  } else if (message.type === "voice_turn_cancelled") {
    turn.status = "failed";
    turn.error = "本轮已取消，未生成转写、回复或学习事件。";
    activeTurnId.value = "";
  }
}

const client = new RealtimeVoiceClient(
  handleMessage,
  (value) => {
    phase.value = value;
    if (value !== "listening") stopElapsedTimer();
  },
  (level) => {
    microphoneLevel.value = level;
    microphonePeak.value = Math.max(microphonePeak.value, level);
    if (level > .018) microphoneWarning.value = "";
  },
);

const isBusy = computed(() => [
  "requesting_permission",
  "connecting",
  "recognizing",
  "generating",
].includes(phase.value));
const latestTurn = computed(() => turns.value[turns.value.length - 1] ?? null);
const completedTurns = computed(() => turns.value.filter((row) => row.status === "ready").length);
const latestReferences = computed(() => (latestTurn.value?.evidences ?? []).map((row, index) =>
  toEvidenceReference({ ...row, id: row.evidence_id }, `voice-${index + 1}`),
));
const asrStateLabel = computed(() => ({
  available: "ASR 已连接",
  configured_not_verified: "ASR 已配置 · 待本轮握手",
  not_configured: "ASR 未配置",
  not_connected: "ASR 未连接",
}[props.asrStatus] ?? `ASR ${props.asrStatus}`));
const ttsStateLabel = computed(() => ({
  available: "TTS 已连接 · 小露女声",
  configured_not_verified: "TTS 已配置 · 待首轮合成",
  not_configured: "TTS 未配置",
  not_connected: "TTS 未连接",
}[props.ttsStatus] ?? `TTS ${props.ttsStatus}`));
const canStart = computed(() => (
  ["idle", "error"].includes(phase.value)
  || (phase.value === "reply_ready" && playbackState.value !== "playing")
));
const phaseLabel = computed(() => ({
  idle: "等待提问",
  requesting_permission: "请求麦克风权限",
  connecting: "连接讯飞实时IAT",
  listening: `正在聆听 · ${elapsedSeconds.value}s`,
  recognizing: "等待最终转写",
  generating: "检索Evidence并生成回复",
  reply_ready: playbackState.value === "playing" ? "AI语音播放中" : "本轮完成 · 可继续提问",
  error: "本轮未完成 · 可重试",
})[phase.value]);

async function startTurn(): Promise<void> {
  panelError.value = "";
  playbackState.value = "idle";
  elapsedSeconds.value = 0;
  microphoneLevel.value = 0;
  microphonePeak.value = 0;
  microphoneWarning.value = "";
  window.clearTimeout(signalTimer);
  try {
    const id = await client.startTurn();
    activeTurnId.value = id;
    resolveTurn(id).status = "listening";
    microphoneName.value = client.activeMicrophoneName;
    signalTimer = window.setTimeout(() => {
      if (phase.value === "listening" && microphonePeak.value < .012) {
        microphoneWarning.value = "已连接讯飞，但没有检测到麦克风声音；请检查系统输入设备、物理静音键和浏览器权限。";
      }
    }, 3500);
    stopElapsedTimer();
    elapsedTimer = window.setInterval(() => {
      elapsedSeconds.value += 1;
      if (elapsedSeconds.value >= 60) void stopTurn();
    }, 1000);
  } catch (reason) {
    panelError.value = reason instanceof DOMException && reason.name === "NotAllowedError"
      ? "麦克风权限被拒绝；请在浏览器地址栏允许麦克风后重试。"
      : reason instanceof Error ? reason.message : String(reason);
  }
}

async function stopTurn(): Promise<void> {
  panelError.value = "";
  stopElapsedTimer();
  window.clearTimeout(signalTimer);
  try {
    await client.stopTurn();
  } catch (reason) {
    panelError.value = reason instanceof Error ? reason.message : String(reason);
    phase.value = "error";
  }
}

async function cancelTurn(): Promise<void> {
  stopElapsedTimer();
  await client.cancelTurn();
  activeTurnId.value = "";
}

function handlePlaybackEnded(): void {
  playbackState.value = "ended";
}

function handlePlaybackPaused(): void {
  const audio = audioRef.value;
  if (audio && !audio.ended && audio.currentTime > 0) playbackState.value = "manual";
}

onUnmounted(() => {
  stopElapsedTimer();
  window.clearTimeout(signalTimer);
  for (const turn of turns.value) if (turn.audioUrl) URL.revokeObjectURL(turn.audioUrl);
  void client.close();
});

onMounted(async () => {
  try {
    const status = await navigator.permissions?.query({ name: "microphone" as PermissionName });
    if (status) {
      permissionState.value = status.state;
      status.onchange = () => { permissionState.value = status.state; };
    }
  } catch {
    permissionState.value = "unknown";
  }
});
</script>

<template>
  <section class="voice-console" aria-label="讯飞实时语音对话">
    <header>
      <div>
        <p class="voice-kicker">LIVE MICROPHONE · IFLYTEK STREAMING IAT → EVIDENCE → TTS</p>
        <h3>与刑法AI助教实时语音交流</h3>
        <p>点击开始后直接说话，页面会边听边显示转写；结束本轮后自动检索受治理法源、生成形成性回复并播放讯飞语音。</p>
      </div>
      <div class="voice-runtime" :class="`phase--${phase}`">
        <i></i><strong>{{ phaseLabel }}</strong><span>{{ completedTurns }}轮已完成</span>
      </div>
    </header>

    <div class="voice-health" aria-label="实时语音连接诊断">
      <span :class="{ ok: asrStatus === 'available', configured: asrStatus === 'configured_not_verified' }"><i></i>{{ asrStateLabel }}</span>
      <span :class="{ ok: ttsStatus === 'available', configured: ttsStatus === 'configured_not_verified' }"><i></i>{{ ttsStateLabel }}</span>
      <span :class="{ ok: permissionState === 'granted', warn: permissionState === 'denied' }"><i></i>麦克风权限 {{ permissionState }}</span>
      <strong>{{ microphoneName }}</strong>
    </div>

    <div class="voice-stage">
      <div class="voice-orb" :class="{ live: phase === 'listening', thinking: isBusy && phase !== 'listening' }" aria-hidden="true">
        <span v-for="index in 7" :key="index" :style="phase === 'listening' ? { height: `${Math.max(10, Math.min(62, 10 + microphoneLevel * 52 * (1 - Math.abs(4 - index) * .08)))}px` } : undefined"></span>
      </div>
      <div class="voice-actions">
        <button v-if="canStart" class="voice-primary" @click="startTurn">● 开始实时提问</button>
        <button v-else-if="phase === 'listening'" class="voice-primary voice-stop" @click="stopTurn">■ 结束本轮并发送</button>
        <button v-else class="voice-primary" disabled>{{ phaseLabel }}</button>
        <button v-if="activeTurnId && phase === 'listening'" class="voice-cancel" @click="cancelTurn">取消本轮</button>
        <small>16kHz · 单声道 · 16bit PCM · 40ms分片 · 单轮≤60秒</small>
        <div class="input-level"><i :style="{ width: `${Math.round(microphoneLevel * 100)}%` }"></i></div><small>真实输入电平 {{ Math.round(microphoneLevel * 100) }}%</small>
      </div>
    </div>

    <p v-if="panelError" class="voice-error" role="alert">{{ panelError }}</p>
    <p v-if="microphoneWarning" class="voice-warning" role="status">{{ microphoneWarning }}</p>

    <article v-if="latestTurn" class="voice-turn">
      <div class="turn-index"><span>TURN</span><b>{{ String(turns.length).padStart(2, "0") }}</b><small>{{ latestTurn.turnId }}</small></div>
      <div class="turn-content">
        <section>
          <p class="voice-kicker">REAL-TIME TRANSCRIPT · NEEDS REVIEW</p>
          <h4>你的问题</h4>
          <p :class="{ partial: latestTurn.partial && !latestTurn.transcript }">{{ latestTurn.transcript || latestTurn.partial || "正在等待第一段语音……" }}</p>
          <small>ASR转写仅用于本轮形成性对话，未确认前不进入正式评价。</small>
        </section>
        <section>
          <p class="voice-kicker">AI TUTOR · GOVERNED EVIDENCE</p>
          <h4>形成性回复</h4>
          <p><span>{{ latestTurn.replyText || (latestTurn.status === "generating" ? "正在检索受治理法源并生成口语回复……" : "结束本轮后在此显示回复。") }}</span><EvidenceCitations :references="latestReferences" /></p>
          <audio
            v-if="latestTurn.audioUrl"
            ref="audioRef"
            :src="latestTurn.audioUrl"
            controls
            autoplay
            aria-label="讯飞AI形成性回复音频"
            @play="playbackState = 'playing'"
            @pause="handlePlaybackPaused"
            @ended="handlePlaybackEnded"
          ></audio>
          <small v-if="latestTurn.audioUrl">讯飞TTS · {{ latestTurn.voice || 'x4_yezi' }}{{ latestTurn.preferredVoiceUsed ? '（小露女声）' : '（回退音色）' }} · {{ latestTurn.audioBytes.toLocaleString() }} bytes · {{ latestTurn.durationSeconds.toFixed(2) }}s · AI合成语音</small>
        </section>
      </div>
    </article>

    <footer class="voice-boundary">
      <span><b>0</b> LearningEvent</span><span><b>0</b> 正式评分</span><span><b>0</b> 自动画像更新</span>
      <p>实时ASR、AI回复和TTS均为课堂形成性辅助；Evidence检索相关性不等于法律蕴含，争议问题仍需教师复核。</p>
    </footer>
  </section>
</template>

<style scoped>
.voice-console{border:1px solid rgba(112,157,171,.48);background:linear-gradient(145deg,rgba(9,15,17,.96),rgba(19,31,35,.94));box-shadow:0 20px 55px rgba(0,0,0,.24),inset 0 1px rgba(203,232,236,.04);overflow:hidden}.voice-console>header{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:22px;align-items:center;padding:21px 22px;border-bottom:1px solid rgba(112,157,171,.25)}.voice-console h3{margin:0 0 6px;font-size:1.25rem;color:#e6eff0}.voice-console header p:not(.voice-kicker){max-width:760px;margin:0;color:#9eb2b5;font-size:.8rem;line-height:1.65}.voice-kicker{margin:0 0 5px;color:#79aaba;font:600 .6rem/1.2 var(--font-mono);letter-spacing:.14em}.voice-runtime{min-width:190px;display:grid;grid-template-columns:12px 1fr;align-items:center;gap:3px 8px;padding:11px 13px;border:1px solid rgba(112,157,171,.35);background:rgba(5,10,11,.42)}.voice-runtime i{grid-row:1/3;width:9px;height:9px;border-radius:50%;background:#718087;box-shadow:0 0 0 4px rgba(113,128,135,.12)}.voice-runtime strong{color:#dce8ea;font-size:.75rem}.voice-runtime span{color:#829397;font-size:.61rem}.voice-runtime.phase--listening i{background:#82d3ad;box-shadow:0 0 0 4px rgba(130,211,173,.13),0 0 18px #62b994}.voice-runtime.phase--error i{background:#d4846f}.voice-health{display:flex;align-items:center;flex-wrap:wrap;gap:7px;padding:10px 22px;border-bottom:1px solid rgba(112,157,171,.18);background:rgba(4,9,10,.2)}.voice-health>span{display:inline-flex;align-items:center;gap:5px;padding:5px 7px;color:#afbbb9;border:1px solid rgba(112,157,171,.28);font:500 .6rem/1.2 var(--font-mono)}.voice-health>span i{width:6px;height:6px;border-radius:50%;background:#8a7768}.voice-health>span.ok{color:#b8d6c1;border-color:rgba(130,190,158,.45)}.voice-health>span.ok i{background:#82d3ad}.voice-health>span.configured{color:#d4bc8a;border-color:rgba(190,159,91,.4)}.voice-health>span.configured i{background:#caa45d}.voice-health>span.warn{color:#df9a84;border-color:rgba(196,71,27,.45)}.voice-health>span.warn i{background:#d47d64}.voice-health>strong{margin-left:auto;max-width:320px;overflow:hidden;color:#71898e;font-size:.6rem;text-overflow:ellipsis;white-space:nowrap}.voice-stage{display:grid;grid-template-columns:190px minmax(0,1fr);align-items:center;gap:22px;padding:20px 22px}.voice-orb{height:92px;display:flex;align-items:center;justify-content:center;gap:5px;border-right:1px solid rgba(112,157,171,.2)}.voice-orb span{width:4px;height:16px;background:#67838d;transition:.14s}.voice-orb.live span{background:#8bcbb3;animation:none}.voice-orb.thinking span{animation:voice-pulse 1.2s ease-in-out infinite}.voice-actions{display:flex;align-items:center;flex-wrap:wrap;gap:9px}.voice-actions button{border:1px solid rgba(125,174,187,.45);font-family:var(--font-display);cursor:pointer}.voice-primary{min-width:210px;padding:12px 18px;color:#eef7f4;background:linear-gradient(120deg,#305f69,#347b6b)}.voice-primary:disabled{opacity:.58;cursor:wait}.voice-stop{background:linear-gradient(120deg,#70473e,#8d5a46)}.voice-cancel{padding:11px 14px;color:#aebdc0;background:transparent}.voice-actions small{flex-basis:100%;color:#789094;font:500 .59rem/1.4 var(--font-mono)}.input-level{flex-basis:100%;height:4px;background:rgba(112,157,171,.2)}.input-level i{display:block;height:100%;background:#82d3ad;transition:width .12s ease}.voice-error{margin:0 22px 18px;padding:9px 11px;color:#e3b5a8;border:1px solid rgba(190,102,80,.4);background:rgba(108,43,32,.18);font-size:.72rem}.voice-warning{margin:0 22px 18px;padding:9px 11px;color:#ddc08c;border:1px solid rgba(190,159,91,.45);background:rgba(120,84,31,.14);font-size:.72rem}.voice-turn{display:grid;grid-template-columns:96px minmax(0,1fr);margin:0 22px 20px;border:1px solid rgba(112,157,171,.25);background:rgba(4,9,10,.35)}.turn-index{padding:15px 12px;border-right:1px solid rgba(112,157,171,.2)}.turn-index span,.turn-index small{display:block;color:#70898e;font:500 .55rem/1.4 var(--font-mono)}.turn-index b{display:block;margin:3px 0 9px;color:#cfe2e4;font:700 1.3rem/1 var(--font-mono)}.turn-index small{word-break:break-all}.turn-content{display:grid;grid-template-columns:1fr 1.15fr}.turn-content section{min-width:0;padding:15px 17px}.turn-content section+section{border-left:1px solid rgba(112,157,171,.2)}.turn-content h4{margin:0 0 7px;color:#dbe7e8;font-size:.86rem}.turn-content section>p:not(.voice-kicker){min-height:42px;margin:0 0 8px;color:#bac9cb;font-size:.76rem;line-height:1.65}.turn-content p.partial{color:#8fc1b3}.turn-content small{color:#758a8f;font-size:.58rem;line-height:1.45}.turn-content audio{width:100%;height:32px;margin:7px 0}.voice-boundary{display:grid;grid-template-columns:repeat(3,auto) 1fr;gap:8px 16px;align-items:center;padding:12px 22px;border-top:1px solid rgba(112,157,171,.25);background:rgba(3,7,8,.35)}.voice-boundary span{color:#9db0b3;font-size:.65rem}.voice-boundary b{color:#8bcbb3;font:700 .95rem var(--font-mono)}.voice-boundary p{margin:0;color:#71878b;font-size:.61rem;line-height:1.45}@keyframes voice-pulse{0%,100%{opacity:.35;height:14px}50%{opacity:1;height:34px}}@media(max-width:820px){.voice-console>header{grid-template-columns:1fr}.voice-health{padding:9px 13px}.voice-health>strong{flex-basis:100%;margin-left:0}.voice-stage{grid-template-columns:1fr}.voice-orb{height:60px;border-right:0;border-bottom:1px solid rgba(112,157,171,.2)}.voice-turn{grid-template-columns:1fr}.turn-index{border-right:0;border-bottom:1px solid rgba(112,157,171,.2)}.turn-content{grid-template-columns:1fr}.turn-content section+section{border-left:0;border-top:1px solid rgba(112,157,171,.2)}.voice-boundary{grid-template-columns:repeat(3,1fr)}.voice-boundary p{grid-column:1/-1}.voice-primary{width:100%}}
</style>
