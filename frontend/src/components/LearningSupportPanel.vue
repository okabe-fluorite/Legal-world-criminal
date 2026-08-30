<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api } from "../lib/api";
import type { LearningSupportSeed, LearningSupportSession } from "../lib/types";
import AITutor from "./AITutor.vue";

const props = defineProps<{ seed: LearningSupportSeed }>();
const emit = defineEmits<{ close: []; retryTask: [] }>();

const loading = ref(true);
const responding = ref(false);
const error = ref("");
const session = ref<LearningSupportSession | null>(null);
const studentResponse = ref("");
const sessionId = `support-${
  typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
}`;

const result = computed(() => session.value?.result ?? null);
const isFallback = computed(() => session.value?.result_source === "deterministic_fallback");
const supportStatus = computed(() => {
  if (!session.value) return "建立会话";
  if (session.value.status === "awaiting_response") return "等待你的解释";
  if (session.value.status === "needs_teacher_review") return "需要教师复核";
  return "分层解释完成";
});

const layerRows = computed(() => {
  if (!result.value) return [];
  return [
    { no: "01", key: "norm", label: "规范原文", content: result.value.layers.norm.content },
    { no: "02", key: "plain", label: "白话解释", content: result.value.layers.plain.content },
    { no: "03", key: "application", label: "事实适用", content: result.value.layers.application.content },
    { no: "04", key: "dispute", label: "争议边界", content: result.value.layers.dispute.content },
  ];
});
const tutorSpeech = computed(() => {
  if (!result.value) return "";
  return [
    `关于${props.seed.knowledgeName}，先看规范原文。${result.value.layers.norm.content}`,
    `白话解释：${result.value.layers.plain.content}`,
    `事实适用：${result.value.layers.application.content}`,
    `争议边界：${result.value.layers.dispute.content}`,
  ].join(" ");
});

async function createSession(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const response = await api.createLearningSupportSession({
      session_id: sessionId,
      knowledge_id: props.seed.knowledgeId,
      task_id: props.seed.taskId,
      phase: props.seed.phase,
      confusion_type: props.seed.confusionType,
      confusion_note: props.seed.note,
    });
    session.value = response.session;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    loading.value = false;
  }
}

async function respond(): Promise<void> {
  if (!session.value || !studentResponse.value.trim() || responding.value) return;
  responding.value = true;
  error.value = "";
  try {
    const response = await api.respondLearningSupport(
      session.value.session_id,
      studentResponse.value.trim(),
    );
    session.value = response.session;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    responding.value = false;
  }
}

onMounted(() => void createSession());
</script>

