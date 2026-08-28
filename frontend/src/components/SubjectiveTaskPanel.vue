<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { api } from "../lib/api";
import type { SubjectiveAttempt, SubjectiveTask } from "../lib/types";

const props = defineProps<{ phase: "prestudy" | "review" }>();
const emit = defineEmits<{ close: [] }>();

const loading = ref(true);
const submitting = ref(false);
const error = ref("");
const tasks = ref<SubjectiveTask[]>([]);
const history = ref<SubjectiveAttempt[]>([]);
const historyPrivacy = ref("");
const filter = ref<"all" | "short_answer" | "role_reversal">("all");
const selectedId = ref("");
const responseText = ref("");
const confidence = ref<number | null>(3);
const attemptId = ref("");
const attempt = ref<SubjectiveAttempt | null>(null);

const STATUS_LABELS: Record<string, string> = {
  needs_teacher_review: "等待教师",
  teacher_approved: "教师批准",
  revision_requested: "退回修订",
  teacher_rejected: "教师拒绝",
};

const DECISION_LABELS: Record<string, string> = {
  approve: "批准为形成性证据",
  request_revision: "退回修订",
  reject: "拒绝本次稿件",
};

function clientId(): string {
  const id = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `subjective-${id}`;
}

const visibleTasks = computed(() =>
  filter.value === "all" ? tasks.value : tasks.value.filter((task) => task.task_type === filter.value),
);
const selectedTask = computed(() => tasks.value.find((task) => task.task_id === selectedId.value) ?? null);
const charCount = computed(() => responseText.value.trim().length);
const withinLength = computed(() => {
  const task = selectedTask.value;
  return Boolean(task && charCount.value >= task.response_constraints.min_characters && charCount.value <= task.response_constraints.max_characters);
});
const canSubmit = computed(() => withinLength.value && !submitting.value && !attempt.value);
const reviewedCount = computed(() => history.value.filter((row) => row.teacher_review).length);
const revisionCount = computed(() => history.value.filter((row) => row.status === "revision_requested").length);
const contextRows = computed(() => {
  const context = selectedTask.value?.context_public ?? {};
  const rows: Array<{ label: string; value: string }> = [];
  for (const [key, value] of Object.entries(context)) {
    if (value === null || value === undefined || value === "") continue;
    const text = Array.isArray(value)
      ? value.map((item) => typeof item === "string" ? item : JSON.stringify(item)).join("；")
      : typeof value === "object" ? JSON.stringify(value) : String(value);
    rows.push({ label: key, value: text });
  }
  return rows.slice(0, 6);
});

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [catalogResult, historyResult] = await Promise.all([
      api.subjectiveCatalog(props.phase),
      api.subjectiveAttemptHistory(props.phase),
    ]);
    tasks.value = catalogResult.tasks;
    history.value = historyResult.attempts;
    historyPrivacy.value = historyResult.privacy;
    const latestTeacherResult = history.value.find((row) => row.teacher_review);
    if (latestTeacherResult) openHistory(latestTeacherResult);
    else selectTask(catalogResult.tasks[0] ?? null);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    loading.value = false;
  }
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

function decisionLabel(decision: string): string {
  return DECISION_LABELS[decision] ?? decision;
}

function selectTask(task: SubjectiveTask | null): void {
  selectedId.value = task?.task_id ?? "";
  responseText.value = "";
  confidence.value = 3;
  attempt.value = null;
  attemptId.value = clientId();
  error.value = "";
}

function openHistory(row: SubjectiveAttempt): void {
  selectedId.value = row.task.task_id;
  responseText.value = row.response_text;
  confidence.value = row.confidence ?? 3;
  attemptId.value = row.attempt_id;
  attempt.value = row;
  error.value = "";
}

function startRevision(row: SubjectiveAttempt): void {
  selectedId.value = row.task.task_id;
  responseText.value = row.response_text;
  confidence.value = row.confidence ?? 3;
  attemptId.value = clientId();
  attempt.value = null;
  error.value = "";
}

