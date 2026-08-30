<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import idleSprite from "../assets/tutor/tutor-idle.webp";
import halfSprite from "../assets/tutor/tutor-mouth-half.webp";
import openSprite from "../assets/tutor/tutor-mouth-open.webp";
import blinkSprite from "../assets/tutor/tutor-blink.webp";

type TutorContext = "support" | "evidence" | "path";

const props = withDefaults(defineProps<{ context: TutorContext; speechText?: string; compact?: boolean }>(), {
  speechText: "",
  compact: false,
});
const emit = defineEmits<{ speechStart: []; speechEnd: [] }>();
const speaking = ref(false);
const blinking = ref(false);
const mouthIndex = ref(0);
const browserSpeechSupported = ref(false);
let mouthTimer: number | undefined;
let blinkTimer: number | undefined;
let ownsSpeech = false;

const copy = computed(() => ({
  support: { code: "SOCRATIC", title: "陪你拆开这一层", note: "先追问，再解释；引用通过也仍需判断是否真正支持结论。" },
  evidence: { code: "EVIDENCE ALERT", title: "这条引用不能直接采信", note: "我只提示条号、范围与逐字片段风险，不替教师作法律结论。" },
  path: { code: "NEXT STEP", title: "下一步为何是这项任务", note: "依据当前证据、先修和已完成任务解释推荐；路径不是因果最优证明。" },
}[props.context]));
const mouthSprites = [idleSprite, halfSprite, openSprite, halfSprite];
const sprite = computed(() => blinking.value && !speaking.value ? blinkSprite : speaking.value ? mouthSprites[mouthIndex.value] : idleSprite);
const canSpeak = computed(() => browserSpeechSupported.value && Boolean(props.speechText.trim()));

function stopMouth(): void {
  if (mouthTimer !== undefined) window.clearInterval(mouthTimer);
  mouthTimer = undefined;
  mouthIndex.value = 0;
}
function startMouth(): void {
  stopMouth();
  mouthTimer = window.setInterval(() => { mouthIndex.value = (mouthIndex.value + 1) % mouthSprites.length; }, 145);
}
function scheduleBlink(): void {
  if (blinkTimer !== undefined) window.clearTimeout(blinkTimer);
  blinkTimer = window.setTimeout(() => {
    if (!speaking.value) {
      blinking.value = true;
      window.setTimeout(() => { blinking.value = false; }, 150);
    }
    scheduleBlink();
  }, 3200 + Math.round(Math.random() * 2600));
}
function setSpeaking(value: boolean): void {
  speaking.value = value;
  if (value) { startMouth(); emit("speechStart"); }
  else { stopMouth(); emit("speechEnd"); }
}
function speak(): void {
  if (!canSpeak.value || speaking.value) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(props.speechText.trim());
  utterance.lang = "zh-CN";
  utterance.rate = 0.96;
  utterance.onstart = () => { ownsSpeech = true; setSpeaking(true); };
  utterance.onend = () => { ownsSpeech = false; setSpeaking(false); };
  utterance.onerror = () => { ownsSpeech = false; setSpeaking(false); };
  window.speechSynthesis.speak(utterance);
}
function stopSpeech(): void {
  if (ownsSpeech && browserSpeechSupported.value) window.speechSynthesis.cancel();
  ownsSpeech = false;
  setSpeaking(false);
}

watch(() => props.speechText, () => { if (speaking.value) stopSpeech(); });
onMounted(() => {
  browserSpeechSupported.value = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
  scheduleBlink();
});
onBeforeUnmount(() => {
  stopMouth();
  if (blinkTimer !== undefined) window.clearTimeout(blinkTimer);
  if (ownsSpeech && browserSpeechSupported.value) window.speechSynthesis.cancel();
});
</script>

<template>
  <aside :class="['ai-tutor', `ai-tutor--${context}`, { 'ai-tutor--compact': compact, 'ai-tutor--speaking': speaking }]" :aria-label="`AI助教形成性反馈：${copy.title}`">
    <div class="ai-tutor__halo" aria-hidden="true"></div>
    <div class="ai-tutor__figure"><img :src="sprite" alt="原创轻量2D法学AI助教" width="768" height="960" /></div>
    <div class="ai-tutor__docket">
      <p class="ai-tutor__code mono">{{ copy.code }}</p><h3>{{ copy.title }}</h3><p>{{ copy.note }}</p>
      <div class="ai-tutor__truth"><span>AI助教·形成性反馈</span><small>{{ speaking ? "浏览器本地朗读中 · AI语音" : "非教师结论 · 不形成正式成绩" }}</small></div>
      <button v-if="speechText" type="button" :disabled="!canSpeak" @click="speaking ? stopSpeech() : speak()"><span aria-hidden="true">{{ speaking ? "■" : "▶" }}</span>{{ speaking ? "停止朗读" : browserSpeechSupported ? "朗读本段" : "浏览器不支持朗读" }}</button>
    </div>
  </aside>
</template>

