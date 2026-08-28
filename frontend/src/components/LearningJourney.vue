<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { api } from "../lib/api";
import LearningSupportPanel from "./LearningSupportPanel.vue";
import type {
  AdaptiveKnowledgeEvidence,
  AdaptiveRecommendationItem,
  AdaptiveRecommendationResponse,
  ConfusionAnnotationPayload,
  KnowledgeCard,
  KnowledgeCatalogResponse,
  LearningSupportSeed,
  TaskAttemptFeedback,
  TaskAttemptPayload,
} from "../lib/types";

const emit = defineEmits<{ close: [] }>();

const catalog = ref<KnowledgeCatalogResponse | null>(null);
const adaptive = ref<AdaptiveRecommendationResponse | null>(null);
const loading = ref(true);
const refreshing = ref(false);
const loadError = ref("");
const actionError = ref("");
const phase = ref<"prestudy" | "review">("prestudy");
const selectedKnowledgeId = ref("");
const currentTask = ref<AdaptiveRecommendationItem | null>(null);
const selectedOptions = ref<string[]>([]);
const confidence = ref<number | null>(3);
const attemptId = ref("");
const taskStartedAt = ref(Date.now());
const submitting = ref(false);
const feedback = ref<TaskAttemptFeedback | null>(null);
const feedbackEventId = ref("");
const confusionOpen = ref(false);
const confusionType = ref<ConfusionAnnotationPayload["confusion_type"]>("fact_application");
const confusionNote = ref("");
const confusionId = ref("");
const confusionSaving = ref(false);
const confusionSaved = ref("");
const supportSeed = ref<LearningSupportSeed | null>(null);
const supportOpen = ref(false);

const REASON_LABELS: Record<string, string> = {
  case_evidence_indicates_weakness: "案件证据提示薄弱，优先补强",
  case_evidence_requires_reinforcement: "已有表现不稳定，安排巩固",
  provisional_mastery_spaced_review: "已有临时证据，安排复现确认",
  insufficient_repeated_evidence: "独立证据仍不足，继续采集",
  no_evidence_collect_diagnostic: "尚无课堂证据，先做覆盖诊断",
  learner_reported_confusion: "你主动标记了困惑，优先回应",
};

const CONFUSION_TYPES: Array<{
  value: ConfusionAnnotationPayload["confusion_type"];
  label: string;
}> = [
  { value: "concept_boundary", label: "概念边界" },
  { value: "rule_understanding", label: "规范理解" },
  { value: "fact_application", label: "事实适用" },
  { value: "evidence_use", label: "证据使用" },
  { value: "other", label: "其他困惑" },
];