async function submit(): Promise<void> {
  const task = selectedTask.value;
  if (!task || !canSubmit.value) return;
  submitting.value = true;
  error.value = "";
  try {
    const result = await api.submitSubjectiveAttempt({
      attempt_id: attemptId.value,
      task_id: task.task_id,
      task_version: task.content_sha256,
      phase: props.phase,
      response_text: responseText.value.trim(),
      confidence: confidence.value,
    });
    attempt.value = result.attempt;
    history.value = [
      result.attempt,
      ...history.value.filter((row) => row.attempt_id !== result.attempt.attempt_id),
    ];
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    submitting.value = false;
  }
}

watch(filter, () => {
  if (!visibleTasks.value.some((task) => task.task_id === selectedId.value)) {
    selectTask(visibleTasks.value[0] ?? null);
  }
});

onMounted(() => void load());
</script>

<template>
  <div class="subjective-layer">
    <section class="subjective-board" role="dialog" aria-modal="true" aria-label="刑法主观论证训练">
      <header class="subjective-head">
        <div class="subjective-brand">
          <span class="subjective-seal">论</span>
          <div><p class="subjective-kicker mono">ARGUMENT DRAFT · TEACHER REVIEW</p><h2>刑法主观论证稿</h2></div>
        </div>
        <div class="subjective-summary mono">
          <span>13 个任务</span><span>{{ reviewedCount }} 份教师结论</span><span>{{ revisionCount }} 份待修订</span>
        </div>
        <button class="subjective-close" aria-label="关闭主观论证训练" @click="emit('close')">×</button>
      </header>

      <div v-if="loading" class="subjective-loading"><span class="subjective-seal">阅</span><p>正在读取主观任务与法源版本……</p></div>
      <div v-else class="subjective-body">
        <aside class="subjective-index">
          <div class="index-title"><p class="subjective-kicker mono">TASK FOLIOS</p><h3>任务稿签</h3></div>
          <div class="subjective-filter">
            <button :class="{ active: filter === 'all' }" @click="filter = 'all'">全部</button>
            <button :class="{ active: filter === 'short_answer' }" @click="filter = 'short_answer'">知识短答</button>
            <button :class="{ active: filter === 'role_reversal' }" @click="filter = 'role_reversal'">角色互换</button>
          </div>
          <div class="subjective-list">
            <button v-for="(task, index) in visibleTasks" :key="task.task_id" :class="{ active: task.task_id === selectedId }" @click="selectTask(task)">
              <span class="mono">{{ String(index + 1).padStart(2, "0") }}</span>
              <div><strong>{{ task.knowledge_names.join(" / ") }}</strong><small>{{ task.task_type === "role_reversal" ? "角色互换" : "知识短答" }} · 难度{{ task.difficulty }}/3</small></div>
            </button>
          </div>
          <p class="index-boundary">AI反馈只帮助修改稿件。低置信度会弃权；任何长期证据都必须经过任课教师复核。</p>
          <section class="history-index">
            <div class="history-index__head">
              <div><p class="subjective-kicker mono">MY REVIEW LEDGER</p><h3>我的复核台账</h3></div>
              <span class="mono">{{ history.length }}</span>
            </div>
            <div v-if="history.length" class="history-list">
              <button
                v-for="row in history"
                :key="row.attempt_id"
                :class="['history-row', `history-row--${row.status}`, { active: attempt?.attempt_id === row.attempt_id }]"
                @click="openHistory(row)"
              >
                <span>{{ row.teacher_review ? (row.teacher_review.decision === "approve" ? "准" : row.teacher_review.decision === "request_revision" ? "改" : "止") : "候" }}</span>
                <div>
                  <strong>{{ row.task.knowledge_names.join(" / ") }}</strong>
                  <small>{{ statusLabel(row.status) }} · {{ row.phase === "prestudy" ? "课前" : "课后" }}</small>
                </div>
              </button>
            </div>
            <p v-else class="history-empty">尚无主观稿件。首次提交后会在此保留AI反馈和教师结论。</p>
            <p class="history-privacy">{{ historyPrivacy }}</p>
          </section>
        </aside>

        <main v-if="selectedTask" class="draft-main">
          <section class="task-brief">
            <div><p class="subjective-kicker mono">{{ selectedTask.task_type.toUpperCase() }} · {{ selectedTask.content_sha256.slice(0, 10) }}</p><h3>{{ selectedTask.knowledge_names.join(" / ") }}</h3></div>
            <span>{{ props.phase === "prestudy" ? "课前预习" : "课后复习" }}</span>
          </section>
          <section class="task-prompt"><p class="subjective-kicker mono">PROMPT</p><h3>{{ selectedTask.prompt }}</h3></section>

          <div class="draft-grid">
            <section class="draft-paper">
              <div class="paper-meta">
                <span>字数 {{ selectedTask.response_constraints.min_characters }}—{{ selectedTask.response_constraints.max_characters }}</span>
                <span v-if="selectedTask.response_constraints.citations_required">须使用《刑法》第X条明确引用</span>
              </div>
              <textarea v-model="responseText" :maxlength="selectedTask.response_constraints.max_characters" :disabled="Boolean(attempt)" placeholder="先写争点，再写规范条件；将事实逐项对应，最后说明边界或反方意见……"></textarea>
              <footer>
                <div class="confidence"><span class="mono">作答把握</span><button v-for="level in 5" :key="level" :class="{ active: confidence === level }" :disabled="Boolean(attempt)" @click="confidence = level">{{ level }}</button></div>
                <span :class="['char-count', { warn: !withinLength }]">{{ charCount }} 字</span>
                <button class="submit-draft" :disabled="!canSubmit" @click="submit">{{ submitting ? "形成性评阅中…" : "提交教师复核 →" }}</button>
              </footer>
              <p v-if="error" class="draft-error">{{ error }}</p>
            </section>

            <aside class="draft-evidence">
              <section><p class="subjective-kicker mono">GOVERNED SOURCES</p><h3>可引用法源</h3><div class="evidence-tags"><span v-for="evidence in selectedTask.evidence_refs_public" :key="evidence.evidence_id">{{ evidence.source_title }} {{ evidence.article_ref }}</span></div></section>
              <section v-if="contextRows.length"><p class="subjective-kicker mono">PUBLIC CONTEXT</p><h3>公开任务材料</h3><dl><div v-for="row in contextRows" :key="row.label"><dt>{{ row.label }}</dt><dd>{{ row.value }}</dd></div></dl></section>
            </aside>
          </div>

          <section v-if="attempt" :class="['formative-review', { abstained: attempt.ai_abstained }]">
            <header><span class="review-seal">{{ attempt.ai_abstained ? "弃" : "评" }}</span><div><p class="subjective-kicker mono">FORMATIVE ONLY · {{ attempt.status }}</p><h3>{{ attempt.ai_abstained ? "自动评阅已弃权，等待教师复核" : `AI形成性参考 ${(Number(attempt.ai_score) * 10).toFixed(1)}/10` }}</h3><span>置信度 {{ Math.round(attempt.ai_confidence * 100) }}% · 不更新掌握或正式成绩</span></div></header>
            <div v-if="attempt.ai_abstained" class="abstain-reason">{{ attempt.ai_feedback.abstain_reason || "未通过结构、引用或置信度门禁。" }}</div>
            <div class="feedback-columns"><section><h4>已做到</h4><ul><li v-for="item in attempt.ai_feedback.strengths" :key="item">{{ item }}</li><li v-if="!attempt.ai_feedback.strengths.length">等待教师判断</li></ul></section><section><h4>需修订</h4><ul><li v-for="item in attempt.ai_feedback.corrections" :key="item">{{ item }}</li></ul></section></div>
            <p class="revision-note"><b>建议改写：</b>{{ attempt.ai_feedback.suggested_revision }}</p>
            <footer><span>{{ attempt.citation_audit.valid_standard_count }}条标准Evidence引用通过</span><strong>教师复核队列已接收 · {{ attempt.student_ref ?? "匿名学生" }}</strong></footer>
          </section>

          <section v-if="attempt?.teacher_review" :class="['teacher-return', `teacher-return--${attempt.teacher_review.decision}`]">
            <header>
              <span class="teacher-return__seal">{{ attempt.teacher_review.decision === "approve" ? "准" : attempt.teacher_review.decision === "request_revision" ? "改" : "止" }}</span>
              <div>
                <p class="subjective-kicker mono">HUMAN-IN-THE-LOOP · {{ attempt.status }}</p>
                <h3>{{ decisionLabel(attempt.teacher_review.decision) }}</h3>
                <span>教师结论与AI建议分开记录 · 不是正式课程成绩</span>
              </div>
            </header>
            <div v-if="attempt.teacher_review.decision === 'approve'" class="teacher-verdict-strip mono">
              <span>教师形成性评分 {{ ((attempt.teacher_review.teacher_score ?? 0) * 10).toFixed(1) }}/10</span>
              <span>知识状态 {{ attempt.teacher_review.knowledge_status }}</span>
              <span>已进入保守证据画像</span>
            </div>
            <blockquote>{{ attempt.teacher_review.feedback || "教师未填写补充意见。" }}</blockquote>
            <div v-if="attempt.teacher_review.error_tags.length" class="teacher-error-tags">
              <span v-for="tag in attempt.teacher_review.error_tags" :key="tag">{{ tag }}</span>
            </div>
            <footer>
              <span v-if="attempt.teacher_review.learning_event_id" class="mono">Evidence {{ attempt.teacher_review.learning_event_id }}</span>
              <span v-else>本次决定未生成画像事件</span>
              <button v-if="attempt.teacher_review.decision === 'request_revision'" @click="startRevision(attempt)">带入原文开始修订 →</button>
              <button v-else @click="selectTask(selectedTask)">开始同知识点新稿 →</button>
            </footer>
          </section>
        </main>
      </div>
    </section>
  </div>
