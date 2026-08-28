<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { api } from "../lib/api";
import type {
  SubjectiveAttempt,
  TeacherAnalyticsResponse,
  TeacherCaseBundleResponse,
  TeacherClassroom,
  TeacherOverviewResponse,
  TeacherReviewCatalogResponse,
  TeacherReviewObject,
  TeacherSubjectiveQueueResponse,
} from "../lib/types";

const emit = defineEmits<{ close: [] }>();

const tab = ref<"analytics" | "reviews" | "subjective">("analytics");
const overview = ref<TeacherOverviewResponse | null>(null);
const analytics = ref<TeacherAnalyticsResponse | null>(null);
const reviewCatalog = ref<TeacherReviewCatalogResponse | null>(null);
const subjectiveQueue = ref<TeacherSubjectiveQueueResponse | null>(null);
const selectedClassId = ref("");
const loading = ref(true);
const actionBusy = ref(false);
const error = ref("");
const notice = ref("");
const createOpen = ref(false);
const className = ref("刑法甲班");
const classTerm = ref("2026秋");
const studentEmail = ref("");
const reviewFilter = ref<"all" | "case_bundle" | "knowledge_card" | "task_item">("all");
const selectedReview = ref<TeacherReviewObject | null>(null);
const reviewDecision = ref<"approve" | "request_revision" | "reject">("approve");
const reviewNote = ref("");
const reviewId = ref("");
const selectedCaseBundle = ref<TeacherCaseBundleResponse["case_bundle"] | null>(null);
const caseBundleLoading = ref(false);
const selectedSubjective = ref<SubjectiveAttempt | null>(null);
const subjectiveDecision = ref<"approve" | "request_revision" | "reject">("approve");
const subjectiveScore = ref<number | null>(0.7);
const subjectiveKnowledgeStatus = ref<"mastered" | "partial" | "missing">("partial");
const subjectiveFeedback = ref("");
const subjectiveErrorTags = ref("");
const subjectiveReviewId = ref("");

const classes = computed(() => overview.value?.classes ?? []);
const selectedClass = computed(() =>
  classes.value.find((row) => row.class_id === selectedClassId.value) ?? null,
);
const reviewObjects = computed(() => {
  const rows = reviewCatalog.value?.objects ?? [];
  return reviewFilter.value === "all"
    ? rows
    : rows.filter((row) => row.object_type === reviewFilter.value);
});
const subjectiveAttempts = computed(() => subjectiveQueue.value?.attempts ?? []);
const subjectiveAbstainedCount = computed(() =>
  subjectiveAttempts.value.filter((row) => row.ai_abstained).length,
);
const subjectiveCitationPassedCount = computed(() =>
  subjectiveAttempts.value.filter((row) => row.citation_audit.passed).length,
);
const atRiskKnowledge = computed(() => analytics.value?.knowledge ?? []);
const maxKnowledgeSignal = computed(() =>
  Math.max(
    1,
    ...atRiskKnowledge.value.map(
      (row) => row.missing_students + row.partial_students + row.confusion_count,
    ),
  ),
);

const DECISION_LABELS: Record<string, string> = {
  approve: "同意试用",
  request_revision: "要求修订",
  reject: "停止使用",
};

function newReviewId(): string {
  const id = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `review-${id}`;
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [overviewResult, reviewResult, subjectiveResult] = await Promise.all([
      api.teacherOverview(),
      api.teacherReviewCatalog(),
      api.teacherSubjectiveQueue(),
    ]);
    overview.value = overviewResult;
    reviewCatalog.value = reviewResult;
    subjectiveQueue.value = subjectiveResult;
    if (!selectedClassId.value && classes.value[0]) {
      selectedClassId.value = classes.value[0].class_id;
    }
    if (selectedClassId.value) await loadAnalytics(selectedClassId.value);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    loading.value = false;
  }
}

function openSubjectiveReview(row: SubjectiveAttempt): void {
  selectedSubjective.value = row;
  subjectiveDecision.value = "approve";
  subjectiveScore.value = row.ai_score ?? 0.7;
  subjectiveKnowledgeStatus.value = "partial";
  subjectiveFeedback.value = "";
  subjectiveErrorTags.value = "";
  subjectiveReviewId.value = `subjective-${newReviewId()}`;
  error.value = "";
}

async function submitSubjectiveReview(): Promise<void> {
  const row = selectedSubjective.value;
  if (!row || !subjectiveReviewId.value || actionBusy.value) return;
  if (
    subjectiveDecision.value === "approve"
    && (subjectiveScore.value === null || subjectiveScore.value < 0 || subjectiveScore.value > 1)
  ) {
    error.value = "批准稿件必须给出0到1之间的教师评分。";
    return;
  }
  actionBusy.value = true;
  error.value = "";
  try {
    const result = await api.reviewSubjectiveAttempt({
      review_id: subjectiveReviewId.value,
      attempt_id: row.attempt_id,
      decision: subjectiveDecision.value,
      teacher_score: subjectiveDecision.value === "approve" ? subjectiveScore.value : null,
      knowledge_status: subjectiveDecision.value === "approve" ? subjectiveKnowledgeStatus.value : "",
      feedback: subjectiveFeedback.value.trim(),
      error_tags: subjectiveErrorTags.value
        .split(/[，,;；\n]/)
        .map((value) => value.trim())
        .filter(Boolean),
    });
    notice.value = result.learning_event
      ? `教师复核已入账，已生成形成性证据 ${result.learning_event.event_id}。`
      : subjectiveDecision.value === "request_revision"
        ? "已退回学生修订；本次未生成掌握证据。"
        : "已拒绝该稿件；本次未生成掌握证据。";
    selectedSubjective.value = null;
    const refreshes: Promise<unknown>[] = [api.teacherSubjectiveQueue().then((value) => {
      subjectiveQueue.value = value;
    })];
    if (selectedClassId.value) {
      refreshes.push(api.teacherClassAnalytics(selectedClassId.value).then((value) => {
        analytics.value = value;
      }));
    }
    await Promise.all(refreshes);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    actionBusy.value = false;
  }
}

async function loadAnalytics(classId: string): Promise<void> {
  if (!classId) {
    analytics.value = null;
    return;
  }
  actionBusy.value = true;
  error.value = "";
  try {
    analytics.value = await api.teacherClassAnalytics(classId);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    actionBusy.value = false;
  }
}