function newClientId(prefix: string): string {
  const id = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${id}`;
}

const cards = computed(() => catalog.value?.knowledge_cards ?? []);
const recommendations = computed(() => adaptive.value?.recommendations ?? []);
const executableRecommendations = computed(() =>
  recommendations.value.filter((row) => Boolean(row.task_id && row.content_version && row.options)),
);
const selectedCard = computed(() =>
  cards.value.find((card) => card.knowledge_id === selectedKnowledgeId.value) ?? cards.value[0] ?? null,
);
const selectedState = computed(() => {
  const knowledgeId = selectedCard.value?.knowledge_id;
  return knowledgeId ? adaptive.value?.profile?.knowledge?.[knowledgeId] : undefined;
});
const selectedConfusion = computed(() => {
  const knowledgeId = selectedCard.value?.knowledge_id;
  return knowledgeId ? adaptive.value?.profile?.confusions?.[knowledgeId] : undefined;
});
const visibleQueue = computed(() => {
  if (!selectedKnowledgeId.value) return executableRecommendations.value;
  const scoped = executableRecommendations.value.filter(
    (row) => row.knowledge_id === selectedKnowledgeId.value,
  );
  return scoped.length ? scoped : executableRecommendations.value;
});
const observedKnowledgeCount = computed(() =>
  cards.value.filter((card) => {
    const state = adaptive.value?.profile?.knowledge?.[card.knowledge_id];
    return Number(state?.event_count ?? 0) > 0;
  }).length,
);
const coveragePercent = computed(() =>
  cards.value.length ? Math.round((observedKnowledgeCount.value / cards.value.length) * 100) : 0,
);
const adaptiveReady = computed(() =>
  adaptive.value?.source === "edubrain_adaptive_service" && executableRecommendations.value.length > 0,
);
const canSubmit = computed(() =>
  Boolean(
    adaptiveReady.value &&
    currentTask.value?.task_id &&
    currentTask.value?.content_version &&
    selectedOptions.value.length &&
    !feedback.value &&
    !submitting.value,
  ),
);

function knowledgeState(card: KnowledgeCard): AdaptiveKnowledgeEvidence | undefined {
  return adaptive.value?.profile?.knowledge?.[card.knowledge_id];
}

function stateLabel(state?: AdaptiveKnowledgeEvidence): string {
  if (!state?.event_count) return "待取证";
  if (state.evidence_status === "provisional") return "临时画像";
  if (state.latest === "mastered") return "本次掌握";
  if (state.latest === "partial") return "部分成立";
  if (state.latest === "missing") return "需要补强";
  return "证据不足";
}

function stateTone(state?: AdaptiveKnowledgeEvidence): string {
  if (!state?.event_count) return "idle";
  if (state.evidence_status === "provisional") return "provisional";
  if (state.latest === "mastered") return "mastered";
  if (state.latest === "partial") return "partial";
  if (state.latest === "missing") return "missing";
  return "idle";
}

function taskReason(task?: AdaptiveRecommendationItem | null): string {
  return REASON_LABELS[String(task?.reason_code ?? "")] ?? "根据当前学习证据排序";
}

function startTask(task: AdaptiveRecommendationItem): void {
  if (!task.task_id || !task.content_version || !task.options) return;
  currentTask.value = { ...task };
  selectedKnowledgeId.value = task.knowledge_id ?? selectedKnowledgeId.value;
  selectedOptions.value = [];
  confidence.value = 3;
  feedback.value = null;
  feedbackEventId.value = "";
  attemptId.value = newClientId("attempt");
  taskStartedAt.value = Date.now();
  actionError.value = "";
}

function selectKnowledge(card: KnowledgeCard): void {
  selectedKnowledgeId.value = card.knowledge_id;
  const next = executableRecommendations.value.find(
    (task) => task.knowledge_id === card.knowledge_id,
  );
  if (next && currentTask.value?.task_id !== next.task_id) startTask(next);
}

function toggleOption(key: string): void {
  if (feedback.value || submitting.value) return;
  const normalized = String(key).trim().toUpperCase();
  selectedOptions.value = selectedOptions.value.includes(normalized)
    ? selectedOptions.value.filter((value) => value !== normalized)
    : [...selectedOptions.value, normalized].sort();
}

function optionTone(key: string): string {
  const normalized = String(key).trim().toUpperCase();
  if (!feedback.value) return selectedOptions.value.includes(normalized) ? "selected" : "";
  if (feedback.value.correct_options.includes(normalized)) return "correct";
  if (selectedOptions.value.includes(normalized)) return "wrong";
  return "";
}

async function loadJourney(): Promise<void> {
  loading.value = true;
  loadError.value = "";
  try {
    catalog.value = await api.knowledgeCatalog();
    try {
      adaptive.value = await api.adaptiveRecommendations();
    } catch (error) {
      loadError.value = error instanceof Error ? error.message : String(error);
    }
    const first = executableRecommendations.value[0];
    if (first) startTask(first);
    else if (cards.value[0]) selectedKnowledgeId.value = cards.value[0].knowledge_id;
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

async function refreshRecommendations(): Promise<void> {
  refreshing.value = true;
  actionError.value = "";
  try {
    adaptive.value = await api.adaptiveRecommendations();
    if (!currentTask.value && executableRecommendations.value[0]) {
      startTask(executableRecommendations.value[0]);
    }
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    refreshing.value = false;
  }
}

async function submitAttempt(): Promise<void> {
  const task = currentTask.value;
  if (!task?.task_id || !task.content_version || !canSubmit.value) return;
  submitting.value = true;
  actionError.value = "";
  const payload: TaskAttemptPayload = {
    schema_version: "criminal-law-task-attempt-v1",
    attempt_id: attemptId.value,
    task_id: task.task_id,
    content_version: task.content_version,
    phase: phase.value,
    selected_options: [...selectedOptions.value],
    submitted_at: new Date().toISOString(),
    response_time_ms: Math.max(0, Date.now() - taskStartedAt.value),
    confidence: confidence.value,
    hint_count: 0,
    answer_revealed_before_submit: false,
  };
  try {
    const result = await api.submitTaskAttempt(payload);
    feedback.value = result.feedback;
    feedbackEventId.value = result.learning_event.event_id;
    adaptive.value = result;
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    submitting.value = false;
  }
}

function nextTask(): void {
  const scoped = visibleQueue.value.find(
    (task) => task.task_id !== currentTask.value?.task_id,
  );
  const next = scoped ?? executableRecommendations.value[0];
  if (next) startTask(next);
  else currentTask.value = null;
}

async function saveConfusion(): Promise<void> {
  const card = selectedCard.value;
  if (!card || !confusionNote.value.trim() || confusionSaving.value) return;
  confusionSaving.value = true;
  actionError.value = "";
  if (!confusionId.value) confusionId.value = newClientId("confusion");
  const payload: ConfusionAnnotationPayload = {
    schema_version: "criminal-law-confusion-annotation-v1",
    annotation_id: confusionId.value,
    phase: phase.value,
    task_id: currentTask.value?.knowledge_id === card.knowledge_id
      ? currentTask.value?.task_id
      : undefined,
    knowledge_id: card.knowledge_id,
    confusion_type: confusionType.value,
    note: confusionNote.value.trim(),
    request_help: true,
    submitted_at: new Date().toISOString(),
  };
  try {
    const result = await api.submitConfusion(payload);
    adaptive.value = result;
    confusionSaved.value = "困惑已进入证据账本，后续任务会优先回应。";
    supportSeed.value = {
      knowledgeId: card.knowledge_id,
      knowledgeName: card.canonical_name,
      taskId: payload.task_id,
      phase: phase.value,
      confusionType: confusionType.value,
      note: payload.note,
    };
    confusionNote.value = "";
    confusionId.value = "";
    confusionOpen.value = false;
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    confusionSaving.value = false;
  }
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") emit("close");
}

watch(phase, () => {
  if (currentTask.value) startTask(currentTask.value);
  confusionSaved.value = "";
});

onMounted(() => {
  window.addEventListener("keydown", handleKeydown);
  void loadJourney();
});
onUnmounted(() => window.removeEventListener("keydown", handleKeydown));
</script>

<template>
  <div class="journey-layer">
    <section class="journey" role="dialog" aria-modal="true" aria-label="刑法自主学习卷宗">
      <header class="journey__head">
        <div class="journey__brand">
          <span class="journey__seal">学</span>
          <div>
            <p class="journey__kicker mono">PERSONAL DOCKET · CRIMINAL LAW</p>
            <h2>刑法自主学习卷宗</h2>
          </div>
        </div>

        <div class="phase-switch" aria-label="学习阶段">
          <button :class="{ active: phase === 'prestudy' }" @click="phase = 'prestudy'">
            <span class="mono">01</span> 课前预习
          </button>
          <button :class="{ active: phase === 'review' }" @click="phase = 'review'">
            <span class="mono">02</span> 课后复习
          </button>
        </div>

        <div class="journey__summary mono">
          <span><b>{{ adaptive?.profile?.eligible_event_count ?? 0 }}</b> 合格证据</span>
          <span><b>{{ observedKnowledgeCount }}</b>/{{ cards.length || 10 }} 已观察</span>
          <span><b>{{ coveragePercent }}%</b> 覆盖</span>
        </div>
        <button class="journey__close" aria-label="关闭自主学习" @click="emit('close')">×</button>
      </header>

      <div v-if="loading" class="journey__loading">
        <span class="loading-seal">卷</span>
        <p>正在调取你的课程卷宗与下一任务……</p>
      </div>

      <div v-else class="journey__body">
        <aside class="index-pane">
          <div class="pane-head">
            <div>
              <p class="pane-kicker mono">COURSE INDEX</p>
              <h3>知识卷宗</h3>
            </div>
            <span class="pane-count mono">{{ cards.length }} 卷</span>
          </div>
          <div class="coverage-track" aria-label="知识覆盖进度">
            <span :style="{ width: `${coveragePercent}%` }"></span>
          </div>
          <ol class="knowledge-list">
            <li v-for="(card, index) in cards" :key="card.knowledge_id">
              <button
                :class="[
                  'knowledge-tab',
                  `knowledge-tab--${stateTone(knowledgeState(card))}`,
                  { active: card.knowledge_id === selectedCard?.knowledge_id },
                ]"
                @click="selectKnowledge(card)"
              >
                <span class="knowledge-tab__no mono">{{ String(index + 1).padStart(2, "0") }}</span>
                <span class="knowledge-tab__copy">
                  <small>{{ card.chapter.replace("刑法总论·", "").replace("刑法分论·", "") }}</small>
                  <strong>{{ card.canonical_name }}</strong>
                  <em>{{ stateLabel(knowledgeState(card)) }}</em>
                </span>
                <span class="knowledge-tab__mark"></span>
              </button>
            </li>
          </ol>
          <p class="index-note">
            状态来自形成性证据。至少3次事件且覆盖2道任务，才标记为“临时画像”。
          </p>
        </aside>

        <main class="task-pane">
          <div v-if="loadError && !catalog" class="empty-state empty-state--error">
            <span>!</span>
            <h3>卷宗调取失败</h3>
            <p>{{ loadError }}</p>
            <button class="btn" @click="loadJourney">重新调取</button>
          </div>

          <template v-else>
            <section v-if="selectedCard" class="knowledge-brief reveal">
              <div class="knowledge-brief__head">
                <div>
                  <p class="pane-kicker mono">SELECTED DOCKET · {{ selectedCard.version }}</p>
                  <h3>{{ selectedCard.canonical_name }}</h3>
                </div>
                <span class="review-stamp">教师门禁</span>
              </div>
              <p class="knowledge-brief__objective">{{ selectedCard.learning_objective }}</p>
              <p class="knowledge-brief__summary">{{ selectedCard.summary }}</p>
              <div class="law-strip">
                <span class="law-strip__label mono">法源索引</span>
                <span v-for="article in selectedCard.law_article_refs" :key="article">
                  刑法{{ article }}
                </span>
                <span class="law-strip__evidence mono">
                  {{ selectedCard.standard_evidence_ids.length }} 条标准证据
                </span>
              </div>
            </section>

            <section v-if="currentTask" class="task-sheet reveal reveal-2">
              <header class="task-sheet__head">
                <div class="task-sheet__folio mono">
                  TASK {{ String(currentTask.rank ?? 1).padStart(2, "0") }}
                </div>
                <div class="task-sheet__meta">
                  <span>{{ phase === "prestudy" ? "预习诊断" : "复习取证" }}</span>
                  <span>{{ currentTask.cognitive_dimension || "理解" }}</span>
                  <span>难度 {{ currentTask.difficulty ?? 2 }}/3</span>
                </div>
              </header>
              <p class="task-sheet__reason">{{ taskReason(currentTask) }}</p>
              <h3 class="task-sheet__stem">{{ currentTask.stem }}</h3>
              <p class="task-sheet__instruction mono">选择你认为成立的全部选项 · 提交前可修改</p>

              <div class="option-list" role="group" aria-label="答题选项">
                <button
                  v-for="(text, key) in currentTask.options"
                  :key="key"
                  :class="['option-row', optionTone(String(key))]"
                  :aria-pressed="selectedOptions.includes(String(key))"
                  @click="toggleOption(String(key))"
                >
                  <span class="option-row__key mono">{{ key }}</span>
                  <span class="option-row__text">{{ text }}</span>
                  <span class="option-row__check">
                    <template v-if="feedback?.correct_options.includes(String(key))">✓</template>
                    <template v-else-if="feedback && selectedOptions.includes(String(key))">×</template>
                    <template v-else>{{ selectedOptions.includes(String(key)) ? "●" : "" }}</template>
                  </span>
                </button>
              </div>

              <div v-if="!feedback" class="task-sheet__controls">
                <div class="confidence">
                  <span class="mono">作答把握</span>
                  <button
                    v-for="level in 5"
                    :key="level"
                    :class="{ active: confidence === level }"
                    :aria-label="`把握程度 ${level}`"
                    @click="confidence = level"
                  >{{ level }}</button>
                </div>
                <div class="task-sheet__actions">
                  <button class="text-action" @click="confusionOpen = !confusionOpen">
                    标记困惑
                  </button>
                  <button class="submit-seal" :disabled="!canSubmit" @click="submitAttempt">
                    {{ submitting ? "判分中…" : "提交取证" }}
                  </button>
                </div>
              </div>

              <div v-if="actionError" class="action-error" role="alert">{{ actionError }}</div>

              <section
                v-if="feedback"
                :class="['feedback-sheet', feedback.correct ? 'feedback-sheet--correct' : 'feedback-sheet--wrong']"
              >
                <div class="feedback-sheet__verdict">
                  <span class="verdict-seal">{{ feedback.correct ? "正" : "补" }}</span>
                  <div>
                    <p class="mono">DETERMINISTIC VERDICT · {{ feedbackEventId.slice(0, 18) }}</p>
                    <h3>{{ feedback.correct ? "本次判断成立" : "本次证据尚需补强" }}</h3>
                    <span>
                      得分 {{ feedback.score }}/{{ feedback.max_score }} · 正确选项
                      {{ feedback.correct_options.join("、") }} · {{ stateLabel({ event_count: 1, latest: feedback.knowledge_status }) }}
                    </span>
                  </div>
                </div>
                <p class="feedback-sheet__rationale">{{ feedback.rationale }}</p>
                <ul v-if="feedback.triggered_misconceptions.length" class="misconceptions">
                  <li v-for="item in feedback.triggered_misconceptions" :key="item">{{ item }}</li>
                </ul>
                <div class="feedback-sheet__foot">
                  <span class="mono">证据包 {{ feedback.standard_evidence_ids.length }} 条 · 形成性反馈</span>
                  <button class="next-task" @click="nextTask">进入下一任务 →</button>
                </div>
              </section>
            </section>

            <section v-else class="empty-state">
              <span>阅</span>
              <h3>当前没有可执行任务</h3>
              <p v-if="adaptive?.status === 'fallback'">
                目前只有本地降级建议，私有判分服务未接通；系统不会在浏览器中暴露答案。
              </p>
              <p v-else>这一知识卷宗的任务已完成，刷新后可查看其他知识点。</p>
              <button class="btn" :disabled="refreshing" @click="refreshRecommendations">
                {{ refreshing ? "刷新中…" : "刷新下一任务" }}
              </button>
            </section>
          </template>
        </main>

        <aside class="ledger-pane">
          <section class="ledger-block">
            <div class="pane-head pane-head--tight">
              <div>
                <p class="pane-kicker mono">EVIDENCE LEDGER</p>
                <h3>证据账本</h3>
              </div>
              <button class="refresh-button" :disabled="refreshing" @click="refreshRecommendations">↻</button>
            </div>
            <div class="ledger-metrics">
              <div><b>{{ adaptive?.profile?.event_count ?? 0 }}</b><span>全部事件</span></div>
              <div><b>{{ adaptive?.profile?.eligible_event_count ?? 0 }}</b><span>合格证据</span></div>
              <div><b>{{ adaptive?.profile?.self_report_event_count ?? 0 }}</b><span>困惑自报</span></div>
            </div>
            <div v-if="selectedCard" class="selected-ledger">
              <p>{{ selectedCard.canonical_name }}</p>
              <strong :class="`tone--${stateTone(selectedState)}`">{{ stateLabel(selectedState) }}</strong>
              <dl>
                <div><dt>事件</dt><dd>{{ selectedState?.event_count ?? 0 }}/3</dd></div>
                <div><dt>不同任务</dt><dd>{{ selectedState?.task_count ?? 0 }}/2</dd></div>
                <div><dt>困惑</dt><dd>{{ selectedConfusion?.count ?? 0 }}</dd></div>
              </dl>
            </div>
            <p v-if="adaptive?.warning" class="ledger-warning">{{ adaptive.warning }}</p>
            <p v-if="loadError" class="ledger-warning">自适应服务：{{ loadError }}</p>
          </section>

          <section class="ledger-block ledger-block--queue">
            <p class="pane-kicker mono">NEXT ENTRIES · {{ executableRecommendations.length }}</p>
            <h3>任务序列</h3>
            <div class="queue-list">
              <button
                v-for="(task, index) in visibleQueue.slice(0, 6)"
                :key="task.task_id"
                :class="{ active: task.task_id === currentTask?.task_id }"
                @click="startTask(task)"
              >
                <span class="mono">{{ String(index + 1).padStart(2, "0") }}</span>
                <div>
                  <strong>{{ task.knowledge_name }}</strong>
                  <small>{{ taskReason(task) }}</small>
                </div>
              </button>
              <p v-if="!visibleQueue.length" class="queue-empty">暂无未完成任务。</p>
            </div>
          </section>

          <section class="ledger-block confusion-block">
            <div class="confusion-block__head">
              <div>
                <p class="pane-kicker mono">QUESTION SLIP</p>
                <h3>困惑便笺</h3>
              </div>
              <button @click="confusionOpen = !confusionOpen">{{ confusionOpen ? "收起" : "填写" }}</button>
            </div>
            <div v-if="confusionSaved" class="confusion-saved">
              <span>{{ confusionSaved }}</span>
              <button v-if="supportSeed" @click="supportOpen = true">开始分层解惑 →</button>
            </div>
            <template v-if="confusionOpen">
              <select v-model="confusionType" class="ledger-input">
                <option v-for="type in CONFUSION_TYPES" :key="type.value" :value="type.value">
                  {{ type.label }}
                </option>
              </select>
              <textarea
                v-model="confusionNote"
                class="ledger-input ledger-textarea"
                maxlength="2000"
                placeholder="具体写下你卡住的条件、事实或证据……"
              ></textarea>
              <button
                class="confusion-submit"
                :disabled="!confusionNote.trim() || confusionSaving"
                @click="saveConfusion"
              >{{ confusionSaving ? "归档中…" : "归入证据账本" }}</button>
            </template>
            <p v-else class="confusion-note">
              自报困惑会影响下一任务排序，但不会被当作答错或直接降低掌握状态。
            </p>
          </section>

          <section class="boundary-note">
            <span>边界</span>
            <p>当前画像是形成性、未校准证据，不是正式成绩或ORCDF掌握概率。</p>
          </section>
        </aside>
      </div>
      <LearningSupportPanel
        v-if="supportOpen && supportSeed"
        :seed="supportSeed"
        @close="supportOpen = false"
        @retry-task="supportOpen = false"
      />
    </section>
  </div>
</template>

<style scoped>
.journey-layer {
  position: fixed;
  inset: 0;
  z-index: 1200;
  padding: 18px;
  background:
    radial-gradient(circle at 15% 20%, rgba(196, 71, 27, 0.12), transparent 32%),
    rgba(5, 4, 3, 0.9);
  backdrop-filter: blur(12px);
}

.journey {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: var(--parchment);
  background:
    linear-gradient(90deg, rgba(255, 255, 255, 0.015) 1px, transparent 1px) 0 0 / 48px 48px,
    linear-gradient(180deg, #18140f, #0d0b08 65%);
  border: 1px solid rgba(176, 138, 62, 0.32);
  box-shadow: 0 40px 100px rgba(0, 0, 0, 0.72), inset 0 1px rgba(255, 245, 220, 0.04);
}

.journey__head {
  min-height: 82px;
  display: grid;
  grid-template-columns: minmax(300px, 1fr) auto minmax(280px, 1fr) 38px;
  align-items: center;
  gap: 22px;
  padding: 12px 18px 12px 24px;
  border-bottom: 1px solid rgba(176, 138, 62, 0.28);
  background: linear-gradient(180deg, rgba(37, 30, 21, 0.98), rgba(19, 16, 11, 0.98));
}

.journey__brand { display: flex; align-items: center; gap: 14px; }
.journey__seal,
.loading-seal {
  width: 46px;
  height: 46px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  color: #f5e9d2;
  font-family: "Noto Serif SC", var(--font-display);
  font-size: 1.15rem;
  font-weight: 800;
  border: 1px solid rgba(196, 71, 27, 0.8);
  box-shadow: inset 0 0 0 3px #24130c, 0 0 0 1px rgba(196, 71, 27, 0.25);
  background: #8f3216;
  transform: rotate(-2deg);
}
.journey__kicker,
.pane-kicker { margin: 0 0 3px; color: var(--accent-amber); font-size: 0.64rem; letter-spacing: 0.18em; }
.journey__brand h2 { font-size: 1.28rem; font-weight: 650; letter-spacing: 0.04em; }

.phase-switch {
  display: flex;
  border: 1px solid var(--line-strong);
  background: rgba(0, 0, 0, 0.22);
}
.phase-switch button {
  padding: 10px 16px;
  color: var(--parchment-dim);
  border: 0;
  border-right: 1px solid var(--line);
  background: transparent;
  font-family: var(--font-display);
  cursor: pointer;
}
.phase-switch button:last-child { border-right: 0; }
.phase-switch button span { margin-right: 7px; font-size: 0.66rem; }
.phase-switch button.active { color: #f1e8d6; background: rgba(176, 138, 62, 0.15); box-shadow: inset 0 -2px var(--accent-amber); }

.journey__summary { display: flex; justify-content: flex-end; gap: 18px; color: var(--parchment-dim); font-size: 0.72rem; }
.journey__summary span { display: flex; flex-direction: column; align-items: flex-end; }
.journey__summary b { color: var(--parchment); font-size: 1rem; font-weight: 500; }
.journey__close {
  width: 36px;
  height: 36px;
  color: var(--parchment-muted);
  border: 1px solid var(--line-strong);
  background: transparent;
  font-size: 1.35rem;
  cursor: pointer;
}
.journey__close:hover { color: #fff; border-color: var(--accent); }

.journey__loading {
  flex: 1;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 18px;
  color: var(--parchment-muted);
}
.journey__loading .loading-seal { animation: docket-pulse 1.4s ease-in-out infinite; }

.journey__body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 272px minmax(460px, 1fr) 318px;
}

.index-pane,
.ledger-pane,
.task-pane { min-height: 0; overflow-y: auto; }
.index-pane {
  padding: 18px 14px 16px;
  border-right: 1px solid var(--line-strong);
  background: rgba(12, 10, 7, 0.68);
}
.ledger-pane {
  padding: 18px 16px;
  border-left: 1px solid var(--line-strong);
  background: rgba(12, 10, 7, 0.7);
}
.task-pane { padding: 24px clamp(22px, 3vw, 52px) 50px; }

.pane-head { display: flex; align-items: flex-end; justify-content: space-between; margin-bottom: 13px; }
.pane-head--tight { align-items: center; }
.pane-head h3,
.ledger-block h3 { font-size: 1.08rem; font-weight: 600; }
.pane-count { color: var(--parchment-dim); font-size: 0.7rem; }
.coverage-track { height: 2px; margin-bottom: 15px; background: var(--line-strong); }
.coverage-track span { display: block; height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent-amber)); transition: width 0.5s ease; }

.knowledge-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 5px; }
.knowledge-tab {
  width: 100%;
  min-height: 59px;
  display: grid;
  grid-template-columns: 31px 1fr 7px;
  align-items: center;
  gap: 9px;
  padding: 7px 9px 7px 5px;
  color: var(--parchment-muted);
  text-align: left;
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
  transition: 0.16s ease;
}
.knowledge-tab:hover { background: rgba(236, 228, 211, 0.025); border-color: var(--line); }
.knowledge-tab.active { color: var(--parchment); border-color: rgba(176, 138, 62, 0.38); background: linear-gradient(90deg, rgba(176, 138, 62, 0.1), transparent); }
.knowledge-tab__no { color: var(--parchment-faint); font-size: 0.67rem; text-align: center; }
.knowledge-tab__copy { min-width: 0; display: grid; }
.knowledge-tab__copy small { overflow: hidden; color: var(--parchment-dim); font-size: 0.65rem; white-space: nowrap; text-overflow: ellipsis; }
.knowledge-tab__copy strong { overflow: hidden; font-family: var(--font-display); font-size: 0.88rem; font-weight: 580; white-space: nowrap; text-overflow: ellipsis; }
.knowledge-tab__copy em { color: var(--parchment-faint); font-size: 0.66rem; font-style: normal; }
.knowledge-tab__mark { width: 6px; height: 6px; border-radius: 50%; background: var(--parchment-faint); }
.knowledge-tab--mastered .knowledge-tab__mark { background: var(--accent-success); }
.knowledge-tab--partial .knowledge-tab__mark { background: var(--accent-amber); }
.knowledge-tab--missing .knowledge-tab__mark { background: var(--accent); }
.knowledge-tab--provisional .knowledge-tab__mark { background: #88aab7; box-shadow: 0 0 0 3px rgba(92, 122, 138, 0.17); }
.index-note { margin: 16px 5px 0; color: var(--parchment-faint); font-size: 0.7rem; line-height: 1.6; }

.knowledge-brief {
  position: relative;
  margin-bottom: 18px;
  padding: 19px 22px 17px;
  border-top: 1px solid rgba(176, 138, 62, 0.52);
  border-bottom: 1px solid var(--line);
  background: linear-gradient(110deg, rgba(176, 138, 62, 0.07), transparent 65%);
}
.knowledge-brief::before { content: ""; position: absolute; left: 0; top: 18px; bottom: 18px; width: 2px; background: var(--accent-amber); }
.knowledge-brief__head { display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; }
.knowledge-brief h3 { font-size: 1.34rem; font-weight: 620; }
.review-stamp { padding: 5px 8px; color: rgba(196, 71, 27, 0.9); border: 1px solid rgba(196, 71, 27, 0.46); font-family: var(--font-display); font-size: 0.72rem; transform: rotate(2deg); }
.knowledge-brief__objective { margin: 11px 0 4px; color: var(--parchment); font-size: 0.94rem; }
.knowledge-brief__summary { margin: 0; color: var(--parchment-muted); font-size: 0.84rem; }
.law-strip { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 13px; }
.law-strip > span { padding: 3px 7px; color: var(--parchment-muted); border: 1px solid var(--line); font-size: 0.68rem; }
.law-strip__label { color: var(--accent-amber) !important; border-color: rgba(176, 138, 62, 0.32) !important; }
.law-strip__evidence { margin-left: auto; color: var(--parchment-dim) !important; border: 0 !important; }

.task-sheet {
  position: relative;
  padding: clamp(21px, 3vw, 34px);
  border: 1px solid rgba(236, 228, 211, 0.15);
  background:
    linear-gradient(180deg, rgba(236, 228, 211, 0.035), rgba(236, 228, 211, 0.01)),
    #15120d;
  box-shadow: 0 30px 70px -48px #000;
}
.task-sheet::after { content: ""; position: absolute; inset: 8px; pointer-events: none; border: 1px solid rgba(236, 228, 211, 0.035); }
.task-sheet__head { position: relative; z-index: 1; display: flex; justify-content: space-between; gap: 16px; }
.task-sheet__folio { color: var(--accent); font-size: 0.72rem; letter-spacing: 0.12em; }
.task-sheet__meta { display: flex; gap: 8px; }
.task-sheet__meta span { padding: 3px 7px; color: var(--parchment-dim); border: 1px solid var(--line); font-size: 0.68rem; }
.task-sheet__reason { position: relative; z-index: 1; margin: 17px 0 9px; color: var(--accent-amber); font-size: 0.78rem; }
.task-sheet__stem { position: relative; z-index: 1; max-width: 900px; font-size: clamp(1.08rem, 1.45vw, 1.36rem); font-weight: 520; line-height: 1.65; }
.task-sheet__instruction { position: relative; z-index: 1; margin: 9px 0 16px; color: var(--parchment-faint); font-size: 0.68rem; }
.option-list { position: relative; z-index: 1; display: grid; gap: 8px; }
.option-row {
  width: 100%;
  min-height: 50px;
  display: grid;
  grid-template-columns: 34px 1fr 24px;
  align-items: center;
  gap: 12px;
  padding: 8px 13px;
  color: var(--parchment-muted);
  text-align: left;
  border: 1px solid var(--line);
  background: rgba(0, 0, 0, 0.16);
  cursor: pointer;
  transition: 0.16s ease;
}
.option-row:hover { color: var(--parchment); border-color: rgba(176, 138, 62, 0.42); transform: translateX(2px); }
.option-row.selected { color: var(--parchment); border-color: var(--accent-amber); background: rgba(176, 138, 62, 0.1); }
.option-row.correct { color: #dce8d4; border-color: rgba(122, 153, 98, 0.6); background: rgba(122, 153, 98, 0.1); }
.option-row.wrong { color: #e0b4a6; border-color: rgba(196, 71, 27, 0.6); background: rgba(196, 71, 27, 0.1); }
.option-row__key { width: 29px; height: 29px; display: grid; place-items: center; color: var(--accent-amber); border: 1px solid currentColor; }
.option-row__text { font-size: 0.88rem; line-height: 1.5; }
.option-row__check { color: var(--parchment); text-align: center; }
.task-sheet__controls { position: relative; z-index: 1; display: flex; align-items: center; justify-content: space-between; gap: 18px; margin-top: 20px; padding-top: 15px; border-top: 1px dashed var(--line-strong); }
.confidence { display: flex; align-items: center; gap: 6px; color: var(--parchment-dim); font-size: 0.7rem; }
.confidence > span { margin-right: 5px; }
.confidence button { width: 26px; height: 25px; color: var(--parchment-dim); border: 1px solid var(--line); background: transparent; cursor: pointer; }
.confidence button.active { color: var(--ink-900); border-color: var(--accent-amber); background: var(--accent-amber); }
.task-sheet__actions { display: flex; align-items: center; gap: 10px; }
.text-action { color: var(--parchment-muted); border: 0; border-bottom: 1px solid var(--line-strong); background: transparent; cursor: pointer; }
.submit-seal,
.next-task,
.confusion-submit {
  padding: 10px 17px;
  color: #fff6e6;
  border: 1px solid var(--accent);
  background: linear-gradient(180deg, #c64a1c, #8f3014);
  font-family: var(--font-display);
  cursor: pointer;
}
.submit-seal:disabled,
.confusion-submit:disabled { opacity: 0.35; cursor: not-allowed; }
.action-error { position: relative; z-index: 1; margin-top: 13px; padding: 9px 11px; color: #e4ad9d; border-left: 2px solid var(--accent); background: rgba(196, 71, 27, 0.08); font-size: 0.78rem; }

.feedback-sheet { position: relative; z-index: 1; margin-top: 19px; padding: 18px; border: 1px solid var(--line-strong); background: rgba(0, 0, 0, 0.18); animation: verdict-in 0.46s ease both; }
.feedback-sheet--correct { border-color: rgba(122, 153, 98, 0.45); }
.feedback-sheet--wrong { border-color: rgba(196, 71, 27, 0.45); }
.feedback-sheet__verdict { display: flex; align-items: center; gap: 13px; }
.verdict-seal { width: 42px; height: 42px; display: grid; place-items: center; flex: 0 0 auto; color: #e9f0e4; border: 1px solid var(--accent-success); font-family: var(--font-display); font-size: 1.15rem; transform: rotate(-3deg); }
.feedback-sheet--wrong .verdict-seal { color: #f1d0c6; border-color: var(--accent); }
.feedback-sheet__verdict p { margin: 0; color: var(--parchment-dim); font-size: 0.62rem; }
.feedback-sheet__verdict h3 { margin: 2px 0; font-size: 1.1rem; }
.feedback-sheet__verdict span { color: var(--parchment-muted); font-size: 0.75rem; }
.feedback-sheet__rationale { margin: 15px 0 0; padding-top: 13px; color: var(--parchment-muted); border-top: 1px dashed var(--line); font-size: 0.86rem; line-height: 1.68; }
.misconceptions { margin: 11px 0 0; padding: 10px 10px 10px 28px; color: #d5a994; background: rgba(196, 71, 27, 0.06); font-size: 0.78rem; }
.feedback-sheet__foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 14px; }
.feedback-sheet__foot > span { color: var(--parchment-faint); font-size: 0.65rem; }
.next-task { border-color: var(--accent-success); background: rgba(122, 153, 98, 0.12); color: #dce8d4; }

.empty-state { min-height: 420px; display: grid; place-content: center; justify-items: center; text-align: center; color: var(--parchment-muted); }
.empty-state > span { width: 52px; height: 52px; display: grid; place-items: center; margin-bottom: 12px; color: var(--accent-amber); border: 1px solid currentColor; font-family: var(--font-display); font-size: 1.2rem; }
.empty-state h3 { margin-bottom: 6px; }
.empty-state p { max-width: 480px; margin: 0 0 15px; font-size: 0.82rem; }
.empty-state--error > span { color: var(--accent); }

.ledger-block { margin-bottom: 18px; padding-bottom: 17px; border-bottom: 1px solid var(--line); }
.refresh-button { width: 29px; height: 29px; color: var(--parchment-muted); border: 1px solid var(--line); background: transparent; cursor: pointer; }
.ledger-metrics { display: grid; grid-template-columns: repeat(3, 1fr); margin: 12px 0; border: 1px solid var(--line); }
.ledger-metrics div { padding: 9px 5px; text-align: center; border-right: 1px solid var(--line); }
.ledger-metrics div:last-child { border-right: 0; }
.ledger-metrics b { display: block; color: var(--parchment); font-family: var(--font-mono); font-size: 1rem; font-weight: 500; }
.ledger-metrics span { color: var(--parchment-faint); font-size: 0.62rem; }
.selected-ledger { padding: 11px; border-left: 2px solid var(--accent-amber); background: rgba(176, 138, 62, 0.055); }
.selected-ledger > p { margin: 0; color: var(--parchment-muted); font-size: 0.74rem; }
.selected-ledger > strong { display: block; margin: 2px 0 9px; font-family: var(--font-display); font-size: 0.98rem; }
.selected-ledger dl { display: grid; grid-template-columns: repeat(3, 1fr); margin: 0; }
.selected-ledger dl div { text-align: center; }
.selected-ledger dt { color: var(--parchment-faint); font-size: 0.61rem; }
.selected-ledger dd { margin: 1px 0 0; color: var(--parchment-muted); font-family: var(--font-mono); font-size: 0.72rem; }
.tone--mastered { color: var(--accent-success); }
.tone--partial,
.tone--provisional { color: var(--accent-amber); }
.tone--missing { color: var(--accent); }
.tone--idle { color: var(--parchment-dim); }
.ledger-warning { margin: 10px 0 0; color: #d1a17e; font-size: 0.68rem; line-height: 1.5; }

.ledger-block--queue > h3 { margin-bottom: 10px; }
.queue-list { display: grid; gap: 5px; }
.queue-list button {
  display: grid;
  grid-template-columns: 25px 1fr;
  gap: 8px;
  padding: 8px;
  color: var(--parchment-muted);
  text-align: left;
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
}
.queue-list button:hover,
.queue-list button.active { border-color: var(--line-strong); background: rgba(236, 228, 211, 0.025); }
.queue-list button > span { color: var(--parchment-faint); font-size: 0.64rem; }
.queue-list button div { min-width: 0; display: grid; }
.queue-list strong { overflow: hidden; font-family: var(--font-display); font-size: 0.78rem; font-weight: 560; white-space: nowrap; text-overflow: ellipsis; }
.queue-list small { overflow: hidden; color: var(--parchment-faint); font-size: 0.64rem; white-space: nowrap; text-overflow: ellipsis; }
.queue-empty { color: var(--parchment-faint); font-size: 0.72rem; }

.confusion-block__head { display: flex; justify-content: space-between; align-items: center; }
.confusion-block__head button { color: var(--accent-amber); border: 0; border-bottom: 1px solid rgba(176, 138, 62, 0.35); background: transparent; cursor: pointer; }
.confusion-note { margin: 10px 0 0; color: var(--parchment-faint); font-size: 0.7rem; line-height: 1.55; }
.confusion-saved { display:grid; gap:7px; margin:10px 0; padding:8px; color:#bfd2b2; border-left:2px solid var(--accent-success); background:rgba(122,153,98,.07); font-size:.7rem; }
.confusion-saved button { justify-self:start; padding:0 0 2px; color:#b9ced6; border:0; border-bottom:1px solid rgba(92,122,138,.45); background:transparent; font-family:var(--font-display); cursor:pointer; }
.ledger-input { width: 100%; margin-top: 9px; padding: 8px 9px; color: var(--parchment); border: 1px solid var(--line-strong); border-radius: 0; background: #0e0c09; font-family: var(--font-body); }
.ledger-textarea { min-height: 88px; resize: vertical; }
.confusion-submit { width: 100%; margin-top: 8px; padding: 8px; border-color: var(--accent-amber); background: rgba(176, 138, 62, 0.12); color: #ead8af; }
.boundary-note { display: grid; grid-template-columns: 37px 1fr; gap: 9px; padding: 10px; border: 1px dashed rgba(236, 228, 211, 0.13); }
.boundary-note span { color: var(--accent); font-family: var(--font-display); }
.boundary-note p { margin: 0; color: var(--parchment-faint); font-size: 0.66rem; line-height: 1.5; }

@keyframes docket-pulse { 50% { opacity: 0.55; transform: rotate(2deg) scale(0.96); } }
@keyframes verdict-in { from { opacity: 0; transform: translateY(8px); } }

@media (max-width: 1320px) {
  .journey__body { grid-template-columns: 232px minmax(430px, 1fr) 285px; }
  .journey__head { grid-template-columns: minmax(260px, 1fr) auto 38px; }
  .journey__summary { display: none; }
}

@media (max-width: 1040px) {
  .journey-layer { padding: 0; }
  .journey__body {
    display: block;
    overflow-y: auto;
  }
  .index-pane,
  .task-pane,
  .ledger-pane {
    min-height: auto;
    overflow: visible;
  }
  .index-pane {
    border-right: 0;
    border-bottom: 1px solid var(--line-strong);
  }
  .knowledge-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ledger-pane {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 18px;
    border-top: 1px solid var(--line-strong);
    border-left: 0;
  }
  .ledger-block { margin: 0; }
  .task-pane { padding: 18px; }
}

@media (max-width: 720px) {
  .journey__head { grid-template-columns: 1fr 38px; min-height: auto; }
  .phase-switch { grid-column: 1 / -1; grid-row: 2; }
  .phase-switch button { flex: 1; }
  .ledger-pane { display: block; }
  .ledger-block { margin-bottom: 18px; }
  .knowledge-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .knowledge-list li:nth-child(n + 7) { display: none; }
  .task-sheet__head,
  .task-sheet__controls,
  .feedback-sheet__foot { align-items: flex-start; flex-direction: column; }
  .task-sheet__meta { flex-wrap: wrap; }
}
</style>