</template>

<style scoped>
.subjective-layer{position:fixed;inset:0;z-index:1420;padding:20px;background:radial-gradient(circle at 20% 10%,rgba(176,138,62,.12),transparent 34%),rgba(4,3,2,.9);backdrop-filter:blur(12px)}
.subjective-board{height:100%;display:flex;flex-direction:column;overflow:hidden;color:var(--parchment);border:1px solid rgba(176,138,62,.38);background:linear-gradient(145deg,#18150f,#0d0c09 70%);box-shadow:0 38px 100px #000c}
.subjective-head{min-height:80px;display:grid;grid-template-columns:1fr auto 38px;align-items:center;gap:18px;padding:12px 18px 12px 24px;border-bottom:1px solid rgba(176,138,62,.28)}
.subjective-brand{display:flex;align-items:center;gap:14px}.subjective-seal,.review-seal{width:46px;height:46px;display:grid;place-items:center;color:#ead9b3;border:1px solid var(--accent-amber);box-shadow:inset 0 0 0 3px #271d0d;font-family:var(--font-display);font-weight:800;transform:rotate(-2deg)}
.subjective-kicker{margin:0 0 3px;color:var(--accent-amber);font-size:.63rem;letter-spacing:.17em}.subjective-brand h2{font-size:1.28rem;font-weight:650}.subjective-summary{display:flex;gap:7px}.subjective-summary span{padding:4px 7px;color:var(--parchment-dim);border:1px solid var(--line);font-size:.65rem}.subjective-close{width:36px;height:36px;color:var(--parchment-muted);border:1px solid var(--line-strong);background:transparent;font-size:1.35rem;cursor:pointer}
.subjective-loading{flex:1;display:grid;place-content:center;justify-items:center;gap:14px;color:var(--parchment-muted)}.subjective-body{flex:1;min-height:0;display:grid;grid-template-columns:255px minmax(0,1fr)}
.subjective-index{min-height:0;overflow-y:auto;padding:20px 14px;border-right:1px solid var(--line-strong);background:rgba(10,8,5,.65)}.index-title h3{font-size:1.05rem}.subjective-filter{display:flex;margin:13px 0;border:1px solid var(--line)}.subjective-filter button{flex:1;padding:7px 4px;color:var(--parchment-dim);border:0;border-right:1px solid var(--line);background:transparent;cursor:pointer}.subjective-filter button:last-child{border:0}.subjective-filter button.active{color:var(--parchment);background:rgba(176,138,62,.1)}
.subjective-list{display:grid;gap:5px}.subjective-list button{display:grid;grid-template-columns:27px 1fr;gap:7px;padding:9px 7px;color:var(--parchment-muted);text-align:left;border:1px solid transparent;background:transparent;cursor:pointer}.subjective-list button.active{color:var(--parchment);border-color:rgba(176,138,62,.35);background:linear-gradient(90deg,rgba(176,138,62,.09),transparent)}.subjective-list button>span{color:var(--parchment-faint);font-size:.62rem}.subjective-list button div{min-width:0;display:grid}.subjective-list strong{overflow:hidden;font-family:var(--font-display);font-size:.78rem;white-space:nowrap;text-overflow:ellipsis}.subjective-list small{color:var(--parchment-faint);font-size:.62rem}.index-boundary{margin:15px 4px;color:var(--parchment-faint);font-size:.68rem;line-height:1.55}
.history-index{margin-top:18px;padding-top:15px;border-top:1px solid rgba(176,138,62,.28)}.history-index__head{display:flex;align-items:flex-end;justify-content:space-between;gap:10px}.history-index__head h3{font-size:.95rem}.history-index__head>span{padding:3px 6px;color:var(--accent-amber);border:1px solid rgba(176,138,62,.35);font-size:.62rem}.history-list{display:grid;gap:5px;margin-top:10px}.history-row{display:grid;grid-template-columns:31px minmax(0,1fr);gap:8px;padding:8px;color:var(--parchment-muted);text-align:left;border:1px solid var(--line);background:rgba(255,255,255,.012);cursor:pointer}.history-row.active{border-color:rgba(176,138,62,.5);background:rgba(176,138,62,.065)}.history-row>span{width:27px;height:27px;display:grid;place-items:center;color:#d7bf87;border:1px solid currentColor;font-family:var(--font-display);font-size:.7rem}.history-row--teacher_approved>span{color:#b7cba9}.history-row--revision_requested>span{color:#e2b17e}.history-row--teacher_rejected>span{color:#d28d79}.history-row div{min-width:0;display:grid}.history-row strong{overflow:hidden;font-family:var(--font-display);font-size:.72rem;white-space:nowrap;text-overflow:ellipsis}.history-row small{color:var(--parchment-faint);font-size:.6rem}.history-empty,.history-privacy{color:var(--parchment-faint);font-size:.64rem;line-height:1.5}.history-privacy{padding-top:8px;border-top:1px dashed var(--line)}
.draft-main{min-height:0;overflow-y:auto;padding:25px clamp(22px,3vw,48px) 50px}.task-brief{display:flex;justify-content:space-between;align-items:flex-start;padding-bottom:15px;border-bottom:1px solid rgba(176,138,62,.3)}.task-brief h3{font-size:1.3rem}.task-brief>span{padding:5px 8px;color:var(--accent-amber);border:1px solid rgba(176,138,62,.4)}.task-prompt{padding:18px 0}.task-prompt h3{max-width:980px;font-size:1.05rem;font-weight:520;line-height:1.65}
.draft-grid{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(270px,.7fr);gap:14px}.draft-paper{border:1px solid var(--line-strong);background:rgba(255,255,255,.018)}.paper-meta{display:flex;gap:14px;padding:9px 13px;color:var(--parchment-faint);border-bottom:1px solid var(--line);font-size:.67rem}.draft-paper textarea{width:100%;min-height:310px;resize:vertical;padding:18px;color:var(--parchment);border:0;outline:0;background:repeating-linear-gradient(transparent 0,transparent 31px,rgba(236,228,211,.055) 32px);font-family:var(--font-body);font-size:.9rem;line-height:2.15}.draft-paper footer{display:flex;align-items:center;gap:12px;padding:12px;border-top:1px solid var(--line)}.confidence{display:flex;gap:5px;align-items:center}.confidence>span{margin-right:5px;color:var(--parchment-dim);font-size:.65rem}.confidence button{width:25px;height:24px;color:var(--parchment-dim);border:1px solid var(--line);background:transparent}.confidence button.active{color:#171108;background:var(--accent-amber)}.char-count{margin-left:auto;color:var(--accent-success);font-size:.7rem}.char-count.warn{color:var(--accent)}.submit-draft{padding:9px 15px;color:#f5ead5;border:1px solid var(--accent-amber);background:rgba(176,138,62,.12);font-family:var(--font-display);cursor:pointer}.submit-draft:disabled{opacity:.35}.draft-error{padding:0 13px;color:#e4ad9d}
.draft-evidence{display:grid;align-content:start;gap:12px}.draft-evidence section{padding:14px;border:1px solid var(--line);background:rgba(255,255,255,.014)}.draft-evidence h3{font-size:.9rem}.evidence-tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}.evidence-tags span{padding:4px 6px;color:#d9c18d;border:1px solid rgba(176,138,62,.3);font-size:.66rem}.draft-evidence dl{margin:8px 0}.draft-evidence dl div{padding:6px 0;border-bottom:1px solid var(--line)}.draft-evidence dt{color:var(--parchment-faint);font-size:.62rem}.draft-evidence dd{max-height:65px;overflow:hidden;margin:2px 0;color:var(--parchment-muted);font-size:.7rem;line-height:1.5}
.formative-review{margin-top:15px;padding:17px;border:1px solid rgba(122,153,98,.42);background:rgba(122,153,98,.045)}.formative-review.abstained{border-color:rgba(196,71,27,.45);background:rgba(196,71,27,.045)}.formative-review header{display:flex;gap:13px}.formative-review h3{font-size:1rem}.formative-review header div>span{color:var(--parchment-dim);font-size:.7rem}.formative-review.abstained .review-seal{color:#e5b49e;border-color:var(--accent)}.abstain-reason{margin:10px 0;padding:8px;color:#dfaa94;border-left:2px solid var(--accent);background:rgba(196,71,27,.07);font-size:.72rem}.feedback-columns{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:13px}.feedback-columns section{padding:10px;border:1px solid var(--line)}.feedback-columns h4{margin:0;font-family:var(--font-display)}.feedback-columns ul{margin:7px 0;padding-left:18px;color:var(--parchment-muted);font-size:.74rem}.revision-note{color:var(--parchment-muted);font-size:.76rem}.formative-review>footer{display:flex;justify-content:space-between;gap:12px;padding-top:10px;border-top:1px dashed var(--line);color:var(--parchment-faint);font-size:.67rem}.formative-review>footer strong{color:var(--accent-amber);font-weight:500}
.teacher-return{margin-top:15px;padding:17px;border:1px solid rgba(92,122,138,.5);background:linear-gradient(120deg,rgba(92,122,138,.075),rgba(255,255,255,.012));box-shadow:inset 3px 0 #7895a2}.teacher-return--approve{border-color:rgba(122,153,98,.5);box-shadow:inset 3px 0 var(--accent-success)}.teacher-return--request_revision{border-color:rgba(176,138,62,.5);box-shadow:inset 3px 0 var(--accent-amber)}.teacher-return--reject{border-color:rgba(196,71,27,.5);box-shadow:inset 3px 0 var(--accent)}.teacher-return header{display:flex;gap:13px;align-items:center}.teacher-return__seal{width:46px;height:46px;display:grid;place-items:center;color:#b9ced6;border:1px solid currentColor;box-shadow:inset 0 0 0 3px #131b1e;font-family:var(--font-display);font-weight:800;transform:rotate(2deg)}.teacher-return h3{font-size:1.04rem}.teacher-return header div>span{color:var(--parchment-dim);font-size:.7rem}.teacher-verdict-strip{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}.teacher-verdict-strip span{padding:4px 7px;color:#bfd2b2;border:1px solid rgba(122,153,98,.38);font-size:.64rem}.teacher-return blockquote{margin:12px 0;padding:10px 12px;color:var(--parchment-muted);border-left:2px solid #7895a2;background:rgba(0,0,0,.16);font-size:.76rem;line-height:1.65;white-space:pre-wrap}.teacher-error-tags{display:flex;flex-wrap:wrap;gap:6px}.teacher-error-tags span{padding:3px 6px;color:#e3b38e;border:1px solid rgba(196,123,74,.4);font-size:.65rem}.teacher-return footer{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:12px;padding-top:10px;border-top:1px dashed var(--line);color:var(--parchment-faint);font-size:.66rem}.teacher-return footer button{padding:7px 10px;color:#ead9b3;border:1px solid rgba(176,138,62,.45);background:rgba(176,138,62,.08);font-family:var(--font-display);cursor:pointer}
@media(max-width:900px){.subjective-layer{padding:0}.subjective-summary{display:none}.subjective-body{display:block;overflow-y:auto}.subjective-index,.draft-main{min-height:auto;overflow:visible;border-right:0}.subjective-list{grid-template-columns:repeat(2,minmax(0,1fr))}.history-list{grid-template-columns:repeat(2,minmax(0,1fr))}.draft-grid{display:block}.draft-evidence{margin-top:12px}.feedback-columns{display:block}.feedback-columns section{margin-bottom:8px}.draft-paper footer{align-items:flex-start;flex-wrap:wrap}.char-count{margin-left:0}.teacher-return footer{align-items:flex-start;flex-direction:column}.teacher-return footer button{width:100%}}
</style>