async function loadSubjectiveQueue(): Promise<void> {
  try {
    subjectiveQueue.value = await api.teacherSubjectiveQueue();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  }
}

async function createClass(): Promise<void> {
  if (!className.value.trim() || !classTerm.value.trim() || actionBusy.value) return;
  actionBusy.value = true;
  error.value = "";
  try {
    const result = await api.createTeacherClass({
      name: className.value.trim(),
      term: classTerm.value.trim(),
    });
    notice.value = result.class_status === "duplicate" ? "该班级已存在。" : "班级已建立。";
    createOpen.value = false;
    overview.value = await api.teacherOverview();
    selectedClassId.value = result.classroom.class_id;
    await loadAnalytics(result.classroom.class_id);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    actionBusy.value = false;
  }
}

async function enrollStudent(): Promise<void> {
  const classroom = selectedClass.value;
  if (!classroom || !studentEmail.value.trim() || actionBusy.value) return;
  actionBusy.value = true;
  error.value = "";
  try {
    const result = await api.enrollTeacherStudent(
      classroom.class_id,
      studentEmail.value.trim(),
    );
    notice.value = result.enrollment_status === "duplicate"
      ? `该学生已在班级中（${result.student_ref}）。`
      : `学生已加入班级（${result.student_ref}）。`;
    studentEmail.value = "";
    overview.value = await api.teacherOverview();
    await Promise.all([loadAnalytics(classroom.class_id), loadSubjectiveQueue()]);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    actionBusy.value = false;
  }
}

async function openReview(row: TeacherReviewObject): Promise<void> {
  selectedReview.value = row;
  selectedCaseBundle.value = null;
  reviewDecision.value = row.latest_teacher_review?.decision ?? "approve";
  reviewNote.value = row.latest_teacher_review?.note ?? "";
  reviewId.value = newReviewId();
  error.value = "";
  if (row.object_type === "case_bundle") {
    caseBundleLoading.value = true;
    try {
      const result = await api.teacherCaseBundle(row.object_id);
      selectedCaseBundle.value = result.case_bundle;
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : String(reason);
    } finally {
      caseBundleLoading.value = false;
    }
  }
}

async function submitReview(): Promise<void> {
  const row = selectedReview.value;
  if (!row || !reviewId.value || actionBusy.value) return;
  actionBusy.value = true;
  error.value = "";
  try {
    const result = await api.submitTeacherReview({
      review_id: reviewId.value,
      object_type: row.object_type,
      object_id: row.object_id,
      object_version: row.object_version,
      decision: reviewDecision.value,
      note: reviewNote.value.trim(),
    });
    notice.value = result.review_status === "duplicate" ? "审核已存在。" : "审核意见已写入不可变台账。";
    selectedReview.value = null;
    reviewCatalog.value = await api.teacherReviewCatalog();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    actionBusy.value = false;
  }
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    if (selectedSubjective.value) selectedSubjective.value = null;
    else if (selectedReview.value) selectedReview.value = null;
    else emit("close");
  }
}

watch(selectedClassId, (value, previous) => {
  if (value && value !== previous && !loading.value) void loadAnalytics(value);
});
watch(tab, (value) => {
  if (value === "subjective" && !loading.value) void loadSubjectiveQueue();
});

onMounted(() => {
  window.addEventListener("keydown", handleKeydown);
  void load();
});
onUnmounted(() => window.removeEventListener("keydown", handleKeydown));
</script>