<template>
  <div class="support-layer" @click.self="emit('close')">
    <section class="support-sheet" role="dialog" aria-modal="true" aria-label="AI分层解惑">
      <header class="support-head">
        <div class="support-brand">
          <span class="support-seal">问</span>
          <div>
            <p class="support-kicker mono">SOCRATIC NOTE · GOVERNED EVIDENCE</p>
            <h2>刑法分层解惑</h2>
            <p>{{ props.seed.knowledgeName }} · {{ props.seed.phase === "prestudy" ? "课前预习" : "课后复习" }}</p>
          </div>
        </div>
        <span :class="['support-status', { 'support-status--review': session?.status === 'needs_teacher_review' }]">
          {{ supportStatus }}
        </span>
        <button class="support-close" aria-label="关闭分层解惑" @click="emit('close')">×</button>
      </header>

      <div class="support-body">
        <aside class="support-rail">
          <div class="support-step complete"><span>01</span><strong>记录困惑</strong><small>进入证据账本</small></div>
          <div :class="['support-step', { complete: session }]">
            <span>02</span><strong>诊断追问</strong><small>先说出你的理解</small>
          </div>
          <div :class="['support-step', { complete: result }]">
            <span>03</span><strong>分层解释</strong><small>规范·白话·适用·争议</small>
          </div>
          <div class="support-boundary">
            <b>形成性边界</b>
            <p>本会话不计分、不更新长期掌握，也不代替教师对争议问题作出结论。</p>
          </div>
        </aside>

        <main class="support-main">
          <AITutor context="support" :speech-text="tutorSpeech" compact />
          <div v-if="loading" class="support-loading">
            <span class="support-seal">析</span>
            <p>正在读取KnowledgeCard与标准Evidence……</p>
          </div>

          <section v-else-if="error && !session" class="support-error">
            <h3>无法建立解惑会话</h3><p>{{ error }}</p>
            <button class="btn" @click="createSession">重试</button>
          </section>

          <template v-else-if="session">
            <section class="confusion-quote">
              <p class="support-kicker mono">YOUR QUESTION</p>
              <blockquote>{{ session.confusion_note }}</blockquote>
            </section>

            <section v-if="!result" class="diagnostic-card">
              <div class="diagnostic-card__head">
                <span class="mono">DIAGNOSTIC QUESTION</span>
                <em>先追问，再解释</em>
              </div>
              <h3>{{ session.diagnostic_question }}</h3>
              <textarea
                v-model="studentResponse"
                maxlength="5000"
                placeholder="请先写出你的判断依据。即使不确定，也尽量说明事实与法律条件如何连接……"
              ></textarea>
              <div class="diagnostic-card__actions">
                <span class="mono">你的回答只用于本次形成性解惑</span>
                <button :disabled="!studentResponse.trim() || responding" @click="respond">
                  {{ responding ? "正在核验Evidence…" : "生成分层解释 →" }}
                </button>
              </div>
              <p v-if="error" class="support-inline-error">{{ error }}</p>
            </section>

            <template v-else>
              <section :class="['diagnosis-strip', { fallback: isFallback }]">
                <span class="diagnosis-strip__seal">{{ isFallback ? "守" : "析" }}</span>
                <div>
                  <p class="support-kicker mono">
                    {{ isFallback ? "DETERMINISTIC FALLBACK" : "GOVERNED AI EXPLANATION" }}
                  </p>
                  <h3>{{ result.diagnosis.summary }}</h3>
                  <span>
                    {{ isFallback ? "模型输出未通过结构或引用门禁，已使用受治理知识卡解释。" : "引用已通过条号与逐字片段检查；法律蕴含仍未自动确认。" }}
                  </span>
                </div>
              </section>

              <div class="layer-grid">
                <article v-for="row in layerRows" :key="row.key" :class="`layer-card layer-card--${row.key}`">
                  <header><span class="mono">{{ row.no }}</span><h3>{{ row.label }}</h3></header>
                  <p>{{ row.content }}</p>
                  <div v-if="row.key === 'norm'" class="citation-stack">
                    <blockquote v-for="citation in result.layers.norm.citations" :key="`${citation.title}:${citation.article_ref}`">
                      <cite>{{ citation.title }} {{ citation.article_ref }}</cite>
                      <span>{{ citation.quote }}</span>
                    </blockquote>
                  </div>
                </article>
              </div>

              <section class="next-action-note">
                <div><p class="support-kicker mono">NEXT ACTION</p><h3>{{ result.next_action.instruction }}</h3></div>
                <button v-if="result.next_action.type === 'retry_task'" @click="emit('retryTask')">回到任务重新作答</button>
                <button v-else @click="emit('close')">返回学习卷宗</button>
              </section>

              <p v-if="result.teacher_review_required" class="teacher-review-note">
                此解释含低置信度或争议边界，已标记“需要教师复核”；请勿把它作为正式法律结论。
              </p>
            </template>
          </template>
        </main>
      </div>
    </section>
  </div>
</template>