<style scoped>
.ai-tutor{position:relative;isolation:isolate;min-height:250px;display:grid;grid-template-columns:minmax(150px,.72fr) minmax(190px,1fr);align-items:end;overflow:hidden;color:var(--parchment);border:1px solid rgba(100,139,153,.44);background:linear-gradient(135deg,rgba(17,25,27,.96),rgba(8,10,9,.98) 68%);box-shadow:inset 0 1px rgba(255,255,255,.035)}
.ai-tutor::before{content:"";position:absolute;inset:0;z-index:-2;background:linear-gradient(90deg,rgba(255,255,255,.018) 1px,transparent 1px) 0 0/26px 26px,linear-gradient(rgba(255,255,255,.012) 1px,transparent 1px) 0 0/26px 26px}.ai-tutor::after{content:"AI FORMATIVE";position:absolute;right:-22px;top:28px;z-index:-1;color:rgba(137,175,186,.07);font:800 2.15rem/1 var(--font-mono);letter-spacing:.05em;transform:rotate(90deg)}
.ai-tutor__halo{position:absolute;left:7%;bottom:8%;z-index:-1;width:46%;aspect-ratio:1;border:1px solid rgba(100,139,153,.24);border-radius:50%;box-shadow:0 0 64px rgba(38,91,112,.22),inset 0 0 36px rgba(38,91,112,.12)}
.ai-tutor__figure{align-self:end;min-width:0;height:250px;display:flex;align-items:flex-end;justify-content:center;transform-origin:50% 92%;animation:tutor-breathe 4.8s ease-in-out infinite}.ai-tutor__figure img{width:auto;height:272px;max-width:100%;object-fit:contain;object-position:center bottom;filter:drop-shadow(0 18px 20px rgba(0,0,0,.4));transform-origin:50% 88%;animation:tutor-sway 7s ease-in-out infinite}
.ai-tutor__docket{position:relative;align-self:center;margin:18px 18px 18px 0;padding:17px 17px 15px;border-left:2px solid #6c98a8;background:linear-gradient(90deg,rgba(100,139,153,.09),transparent)}.ai-tutor__docket::before{content:"";position:absolute;left:-7px;top:18px;width:11px;height:11px;border:1px solid #739dac;background:#101615;transform:rotate(45deg)}
.ai-tutor__code{margin:0;color:#8eb7c5;font-size:.56rem;letter-spacing:.18em}.ai-tutor h3{margin:5px 0 7px;font-size:1rem;line-height:1.3}.ai-tutor__docket>p:not(.ai-tutor__code){margin:0;color:var(--parchment-dim);font-size:.66rem;line-height:1.58}
.ai-tutor__truth{display:grid;gap:2px;margin-top:13px;padding-top:10px;border-top:1px solid var(--line)}.ai-tutor__truth span{color:#b9d1da;font-family:var(--font-display);font-size:.68rem}.ai-tutor__truth small{color:var(--parchment-faint);font-size:.54rem}.ai-tutor button{margin-top:10px;padding:7px 10px;color:#dce8eb;border:1px solid rgba(100,139,153,.48);background:rgba(100,139,153,.08);font:inherit;font-size:.62rem;cursor:pointer}.ai-tutor button span{margin-right:6px;color:#87b3c1}.ai-tutor button:disabled{opacity:.42;cursor:not-allowed}
.ai-tutor--evidence{border-color:rgba(196,71,27,.5);background:linear-gradient(135deg,rgba(35,19,14,.96),rgba(10,10,9,.98) 70%)}.ai-tutor--evidence .ai-tutor__docket{border-left-color:#c46b45}.ai-tutor--evidence .ai-tutor__code,.ai-tutor--evidence .ai-tutor__truth span{color:#e1a18a}.ai-tutor--evidence .ai-tutor__halo{border-color:rgba(196,71,27,.25);box-shadow:0 0 60px rgba(196,71,27,.13)}
.ai-tutor--path{border-color:rgba(122,153,98,.48)}.ai-tutor--path .ai-tutor__docket{border-left-color:#84a878}.ai-tutor--path .ai-tutor__code,.ai-tutor--path .ai-tutor__truth span{color:#b4cda9}
.ai-tutor--compact{min-height:190px;grid-template-columns:125px minmax(180px,1fr)}.ai-tutor--compact .ai-tutor__figure{height:190px}.ai-tutor--compact .ai-tutor__figure img{height:208px}.ai-tutor--compact .ai-tutor__docket{margin:12px 12px 12px 0;padding:12px 12px 11px}.ai-tutor--compact h3{font-size:.82rem}.ai-tutor--compact .ai-tutor__docket>p:not(.ai-tutor__code){font-size:.58rem}.ai-tutor--speaking .ai-tutor__halo{box-shadow:0 0 82px rgba(82,151,176,.32),inset 0 0 34px rgba(82,151,176,.14)}
@keyframes tutor-breathe{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-3px) scale(1.006)}}@keyframes tutor-sway{0%,100%{transform:rotate(-.35deg)}50%{transform:rotate(.45deg)}}
@media(max-width:720px){.ai-tutor{grid-template-columns:108px minmax(0,1fr);min-height:180px}.ai-tutor__figure{height:180px}.ai-tutor__figure img{height:195px}.ai-tutor__docket{margin:10px 10px 10px 0;padding:11px}.ai-tutor h3{font-size:.78rem}.ai-tutor__docket>p:not(.ai-tutor__code){display:none}.ai-tutor::after{display:none}}@media(prefers-reduced-motion:reduce){.ai-tutor__figure,.ai-tutor__figure img{animation:none}}
</style>