<template>
  <div class="teacher-layer">
    <section class="teacher-board" role="dialog" aria-modal="true" aria-label="教师教学驾驶舱">
      <header class="teacher-head">
        <div class="teacher-brand">
          <span class="teacher-seal">师</span>
          <div>
            <p class="teacher-kicker mono">TEACHING LEDGER · CRIMINAL LAW</p>
            <h2>刑法教学驾驶舱</h2>
          </div>
        </div>
        <nav class="teacher-tabs" aria-label="教师功能">
          <button :class="{ active: tab === 'analytics' }" @click="tab = 'analytics'">
            班级学情
          </button>
          <button :class="{ active: tab === 'reviews' }" @click="tab = 'reviews'">
            内容复核
            <span class="mono">{{ reviewCatalog?.counts.teacher_review_events ?? 0 }}</span>
          </button>
          <button :class="{ active: tab === 'subjective' }" @click="tab = 'subjective'">
            主观复核
            <span class="mono">{{ subjectiveAttempts.length }}</span>
          </button>
        </nav>
        <div class="teacher-boundary mono">
          <span>自有班级</span>
          <span>匿名聚合</span>
          <span>形成性证据</span>
        </div>
        <button class="teacher-close" aria-label="关闭教师驾驶舱" @click="emit('close')">×</button>
      </header>

      <div v-if="loading" class="teacher-loading">
        <span class="teacher-seal">阅</span>
        <p>正在汇集班级证据与内容台账……</p>
      </div>

      <div v-else class="teacher-body">
        <div v-if="error" class="teacher-alert" role="alert">{{ error }}</div>
        <div v-if="notice" class="teacher-notice">{{ notice }}</div>

        <template v-if="tab === 'analytics'">
          <aside class="class-index">
            <div class="section-head">
              <div>
                <p class="teacher-kicker mono">MY CLASSES</p>
                <h3>任课班级</h3>
              </div>
              <button class="small-action" @click="createOpen = !createOpen">{{ createOpen ? "收起" : "+ 新建" }}</button>
            </div>

            <form v-if="createOpen" class="class-form" @submit.prevent="createClass">
              <input v-model="className" aria-label="班级名称" placeholder="班级名称" />
              <input v-model="classTerm" aria-label="学期" placeholder="学期，如2026秋" />
              <button :disabled="actionBusy">建立班级</button>
            </form>

            <div class="class-list">
              <button
                v-for="row in classes"
                :key="row.class_id"
                :class="{ active: row.class_id === selectedClassId }"
                @click="selectedClassId = row.class_id"
              >
                <span class="class-list__term mono">{{ row.term }}</span>
                <strong>{{ row.name }}</strong>
                <small>{{ row.student_count }} 名学生 · {{ row.status }}</small>
              </button>
              <p v-if="!classes.length" class="class-empty">尚未建立班级。先创建一个试点班，再把已注册的学生账号加入。</p>
            </div>

            <form v-if="selectedClass" class="enroll-form" @submit.prevent="enrollStudent">
              <label>加入已注册学生</label>
              <input v-model="studentEmail" type="email" aria-label="学生邮箱" placeholder="student@school.edu" />
              <button :disabled="!studentEmail.trim() || actionBusy">加入班级</button>
              <p>系统只返回班内匿名student-ref；页面不展示学生邮箱或困惑原文。</p>
            </form>
          </aside>

          <main class="analytics-main">
            <section v-if="analytics" class="class-hero">
              <div>
                <p class="teacher-kicker mono">{{ analytics.classroom.term }} · {{ analytics.classroom.course_id }}</p>
                <h3>{{ analytics.classroom.name }}</h3>
                <p>更新于 {{ analytics.generated_at.slice(0, 16).replace("T", " ") }}</p>
              </div>
              <span class="privacy-stamp">匿名聚合</span>
            </section>

            <section v-if="analytics" class="metric-strip">
              <div><b>{{ analytics.summary.student_count }}</b><span>班级学生</span></div>
              <div><b>{{ analytics.summary.active_student_count }}</b><span>已有行为</span></div>
              <div><b>{{ analytics.summary.learning_event_count }}</b><span>学习事件</span></div>
              <div><b>{{ analytics.summary.task_attempt_count }}</b><span>任务作答</span></div>
              <div><b>{{ analytics.summary.confusion_event_count }}</b><span>困惑标注</span></div>
              <div><b>{{ analytics.summary.provisional_knowledge_states }}</b><span>临时状态</span></div>
            </section>

            <div v-if="analytics" class="analytics-grid">
              <section class="analytics-card analytics-card--wide">
                <div class="section-head">
                  <div>
                    <p class="teacher-kicker mono">KNOWLEDGE SIGNALS</p>
                    <h3>知识点补强信号</h3>
                  </div>
                  <span class="legend"><i></i>缺失/部分/困惑之和</span>
                </div>
                <div v-if="atRiskKnowledge.length" class="knowledge-signals">
                  <div v-for="row in atRiskKnowledge" :key="row.knowledge_id" class="signal-row">
                    <div class="signal-row__label">
                      <strong>{{ row.knowledge_name }}</strong>
                      <span class="mono">
                        缺失 {{ row.missing_students }} · 部分 {{ row.partial_students }} · 困惑 {{ row.confusion_count }}
                      </span>
                    </div>
                    <div class="signal-row__bar">
                      <span
                        :style="{
                          width: `${Math.max(3, ((row.missing_students + row.partial_students + row.confusion_count) / maxKnowledgeSignal) * 100)}%`,
                        }"
                      ></span>
                    </div>
                    <b class="mono">{{ row.provisional_students }} 临时</b>
                  </div>
                </div>
                <p v-else class="analytics-empty">尚无班级知识证据。学生完成预习、复习或精学后自动汇总。</p>
              </section>

              <section class="analytics-card">
                <p class="teacher-kicker mono">CAPABILITY MEAN</p>
                <h3>能力均值</h3>
                <div v-if="analytics.capabilities.length" class="ability-list">
                  <div v-for="row in analytics.capabilities" :key="row.code">
                    <span>{{ row.code }}</span>
                    <div><i :style="{ width: `${Math.round(row.mean * 100)}%` }"></i></div>
                    <b class="mono">{{ (row.mean * 10).toFixed(1) }}</b>
                  </div>
                </div>
                <p v-else class="analytics-empty">暂无可聚合能力证据。</p>
              </section>

              <section class="analytics-card">
                <p class="teacher-kicker mono">RECURRING ERRORS</p>
                <h3>高频错误标签</h3>
                <ol v-if="analytics.top_error_tags.length" class="error-rank">
                  <li v-for="(row, index) in analytics.top_error_tags" :key="row.tag">
                    <span class="mono">{{ String(index + 1).padStart(2, "0") }}</span>
                    <strong>{{ row.tag }}</strong>
                    <b class="mono">×{{ row.count }}</b>
                  </li>
                </ol>
                <p v-else class="analytics-empty">暂无高频错误。</p>
              </section>
            </div>

            <section v-if="analytics" class="teacher-warning">
              <span>证据边界</span>
              <p>
                {{ analytics.warnings.join("；") }}。本页面不提供学生排名，也不展示困惑原文。
                <template v-if="analytics.privacy.small_group_detail_suppressed">
                  当前未达{{ analytics.privacy.minimum_aggregate_size }}人阈值，细分图表保持空白。
                </template>
              </p>
            </section>

            <section v-if="!selectedClass" class="analytics-welcome">
              <span>班</span>
              <h3>先建立试点班级</h3>
              <p>教师只会看到自己班级中的匿名形成性聚合；学生注册后才可由教师显式加入。</p>
            </section>
          </main>
        </template>

        <template v-else-if="tab === 'reviews'">
          <aside class="review-index">
            <div class="section-head">
              <div>
                <p class="teacher-kicker mono">FROZEN CONTENT</p>
                <h3>待复核内容</h3>
              </div>
            </div>
            <div class="review-filter">
              <button :class="{ active: reviewFilter === 'all' }" @click="reviewFilter = 'all'">全部</button>
              <button :class="{ active: reviewFilter === 'case_bundle' }" @click="reviewFilter = 'case_bundle'">案例</button>
              <button :class="{ active: reviewFilter === 'knowledge_card' }" @click="reviewFilter = 'knowledge_card'">知识卡</button>
              <button :class="{ active: reviewFilter === 'task_item' }" @click="reviewFilter = 'task_item'">任务</button>
            </div>
            <dl class="review-counts">
              <div><dt>案例包</dt><dd>{{ reviewCatalog?.counts.case_bundles ?? 0 }}</dd></div>
              <div><dt>知识卡</dt><dd>{{ reviewCatalog?.counts.knowledge_cards ?? 0 }}</dd></div>
              <div><dt>任务</dt><dd>{{ reviewCatalog?.counts.task_items ?? 0 }}</dd></div>
              <div><dt>审核事件</dt><dd>{{ reviewCatalog?.counts.teacher_review_events ?? 0 }}</dd></div>
            </dl>
            <p class="review-boundary">{{ reviewCatalog?.boundary }}</p>
          </aside>

          <main class="review-main">
            <div class="review-table-head mono">
              <span>对象</span><span>版本与证据</span><span>最新教师决定</span><span></span>
            </div>
            <div class="review-table">
              <article v-for="row in reviewObjects" :key="`${row.object_type}:${row.object_id}`">
                <div class="review-object">
                  <span>{{ row.object_type === "task_item" ? "任务" : row.object_type === "case_bundle" ? "案例" : "知识卡" }}</span>
                  <div>
                    <h3>{{ row.title }}</h3>
                    <p>{{ row.subtitle }}</p>
                  </div>
                </div>
                <div class="review-evidence mono">
                  <span>{{ row.object_version.slice(0, 10) }}…</span>
                  <span>{{ row.standard_evidence_ids.length }} 条证据</span>
                  <span v-if="row.difficulty">难度 {{ row.difficulty }}/3</span>
                </div>
                <div class="review-latest">
                  <strong v-if="row.latest_teacher_review" :class="`decision--${row.latest_teacher_review.decision}`">
                    {{ DECISION_LABELS[row.latest_teacher_review.decision] }}
                  </strong>
                  <span v-else>尚无本教师复核</span>
                  <small v-if="row.latest_teacher_review?.note">{{ row.latest_teacher_review.note }}</small>
                </div>
                <button @click="openReview(row)">复核</button>
              </article>
            </div>
          </main>
        </template>

        <template v-else>
          <aside class="review-index subjective-review-index">
            <div class="section-head">
              <div>
                <p class="teacher-kicker mono">ARGUMENT REVIEW</p>
                <h3>学生论证稿</h3>
              </div>
              <span class="queue-stamp mono">{{ subjectiveAttempts.length }} 待办</span>
            </div>
            <dl class="review-counts">
              <div><dt>待人工复核</dt><dd>{{ subjectiveAttempts.length }}</dd></div>
              <div><dt>AI主动弃权</dt><dd>{{ subjectiveAbstainedCount }}</dd></div>
              <div><dt>引用门禁通过</dt><dd>{{ subjectiveCitationPassedCount }}</dd></div>
              <div><dt>长期画像更新</dt><dd>0（待批准）</dd></div>
            </dl>
            <p class="review-boundary">{{ subjectiveQueue?.privacy }}</p>
            <div class="subjective-boundary-card">
              <strong>双重门禁</strong>
              <p>AI只给修改建议。教师批准前，分数、掌握状态和推荐路径都不会变化。</p>
            </div>
          </aside>

          <main class="review-main subjective-review-main">
            <header class="subjective-queue-head">
              <div>
                <p class="teacher-kicker mono">ANONYMOUS FORMATIVE QUEUE</p>
                <h3>匿名形成性复核队列</h3>
                <p>阅读学生原文、AI弃权原因和引用门禁，再作独立教学判断。</p>
              </div>
              <span class="privacy-stamp">仅自有班级</span>
            </header>

            <div v-if="subjectiveAttempts.length" class="subjective-review-list">
              <article v-for="row in subjectiveAttempts" :key="row.attempt_id" class="subjective-review-row">
                <div class="subjective-review-row__identity">
                  <span class="subjective-review-row__seal">{{ row.task.task_type === "role_reversal" ? "变" : "答" }}</span>
                  <div>
                    <p class="mono">{{ row.student_ref }} · {{ row.phase === "prestudy" ? "课前" : "课后" }}</p>
                    <h3>{{ row.task.knowledge_names.join(" / ") }}</h3>
                    <span>{{ row.task.task_type === "role_reversal" ? "角色互换" : "知识短答" }} · 难度{{ row.task.difficulty }}/3</span>
                  </div>
                </div>

                <blockquote>{{ row.response_text }}</blockquote>

                <div class="subjective-audit-strip mono">
                  <span :class="row.ai_abstained ? 'audit--warn' : 'audit--ok'">
                    {{ row.ai_abstained ? "AI弃权" : `AI参考 ${((row.ai_score ?? 0) * 10).toFixed(1)}/10` }}
                  </span>
                  <span>置信度 {{ Math.round(row.ai_confidence * 100) }}%</span>
                  <span :class="row.citation_audit.passed ? 'audit--ok' : 'audit--warn'">
                    引用门禁{{ row.citation_audit.passed ? "通过" : "未通过" }}
                  </span>
                  <span>把握度 {{ row.confidence ?? "未填" }}/5</span>
                </div>

                <div class="subjective-ai-notes">
                  <section>
                    <strong>AI认为可保留</strong>
                    <ul v-if="row.ai_feedback.strengths.length">
                      <li v-for="item in row.ai_feedback.strengths" :key="item">{{ item }}</li>
                    </ul>
                    <p v-else>无可靠结论。</p>
                  </section>
                  <section>
                    <strong>{{ row.ai_abstained ? "弃权原因" : "建议修订" }}</strong>
                    <ul v-if="row.ai_feedback.corrections.length">
                      <li v-for="item in row.ai_feedback.corrections" :key="item">{{ item }}</li>
                    </ul>
                    <p v-else>{{ row.ai_feedback.abstain_reason || row.ai_feedback.suggested_revision || "等待教师独立判断。" }}</p>
                  </section>
                </div>

                <footer>
                  <span>当前状态：{{ row.status }} · 未进入长期画像</span>
                  <button @click="openSubjectiveReview(row)">打开匿名稿件复核 →</button>
                </footer>
              </article>
            </div>

            <section v-else class="analytics-welcome subjective-empty">
              <span>清</span>
              <h3>当前没有待复核稿件</h3>
              <p>学生提交主观短答或角色互换任务后，稿件会自动进入其任课教师的匿名队列。</p>
            </section>
          </main>
        </template>
      </div>

      <div v-if="selectedReview" class="review-dialog-layer" @click.self="selectedReview = null">
        <section class="review-dialog" role="dialog" aria-label="提交教师内容复核">
          <header>
            <div>
              <p class="teacher-kicker mono">IMMUTABLE REVIEW EVENT</p>
              <h3>{{ selectedReview.title }}</h3>
            </div>
            <button aria-label="关闭复核" @click="selectedReview = null">×</button>
          </header>
          <p class="review-dialog__subtitle">{{ selectedReview.subtitle }}</p>
          <div class="review-dialog__meta mono">
            <span>{{ selectedReview.object_type }}</span>
            <span>{{ selectedReview.object_version.slice(0, 16) }}…</span>
            <span>{{ selectedReview.standard_evidence_ids.length }}条证据</span>
          </div>
          <section v-if="selectedReview.object_type === 'case_bundle'" class="case-review-detail">
            <p v-if="caseBundleLoading" class="analytics-empty">正在读取教师参考投影……</p>
            <template v-else-if="selectedCaseBundle">
              <div class="case-review-detail__links">
                <span v-for="link in selectedCaseBundle.knowledge_links" :key="link.knowledge_id">
                  {{ link.knowledge_name }} · {{ link.role }}
                </span>
                <span>{{ selectedCaseBundle.evidence_ids.length }}条Evidence</span>
                <span>
                  {{ Object.values(selectedCaseBundle.stage_packets).filter((stage) => stage.availability === 'available').length }}个可用阶段
                </span>
              </div>
              <div v-if="selectedCaseBundle.unresolved_legal_basis_fragments.length" class="case-review-detail__risk">
                <strong>待复核法条缺口</strong>
                <p v-for="item in selectedCaseBundle.unresolved_legal_basis_fragments" :key="item">{{ item }}</p>
              </div>
              <div class="case-review-detail__reference">
                <strong>指导要点（教师参考）</strong>
                <p>{{ selectedCaseBundle.reference_private.guiding_points }}</p>
              </div>
            </template>
          </section>
          <label>
            <span>教师决定</span>
            <select v-model="reviewDecision">
              <option value="approve">同意本学期试用</option>
              <option value="request_revision">要求修订后复核</option>
              <option value="reject">停止使用</option>
            </select>
          </label>
          <label>
            <span>复核意见</span>
            <textarea v-model="reviewNote" maxlength="2000" placeholder="写明法源、理论口径、题干或教学风险……"></textarea>
          </label>
          <p class="review-dialog__boundary">提交会新增不可变审核事件，不会直接修改冻结JSON内容；修订须回到受治理构建流程。</p>
          <button class="review-submit" :disabled="actionBusy" @click="submitReview">
            {{ actionBusy ? "写入中…" : "写入审核台账" }}
          </button>
        </section>
      </div>

      <div v-if="selectedSubjective" class="review-dialog-layer" @click.self="selectedSubjective = null">
        <section class="review-dialog subjective-review-dialog" role="dialog" aria-label="教师主观稿件复核">
          <header>
            <div>
              <p class="teacher-kicker mono">TEACHER GATE · {{ selectedSubjective.student_ref }}</p>
              <h3>{{ selectedSubjective.task.knowledge_names.join(" / ") }}</h3>
            </div>
            <button aria-label="关闭主观复核" @click="selectedSubjective = null">×</button>
          </header>
          <div class="review-dialog__meta mono">
            <span>{{ selectedSubjective.task.task_type }}</span>
            <span>{{ selectedSubjective.phase }}</span>
            <span>{{ selectedSubjective.citation_audit.passed ? "引用通过" : "引用未通过" }}</span>
            <span>{{ selectedSubjective.ai_abstained ? "AI弃权" : `AI置信度${Math.round(selectedSubjective.ai_confidence * 100)}%` }}</span>
          </div>

          <section class="subjective-manuscript">
            <strong>学生原文</strong>
            <p>{{ selectedSubjective.response_text }}</p>
          </section>
          <section class="subjective-model-advice">
            <strong>AI形成性参考（非成绩）</strong>
            <p v-if="selectedSubjective.ai_feedback.suggested_revision">{{ selectedSubjective.ai_feedback.suggested_revision }}</p>
            <p v-else>{{ selectedSubjective.ai_feedback.abstain_reason || "模型未给出可采信建议。" }}</p>
          </section>

          <label>
            <span>教师决定</span>
            <select v-model="subjectiveDecision">
              <option value="approve">批准为形成性掌握证据</option>
              <option value="request_revision">退回学生修订</option>
              <option value="reject">拒绝本次稿件</option>
            </select>
          </label>
          <div v-if="subjectiveDecision === 'approve'" class="subjective-verdict-grid">
            <label>
              <span>教师评分（0—1）</span>
              <input v-model.number="subjectiveScore" type="number" min="0" max="1" step="0.01" />
            </label>
            <label>
              <span>知识掌握判定</span>
              <select v-model="subjectiveKnowledgeStatus">
                <option value="mastered">mastered · 已掌握</option>
                <option value="partial">partial · 部分掌握</option>
                <option value="missing">missing · 尚未掌握</option>
              </select>
            </label>
          </div>
          <label>
            <span>给学生的教师反馈</span>
            <textarea v-model="subjectiveFeedback" maxlength="3000" placeholder="指出规范、事实涵摄、反方论证或表达中最需要修订的部分……"></textarea>
          </label>
          <label>
            <span>错误标签（逗号或分号分隔）</span>
            <input v-model="subjectiveErrorTags" maxlength="500" placeholder="例如：构成要件遗漏；边界论证不足" />
          </label>
          <p class="review-dialog__boundary">
            只有“批准”会生成 teacher_reviewed_subjective_assessment；退回和拒绝均不会更新画像或正式成绩。
          </p>
          <button class="review-submit" :disabled="actionBusy" @click="submitSubjectiveReview">
            {{ actionBusy ? "写入中…" : subjectiveDecision === "approve" ? "批准并写入形成性证据" : "写入教师决定" }}
          </button>
        </section>
      </div>
    </section>
  </div>