<style scoped>
.support-layer { position: fixed; inset: 0; z-index: 1450; display: grid; place-items: center; padding: 24px; background: radial-gradient(circle at 75% 18%, rgba(92,122,138,.17), transparent 36%), rgba(4,4,3,.88); backdrop-filter: blur(12px); }
.support-sheet { width: min(1180px, 100%); max-height: calc(100vh - 48px); display: flex; flex-direction: column; overflow: hidden; color: var(--parchment); border: 1px solid rgba(92,122,138,.48); background: linear-gradient(145deg,#151914,#0d0e0c 68%); box-shadow: 0 38px 100px #000c; }
.support-head { min-height: 82px; display: grid; grid-template-columns: 1fr auto 38px; align-items: center; gap: 18px; padding: 12px 18px 12px 24px; border-bottom: 1px solid rgba(92,122,138,.32); background: linear-gradient(180deg,rgba(29,34,29,.98),rgba(15,17,15,.98)); }
.support-brand { display:flex; align-items:center; gap:14px; }
.support-seal { width:46px; height:46px; display:grid; place-items:center; flex:0 0 auto; color:#dce9e4; border:1px solid #71909c; box-shadow:inset 0 0 0 3px #132126; font-family:var(--font-display); font-size:1.08rem; font-weight:800; transform:rotate(-2deg); }
.support-kicker { margin:0 0 3px; color:#88aab7; font-size:.63rem; letter-spacing:.17em; }
.support-brand h2 { margin:0; font-size:1.28rem; font-weight:650; }
.support-brand p:last-child { margin:2px 0 0; color:var(--parchment-dim); font-size:.72rem; }
.support-status { padding:6px 9px; color:#bfd2b2; border:1px solid rgba(122,153,98,.45); font-size:.72rem; }
.support-status--review { color:#e0b58e; border-color:rgba(196,71,27,.48); }
.support-close { width:36px; height:36px; color:var(--parchment-muted); border:1px solid var(--line-strong); background:transparent; font-size:1.35rem; cursor:pointer; }
.support-body { flex:1; min-height:0; display:grid; grid-template-columns:220px minmax(0,1fr); }
.support-rail { padding:24px 17px; border-right:1px solid var(--line-strong); background:rgba(9,11,9,.64); }
.support-step { position:relative; display:grid; grid-template-columns:30px 1fr; column-gap:9px; padding:8px 4px 20px; color:var(--parchment-faint); }
.support-step:not(:last-of-type)::after { content:""; position:absolute; left:18px; top:39px; bottom:0; width:1px; background:var(--line-strong); }
.support-step > span { width:28px; height:28px; display:grid; place-items:center; border:1px solid var(--line-strong); font-family:var(--font-mono); font-size:.62rem; }
.support-step strong { font-family:var(--font-display); font-size:.82rem; font-weight:560; }
.support-step small { grid-column:2; font-size:.64rem; }
.support-step.complete { color:#b9ced6; }
.support-step.complete > span { border-color:#7895a2; background:rgba(92,122,138,.12); }
.support-boundary { margin-top:22px; padding:10px; border:1px dashed var(--line-strong); }
.support-boundary b { color:var(--accent); font-family:var(--font-display); font-size:.75rem; }
.support-boundary p { margin:5px 0 0; color:var(--parchment-faint); font-size:.66rem; line-height:1.55; }
.support-main { min-height:0; overflow-y:auto; padding:28px clamp(22px,4vw,52px) 46px; }
.support-main > :deep(.ai-tutor) { margin-bottom:16px; }
.support-loading,.support-error { min-height:420px; display:grid; place-content:center; justify-items:center; gap:14px; text-align:center; color:var(--parchment-muted); }
.confusion-quote { padding:13px 16px; border-left:2px solid var(--accent-amber); background:rgba(176,138,62,.055); }
.confusion-quote blockquote { margin:5px 0 0; color:var(--parchment-muted); font-size:.86rem; }
.diagnostic-card { margin-top:18px; padding:clamp(20px,3vw,34px); border:1px solid rgba(92,122,138,.34); background:linear-gradient(135deg,rgba(92,122,138,.08),rgba(255,255,255,.012)); }
.diagnostic-card__head { display:flex; justify-content:space-between; color:#88aab7; font-size:.68rem; }
.diagnostic-card__head em { color:var(--parchment-faint); font-style:normal; }
.diagnostic-card h3 { margin:15px 0; max-width:820px; font-size:1.22rem; font-weight:560; line-height:1.6; }
.diagnostic-card textarea { width:100%; min-height:150px; resize:vertical; padding:13px; color:var(--parchment); border:1px solid var(--line-strong); background:#0d0f0d; font-family:var(--font-body); font-size:.9rem; line-height:1.65; }
.diagnostic-card__actions { display:flex; justify-content:space-between; align-items:center; gap:14px; margin-top:12px; }
.diagnostic-card__actions span { color:var(--parchment-faint); font-size:.64rem; }
.diagnostic-card__actions button,.next-action-note button { padding:10px 16px; color:#dce9e4; border:1px solid #7895a2; background:rgba(92,122,138,.12); font-family:var(--font-display); cursor:pointer; }
.diagnostic-card__actions button:disabled { opacity:.35; cursor:not-allowed; }
.support-inline-error { color:#e4ad9d; font-size:.74rem; }
.diagnosis-strip { display:flex; gap:13px; align-items:center; margin-top:18px; padding:15px; border:1px solid rgba(122,153,98,.4); background:rgba(122,153,98,.06); }
.diagnosis-strip.fallback { border-color:rgba(176,138,62,.45); background:rgba(176,138,62,.06); }
.diagnosis-strip__seal { width:40px; height:40px; display:grid; place-items:center; flex:0 0 auto; color:#dce8d4; border:1px solid currentColor; font-family:var(--font-display); transform:rotate(-3deg); }
.diagnosis-strip h3 { margin:1px 0; font-size:1rem; font-weight:590; }
.diagnosis-strip div > span { color:var(--parchment-dim); font-size:.7rem; }
.layer-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin-top:14px; }
.layer-card { position:relative; min-height:170px; padding:17px; border:1px solid var(--line); background:rgba(255,255,255,.016); }
.layer-card::before { content:""; position:absolute; left:0; top:0; bottom:0; width:2px; background:#7895a2; }
.layer-card--application::before { background:var(--accent-amber); }
.layer-card--dispute::before { background:var(--accent); }
.layer-card header { display:flex; gap:9px; align-items:center; }
.layer-card header span { color:#88aab7; font-size:.62rem; }
.layer-card h3 { font-size:.98rem; font-weight:600; }
.layer-card > p { color:var(--parchment-muted); font-size:.8rem; line-height:1.65; }
.citation-stack { display:grid; gap:7px; margin-top:10px; }
.citation-stack blockquote { margin:0; padding:8px 9px; border-left:1px solid var(--accent-amber); background:rgba(176,138,62,.045); }
.citation-stack cite { display:block; color:var(--accent-amber); font-size:.68rem; font-style:normal; }
.citation-stack span { color:var(--parchment-dim); font-size:.68rem; line-height:1.5; }
.next-action-note { display:flex; justify-content:space-between; align-items:center; gap:15px; margin-top:14px; padding:15px; border:1px solid rgba(92,122,138,.35); background:rgba(92,122,138,.04); }
.next-action-note h3 { font-size:.9rem; font-weight:550; }
.teacher-review-note { padding:10px; color:#deb28e; border-left:2px solid var(--accent); background:rgba(196,71,27,.06); font-size:.72rem; }
@media(max-width:820px){.support-layer{padding:0}.support-sheet{max-height:100vh;height:100%}.support-head{grid-template-columns:1fr 38px}.support-status{display:none}.support-body{display:block;overflow-y:auto}.support-rail{display:flex;gap:8px;overflow-x:auto;border-right:0;border-bottom:1px solid var(--line-strong)}.support-step{min-width:150px}.support-step::after{display:none}.support-boundary{min-width:220px;margin:0}.support-main{overflow:visible}.layer-grid{display:block}.layer-card{margin-bottom:10px}.diagnostic-card__actions,.next-action-note{align-items:flex-start;flex-direction:column}}
</style>