</template>

<style scoped>
.teacher-layer {
  position: fixed;
  inset: 0;
  z-index: 1300;
  padding: 18px;
  background: radial-gradient(circle at 80% 10%, rgba(92, 122, 138, 0.13), transparent 35%), rgba(5, 4, 3, 0.91);
  backdrop-filter: blur(12px);
}
.teacher-board {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: var(--parchment);
  border: 1px solid rgba(92, 122, 138, 0.44);
  background:
    linear-gradient(90deg, rgba(255, 255, 255, 0.012) 1px, transparent 1px) 0 0 / 52px 52px,
    linear-gradient(180deg, #151613, #0c0d0c 70%);
  box-shadow: 0 40px 100px rgba(0, 0, 0, 0.72);
}
.teacher-head {
  min-height: 82px;
  display: grid;
  grid-template-columns: minmax(300px, 1fr) auto minmax(260px, 1fr) 38px;
  align-items: center;
  gap: 22px;
  padding: 12px 18px 12px 24px;
  border-bottom: 1px solid rgba(92, 122, 138, 0.32);
  background: linear-gradient(180deg, rgba(28, 31, 28, 0.98), rgba(15, 17, 15, 0.98));
}
.teacher-brand { display: flex; align-items: center; gap: 14px; }
.teacher-seal { width: 46px; height: 46px; display: grid; place-items: center; color: #e4ecdf; border: 1px solid #73906d; box-shadow: inset 0 0 0 3px #162018; font-family: var(--font-display); font-weight: 800; transform: rotate(-2deg); }
.teacher-kicker { margin: 0 0 3px; color: #88aab7; font-size: 0.63rem; letter-spacing: 0.17em; }
.teacher-brand h2 { font-size: 1.28rem; font-weight: 650; }
.teacher-tabs { display: flex; border: 1px solid var(--line-strong); }
.teacher-tabs button { padding: 10px 17px; color: var(--parchment-dim); border: 0; border-right: 1px solid var(--line); background: transparent; font-family: var(--font-display); cursor: pointer; }
.teacher-tabs button:last-child { border-right: 0; }
.teacher-tabs button.active { color: var(--parchment); background: rgba(92, 122, 138, 0.16); box-shadow: inset 0 -2px #7895a2; }
.teacher-tabs span { margin-left: 6px; color: #88aab7; }
.teacher-boundary { display: flex; justify-content: flex-end; gap: 7px; }
.teacher-boundary span { padding: 4px 7px; color: var(--parchment-dim); border: 1px solid var(--line); font-size: 0.65rem; }
.teacher-close { width: 36px; height: 36px; color: var(--parchment-muted); border: 1px solid var(--line-strong); background: transparent; font-size: 1.35rem; cursor: pointer; }
.teacher-body { position: relative; flex: 1; min-height: 0; display: grid; grid-template-columns: 270px minmax(0, 1fr); }
.teacher-loading { flex: 1; display: grid; place-content: center; justify-items: center; gap: 15px; color: var(--parchment-muted); }
.teacher-alert,
.teacher-notice { position: absolute; z-index: 4; top: 10px; left: 50%; transform: translateX(-50%); max-width: 680px; padding: 8px 14px; font-size: 0.76rem; box-shadow: 0 8px 24px #0008; }
.teacher-alert { color: #e8b6a7; border: 1px solid rgba(196, 71, 27, 0.55); background: #27130d; }
.teacher-notice { color: #dce8d4; border: 1px solid rgba(122, 153, 98, 0.55); background: #132013; }
.class-index,
.review-index { min-height: 0; overflow-y: auto; padding: 20px 15px; border-right: 1px solid var(--line-strong); background: rgba(9, 10, 8, 0.66); }
.section-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 14px; margin-bottom: 13px; }
.section-head h3,
.analytics-card h3 { font-size: 1.06rem; font-weight: 620; }
.small-action { color: #88aab7; border: 0; border-bottom: 1px solid rgba(92, 122, 138, 0.42); background: transparent; cursor: pointer; }
.class-form,
.enroll-form { display: grid; gap: 7px; margin: 12px 0 16px; padding: 11px; border: 1px solid var(--line); background: rgba(255, 255, 255, 0.018); }
.class-form input,
.enroll-form input,
.review-dialog select,
.review-dialog textarea,
.review-dialog input { width: 100%; padding: 8px 9px; color: var(--parchment); border: 1px solid var(--line-strong); background: #0c0e0c; font-family: var(--font-body); }
.class-form button,
.enroll-form button { padding: 8px; color: #dbe7de; border: 1px solid rgba(122, 153, 98, 0.45); background: rgba(122, 153, 98, 0.08); cursor: pointer; }
.enroll-form label { color: var(--parchment-muted); font-size: 0.75rem; }
.enroll-form p { margin: 0; color: var(--parchment-faint); font-size: 0.65rem; }
.class-list { display: grid; gap: 6px; }
.class-list button { display: grid; padding: 10px; color: var(--parchment-muted); text-align: left; border: 1px solid transparent; background: transparent; cursor: pointer; }
.class-list button.active { color: var(--parchment); border-color: rgba(92, 122, 138, 0.4); background: linear-gradient(90deg, rgba(92, 122, 138, 0.12), transparent); }
.class-list__term { color: #88aab7; font-size: 0.64rem; }
.class-list strong { font-family: var(--font-display); font-size: 0.9rem; }
.class-list small { color: var(--parchment-faint); }
.class-empty { color: var(--parchment-faint); font-size: 0.72rem; line-height: 1.6; }
.analytics-main,
.review-main { min-height: 0; overflow-y: auto; padding: 26px clamp(22px, 3vw, 44px) 48px; }
.class-hero { display: flex; justify-content: space-between; align-items: flex-start; padding: 0 0 18px; border-bottom: 1px solid rgba(92, 122, 138, 0.35); }
.class-hero h3 { font-size: 1.45rem; font-weight: 650; }
.class-hero p:last-child { margin: 5px 0 0; color: var(--parchment-dim); font-size: 0.72rem; }
.privacy-stamp { padding: 6px 9px; color: #88aab7; border: 1px solid rgba(92, 122, 138, 0.5); font-family: var(--font-display); transform: rotate(2deg); }
.metric-strip { display: grid; grid-template-columns: repeat(6, 1fr); margin: 19px 0; border: 1px solid var(--line); }
.metric-strip div { padding: 12px 7px; text-align: center; border-right: 1px solid var(--line); }
.metric-strip div:last-child { border-right: 0; }
.metric-strip b { display: block; font-family: var(--font-mono); font-size: 1.25rem; font-weight: 500; }
.metric-strip span { color: var(--parchment-faint); font-size: 0.66rem; }
.analytics-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.analytics-card { min-height: 230px; padding: 17px; border: 1px solid var(--line); background: rgba(255, 255, 255, 0.018); }
.analytics-card--wide { grid-column: 1 / -1; }
.legend { color: var(--parchment-faint); font-size: 0.65rem; }
.legend i { display: inline-block; width: 8px; height: 8px; margin-right: 5px; background: #7895a2; }
.knowledge-signals { display: grid; gap: 10px; }
.signal-row { display: grid; grid-template-columns: minmax(180px, 0.9fr) minmax(150px, 1.3fr) 60px; align-items: center; gap: 12px; }
.signal-row__label { min-width: 0; display: grid; }
.signal-row__label strong { overflow: hidden; font-family: var(--font-display); font-size: 0.83rem; white-space: nowrap; text-overflow: ellipsis; }
.signal-row__label span { color: var(--parchment-faint); font-size: 0.62rem; }
.signal-row__bar { height: 7px; background: rgba(236, 228, 211, 0.06); }
.signal-row__bar span { display: block; height: 100%; background: linear-gradient(90deg, #7895a2, var(--accent-amber), var(--accent)); }
.signal-row > b { color: var(--parchment-dim); font-size: 0.63rem; font-weight: 400; }
.ability-list { display: grid; gap: 10px; margin-top: 14px; }
.ability-list > div { display: grid; grid-template-columns: 130px 1fr 32px; align-items: center; gap: 9px; }
.ability-list span { color: var(--parchment-muted); font-size: 0.72rem; }
.ability-list div div { height: 5px; background: var(--line); }
.ability-list i { display: block; height: 100%; background: var(--accent-success); }
.ability-list b { color: var(--parchment-muted); font-size: 0.68rem; }
.error-rank { list-style: none; margin: 13px 0 0; padding: 0; display: grid; gap: 8px; }
.error-rank li { display: grid; grid-template-columns: 28px 1fr 30px; gap: 8px; color: var(--parchment-muted); }
.error-rank li span { color: var(--parchment-faint); font-size: 0.64rem; }
.error-rank strong { font-size: 0.76rem; font-weight: 500; }
.error-rank b { color: var(--accent); font-size: 0.67rem; }
.analytics-empty { color: var(--parchment-faint); font-size: 0.75rem; }
.teacher-warning { display: grid; grid-template-columns: 70px 1fr; gap: 12px; margin-top: 15px; padding: 11px; border: 1px dashed var(--line-strong); }
.teacher-warning span { color: var(--accent); font-family: var(--font-display); }
.teacher-warning p { margin: 0; color: var(--parchment-faint); font-size: 0.69rem; }
.analytics-welcome { min-height: 500px; display: grid; place-content: center; justify-items: center; text-align: center; }
.analytics-welcome > span { width: 52px; height: 52px; display: grid; place-items: center; margin-bottom: 12px; color: #88aab7; border: 1px solid currentColor; font-family: var(--font-display); }
.analytics-welcome p { max-width: 460px; color: var(--parchment-faint); }

.review-filter { display: flex; margin-bottom: 15px; border: 1px solid var(--line); }
.review-filter button { flex: 1; padding: 7px; color: var(--parchment-dim); border: 0; border-right: 1px solid var(--line); background: transparent; cursor: pointer; }
.review-filter button:last-child { border-right: 0; }
.review-filter button.active { color: var(--parchment); background: rgba(92, 122, 138, 0.13); }
.review-counts { margin: 0; }
.review-counts div { display: flex; justify-content: space-between; padding: 7px 0; border-bottom: 1px solid var(--line); }
.review-counts dt { color: var(--parchment-dim); }
.review-counts dd { margin: 0; color: var(--parchment); font-family: var(--font-mono); }
.review-boundary { color: var(--parchment-faint); font-size: 0.7rem; line-height: 1.6; }
.queue-stamp { padding: 4px 7px; color: #ddb091; border: 1px solid rgba(196, 123, 74, 0.42); font-size: 0.65rem; }
.subjective-boundary-card { margin-top: 18px; padding: 12px; border: 1px dashed rgba(196, 123, 74, 0.42); background: rgba(196, 123, 74, 0.045); }
.subjective-boundary-card strong { color: #ddb091; font-family: var(--font-display); }
.subjective-boundary-card p { margin: 6px 0 0; color: var(--parchment-faint); font-size: 0.7rem; line-height: 1.65; }
.subjective-queue-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding-bottom: 16px; border-bottom: 1px solid var(--line-strong); }
.subjective-queue-head h3 { font-size: 1.35rem; }
.subjective-queue-head p:last-child { margin: 5px 0 0; color: var(--parchment-faint); font-size: 0.72rem; }
.subjective-review-list { display: grid; gap: 14px; margin-top: 17px; }
.subjective-review-row { position: relative; padding: 16px; border: 1px solid var(--line); background: linear-gradient(135deg, rgba(255,255,255,.022), rgba(92,122,138,.025)); box-shadow: inset 3px 0 rgba(196, 123, 74, 0.48); }
.subjective-review-row__identity { display: grid; grid-template-columns: 44px minmax(0, 1fr); gap: 11px; align-items: center; }
.subjective-review-row__seal { width: 42px; height: 42px; display: grid; place-items: center; color: #ddb091; border: 1px solid rgba(196, 123, 74, 0.46); box-shadow: inset 0 0 0 3px #21170f; font-family: var(--font-display); transform: rotate(-2deg); }
.subjective-review-row__identity p { margin: 0; color: #88aab7; font-size: .62rem; }
.subjective-review-row__identity h3 { margin: 2px 0; font-size: .96rem; }
.subjective-review-row__identity div > span { color: var(--parchment-faint); font-size: .68rem; }
.subjective-review-row blockquote { max-height: 138px; overflow-y: auto; margin: 13px 0 11px; padding: 11px 13px; color: var(--parchment-muted); border-left: 2px solid rgba(92, 122, 138, .55); background: rgba(0,0,0,.18); font-size: .76rem; line-height: 1.7; white-space: pre-wrap; }
.subjective-audit-strip { display: flex; flex-wrap: wrap; gap: 6px; }
.subjective-audit-strip span { padding: 3px 6px; color: var(--parchment-faint); border: 1px solid var(--line); font-size: .62rem; }
.subjective-audit-strip .audit--ok { color: #b8cca9; border-color: rgba(122, 153, 98, .4); }
.subjective-audit-strip .audit--warn { color: #e3b38e; border-color: rgba(196, 123, 74, .5); }
.subjective-ai-notes { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; margin-top: 10px; }
.subjective-ai-notes section { padding: 9px 10px; border: 1px dashed var(--line); }
.subjective-ai-notes strong { color: var(--parchment-dim); font-size: .69rem; }
.subjective-ai-notes ul { margin: 5px 0 0; padding-left: 17px; color: var(--parchment-faint); font-size: .68rem; line-height: 1.5; }
.subjective-ai-notes p { margin: 5px 0 0; color: var(--parchment-faint); font-size: .68rem; }
.subjective-review-row footer { display: flex; align-items: center; justify-content: space-between; gap: 14px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--line); }
.subjective-review-row footer span { color: var(--parchment-faint); font-size: .66rem; }
.subjective-review-row footer button { padding: 7px 10px; color: #ddb091; border: 1px solid rgba(196, 123, 74, .45); background: rgba(196, 123, 74, .055); cursor: pointer; }
.subjective-empty { min-height: 420px; }
.review-table-head,
.review-table article { display: grid; grid-template-columns: minmax(280px, 1.5fr) 170px 220px 62px; align-items: center; gap: 14px; }
.review-table-head { padding: 0 10px 9px; color: var(--parchment-faint); border-bottom: 1px solid var(--line-strong); font-size: 0.65rem; }
.review-table article { padding: 11px 10px; border-bottom: 1px solid var(--line); }
.review-object { min-width: 0; display: grid; grid-template-columns: 44px 1fr; gap: 10px; }
.review-object > span { width: 39px; height: 39px; display: grid; place-items: center; color: #88aab7; border: 1px solid rgba(92, 122, 138, 0.4); font-size: 0.68rem; }
.review-object h3 { font-size: 0.85rem; font-weight: 600; }
.review-object p { overflow: hidden; margin: 3px 0 0; color: var(--parchment-faint); font-size: 0.68rem; white-space: nowrap; text-overflow: ellipsis; }
.review-evidence { display: grid; color: var(--parchment-dim); font-size: 0.63rem; }
.review-latest { min-width: 0; display: grid; }
.review-latest > span { color: var(--parchment-faint); font-size: 0.69rem; }
.review-latest strong { font-family: var(--font-display); font-size: 0.78rem; }
.review-latest small { overflow: hidden; color: var(--parchment-faint); white-space: nowrap; text-overflow: ellipsis; }
.decision--approve { color: var(--accent-success); }
.decision--request_revision { color: var(--accent-amber); }
.decision--reject { color: var(--accent); }
.review-table article > button { padding: 7px; color: #88aab7; border: 1px solid rgba(92, 122, 138, 0.4); background: transparent; cursor: pointer; }

.review-dialog-layer { position: fixed; inset: 0; z-index: 10; display: grid; place-items: center; padding: 24px; background: rgba(0, 0, 0, 0.72); }
.review-dialog { width: min(680px, 100%); max-height: 90vh; overflow-y: auto; padding: 22px; border: 1px solid rgba(92, 122, 138, 0.48); background: #151713; box-shadow: 0 30px 90px #000; }
.review-dialog header { display: flex; justify-content: space-between; gap: 15px; }
.review-dialog header h3 { font-size: 1.2rem; }
.review-dialog header button { width: 31px; height: 31px; color: var(--parchment-muted); border: 1px solid var(--line); background: transparent; }
.review-dialog__subtitle { color: var(--parchment-muted); line-height: 1.6; }
.review-dialog__meta { display: flex; gap: 7px; margin-bottom: 14px; }
.review-dialog__meta span { padding: 4px 7px; color: var(--parchment-dim); border: 1px solid var(--line); font-size: 0.63rem; }
.review-dialog label { display: block; margin-top: 12px; }
.review-dialog label > span { display: block; margin-bottom: 5px; color: var(--parchment-dim); font-size: 0.72rem; }
.review-dialog textarea { min-height: 120px; resize: vertical; }
.review-dialog__boundary { color: var(--parchment-faint); font-size: 0.68rem; }
.subjective-review-dialog { width: min(820px, 100%); }
.subjective-manuscript,
.subjective-model-advice { margin: 11px 0; padding: 11px 12px; border: 1px solid var(--line); background: rgba(0,0,0,.16); }
.subjective-manuscript strong,
.subjective-model-advice strong { color: #b9ced6; font-size: .72rem; }
.subjective-manuscript p,
.subjective-model-advice p { max-height: 170px; overflow-y: auto; margin: 6px 0 0; color: var(--parchment-muted); font-size: .75rem; line-height: 1.7; white-space: pre-wrap; }
.subjective-model-advice { border-left: 2px solid rgba(196, 123, 74, .6); }
.subjective-verdict-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 11px; }
.subjective-review-dialog input[type="number"] { font-family: var(--font-mono); }
.case-review-detail { margin: 12px 0; padding: 11px; border: 1px solid var(--line); background: rgba(92, 122, 138, 0.045); }
.case-review-detail__links { display: flex; flex-wrap: wrap; gap: 6px; }
.case-review-detail__links span { padding: 3px 6px; color: #b9ced6; border: 1px solid rgba(92, 122, 138, 0.34); font-size: 0.66rem; }
.case-review-detail__risk { margin-top: 9px; padding: 8px; color: #ddb091; border-left: 2px solid var(--accent); background: rgba(196, 71, 27, 0.07); }
.case-review-detail__risk p { margin: 3px 0 0; font-size: 0.68rem; }
.case-review-detail__reference { margin-top: 9px; }
.case-review-detail__reference strong { color: var(--accent-amber); font-size: 0.72rem; }
.case-review-detail__reference p { max-height: 105px; overflow-y: auto; margin: 5px 0 0; color: var(--parchment-muted); font-size: 0.72rem; line-height: 1.55; }
.review-submit { width: 100%; padding: 10px; color: #dce8d4; border: 1px solid var(--accent-success); background: rgba(122, 153, 98, 0.1); font-family: var(--font-display); cursor: pointer; }

@media (max-width: 1120px) {
  .teacher-head { grid-template-columns: minmax(260px, 1fr) auto 38px; }
  .teacher-boundary { display: none; }
  .metric-strip { grid-template-columns: repeat(3, 1fr); }
  .metric-strip div:nth-child(3) { border-right: 0; }
  .metric-strip div:nth-child(-n + 3) { border-bottom: 1px solid var(--line); }
  .review-table-head,
  .review-table article { grid-template-columns: minmax(260px, 1.4fr) 150px 180px 58px; }
}
@media (max-width: 820px) {
  .teacher-layer { padding: 0; }
  .teacher-head { grid-template-columns: 1fr 38px; }
  .teacher-tabs { grid-column: 1 / -1; grid-row: 2; }
  .teacher-tabs button { flex: 1; }
  .teacher-body { display: block; overflow-y: auto; }
  .class-index,
  .review-index,
  .analytics-main,
  .review-main { min-height: auto; overflow: visible; border-right: 0; }
  .analytics-grid { display: block; }
  .analytics-card { margin-bottom: 13px; }
  .review-table-head { display: none; }
  .review-table article { grid-template-columns: 1fr 60px; }
  .review-evidence,
  .review-latest { grid-column: 1; }
  .review-table article > button { grid-column: 2; grid-row: 1 / 4; }
  .subjective-ai-notes,
  .subjective-verdict-grid { grid-template-columns: 1fr; }
  .subjective-review-row footer { align-items: flex-start; flex-direction: column; }
  .subjective-review-row footer button { width: 100%; }
}
</style>
