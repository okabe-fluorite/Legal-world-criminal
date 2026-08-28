<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { api } from "../lib/api";
import { ORCDF_SHADOW } from "../data/orcdfShadow";
import type {
  AdaptiveKnowledgeEvidence,
  AdaptiveRecommendationResponse,
  CasePickerEntry,
  EvidenceTimelineEvent,
  KnowledgeCard,
  ModelCatalogResponse,
  SubjectiveTask,
} from "../lib/types";

const emit = defineEmits<{ close: []; openJourney: [] }>();
const tab = ref<"diagnosis" | "orcdf" | "path" | "models">("diagnosis");
const loading = ref(true);
const error = ref("");
const adaptive = ref<AdaptiveRecommendationResponse | null>(null);
const cards = ref<KnowledgeCard[]>([]);
const timeline = ref<EvidenceTimelineEvent[]>([]);
const subjectiveTasks = ref<SubjectiveTask[]>([]);
const cases = ref<CasePickerEntry[]>([]);
const modelCatalog = ref<ModelCatalogResponse | null>(null);

const REASON_LABELS: Record<string, string> = {
  case_evidence_indicates_weakness: "案件证据提示薄弱，优先补强",
  case_evidence_requires_reinforcement: "已有表现不稳定，安排巩固",
  provisional_mastery_spaced_review: "已有临时证据，安排复现确认",
  insufficient_repeated_evidence: "独立证据不足，继续采集",
  no_evidence_collect_diagnostic: "尚无课堂证据，先做覆盖诊断",
  learner_reported_confusion: "学生主动标记困惑，优先回应",
};

const profile = computed(() => adaptive.value?.profile);
const recommendations = computed(() => adaptive.value?.recommendations ?? []);
const knowledgeRows = computed(() =>
  cards.value
    .map((card) => ({ card, evidence: profile.value?.knowledge?.[card.knowledge_id] }))
    .sort((a, b) => {
      const priority = (row: { evidence?: AdaptiveKnowledgeEvidence }) => {
        if (row.evidence?.latest === "missing") return 0;
        if (row.evidence?.latest === "partial") return 1;
        if (!row.evidence?.event_count) return 2;
        if (row.evidence?.evidence_status === "provisional") return 3;
        return 4;
      };
      return priority(a) - priority(b);
    }),
);
const observedCount = computed(() =>
  knowledgeRows.value.filter((row) => Number(row.evidence?.event_count ?? 0) > 0).length,
);
const insufficientCount = computed(() =>
  knowledgeRows.value.filter((row) => row.evidence?.evidence_status !== "provisional").length,
);
const confusionCount = computed(() =>
  Object.values(profile.value?.confusions ?? {}).reduce((sum, row) => sum + Number(row.count ?? 0), 0),
);
const errorCounts = computed(() => {
  const counts = new Map<string, number>();
  for (const event of timeline.value) {
    for (const tag of event.error_tags) counts.set(tag, (counts.get(tag) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag))
    .slice(0, 6);
});
const targetKnowledge = computed(() => {
  const recommendation = recommendations.value[0];
  return cards.value.find((card) => card.knowledge_id === recommendation?.knowledge_id)
    ?? knowledgeRows.value[0]?.card
    ?? null;
});
const pathNodes = computed(() => {
  const target = targetKnowledge.value;
  const prerequisites = cards.value.filter((card) => target?.prerequisite_ids.includes(card.knowledge_id));
  const selection = recommendations.value.find((row) => row.knowledge_id === target?.knowledge_id)
    ?? recommendations.value[0];
  const shortAnswer = subjectiveTasks.value.find(
    (row) => row.task_type === "short_answer" && row.knowledge_ids.includes(target?.knowledge_id ?? ""),
  ) ?? subjectiveTasks.value.find((row) => row.task_type === "short_answer");
  const roleReversal = subjectiveTasks.value.find((row) => row.task_type === "role_reversal");
  const caseRow = cases.value.find((row) => Number(row.knowledge_count ?? 0) > 0) ?? cases.value[0];
  return [
    {
      no: "01",
      type: "诊断薄弱点",
      title: target?.canonical_name ?? "等待首条学习证据",
      detail: stateLabel(target ? profile.value?.knowledge?.[target.knowledge_id] : undefined),
      status: "current",
      reason: "Evidence-KT按事件、题目覆盖与困惑排序",
    },
    {
      no: "02",
      type: "回退先修",
      title: prerequisites.length ? prerequisites.map((row) => row.canonical_name).join(" / ") : "无需额外先修",
      detail: prerequisites.length ? `${prerequisites.length}个先修节点` : "直接进入目标任务",
      status: prerequisites.length ? "ready" : "complete",
      reason: "只在先修缺失时回退，不让Agent自由跳转",
    },
    {
      no: "03",
      type: "推荐选择题",
      title: selection?.stem ?? selection?.question ?? "等待可执行TaskItem",
      detail: selection?.task_id ?? "insufficient_evidence",
      status: selection ? "ready" : "locked",
      reason: reasonLabel(selection?.reason_code),
    },
    {
      no: "04",
      type: "主观短答",
      title: shortAnswer?.knowledge_names.join(" / ") ?? "等待主观任务映射",
      detail: shortAnswer ? `难度${shortAnswer.difficulty}/3 · 教师复核后入画像` : "未映射",
      status: shortAnswer ? "ready" : "locked",
      reason: "补充事实—规范涵摄与边界论证证据",
    },
    {
      no: "05",
      type: "案件实训",
      title: caseRow?.title ?? "等待CaseBundle",
      detail: caseRow ? `${caseRow.evidence_count ?? 0}条Evidence · ${caseRow.case_id}` : "未映射",
      status: caseRow ? "ready" : "locked",
      reason: "将知识判断迁移到调查、对抗与辩护意见",
    },
    {
      no: "06",
      type: "角色互换",
      title: roleReversal?.knowledge_names.join(" / ") ?? "等待角色任务",
      detail: roleReversal ? "反方立场 · 教师门禁" : "未映射",
      status: roleReversal ? "ready" : "locked",
      reason: "检验结论能否跨事实与立场迁移",
    },
    {
      no: "07",
      type: "间隔复习",
      title: "根据下一条LearningEvent动态重排",
      detail: adaptive.value?.policy_version ?? "evidence-aware-v1",
      status: "future",
      reason: "完成后重新请求路径，不预写固定结论",
    },
  ];
});
const relevantRoutes = computed(() => {
  const tasks = ["subjective_scoring", "learning_support", "teaching_judge", "response_assist"];
  return tasks.map((task) => {
    const route = modelCatalog.value?.routes.find((row) => row.task === task);
    const smallConnected = Boolean(
      modelCatalog.value?.small_model_enabled
      && modelCatalog.value.small_model_tasks.includes(task),
    );
    return { task, route, smallConnected };
  });
});

function stateLabel(state?: AdaptiveKnowledgeEvidence): string {
  if (!state?.event_count) return "insufficient_evidence";
  if (state.evidence_status === "provisional") return `provisional · ${state.event_count}条证据`;
  if (state.latest === "mastered") return `本次掌握 · ${state.event_count}条证据`;
  if (state.latest === "partial") return `部分掌握 · ${state.event_count}条证据`;
  if (state.latest === "missing") return `需要补强 · ${state.event_count}条证据`;
  return `证据不足 · ${state.event_count}条`;
}

function stateTone(state?: AdaptiveKnowledgeEvidence): string {
  if (!state?.event_count) return "insufficient";
  if (state.evidence_status === "provisional") return "provisional";
  return state.latest === "mastered" ? "mastered" : state.latest === "missing" ? "missing" : "partial";
}

function reasonLabel(code?: string): string {
  return REASON_LABELS[String(code ?? "")] ?? "根据当前证据与课程约束排序";
}

function eventLabel(type: string): string {
  const labels: Record<string, string> = {
    task_attempt_assessment: "选择任务",
    confusion_annotation: "困惑自报",
    teacher_reviewed_subjective_assessment: "教师批准主观题",
    case_stage_assessment: "案件阶段评阅",
  };
  return labels[type] ?? type;
}

function heatStyle(value: number): Record<string, string> {
  const normalized = Math.max(0, Math.min(1, (value - 0.4) / 0.18));
  const red = Math.round(188 - normalized * 73);
  const green = Math.round(83 + normalized * 75);
  const blue = Math.round(54 + normalized * 57);
  return { background: `rgba(${red}, ${green}, ${blue}, ${0.35 + normalized * 0.55})` };
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [catalog, adaptiveResult, timelineResult, subjective, caseResult, models] = await Promise.all([
      api.knowledgeCatalog(),
      api.adaptiveRecommendations(),
      api.adaptiveEvidenceTimeline(),
      api.subjectiveCatalog("review"),
      api.listCases(),
      api.modelCatalog(),
    ]);
    cards.value = catalog.knowledge_cards;
    adaptive.value = adaptiveResult;
    timeline.value = timelineResult.events;
    subjectiveTasks.value = subjective.tasks;
    cases.value = caseResult.cases;
    modelCatalog.value = models;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    loading.value = false;
  }
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") emit("close");
}

onMounted(() => {
  window.addEventListener("keydown", handleKeydown);
  void load();
});
onUnmounted(() => window.removeEventListener("keydown", handleKeydown));
</script>

<template>
  <div class="cog-layer">
    <section class="cog-board" role="dialog" aria-modal="true" aria-label="认知诊断与个性化路径驾驶舱">
      <header class="cog-head">
        <div class="cog-brand">
          <span class="cog-seal">诊</span>
          <div><p class="kicker mono">EVIDENCE-KT · ORCDF SHADOW · PATH</p><h2>刑法认知诊断驾驶舱</h2></div>
        </div>
        <nav class="cog-tabs" aria-label="认知诊断功能">
          <button :class="{ active: tab === 'diagnosis' }" @click="tab = 'diagnosis'">在线诊断</button>
          <button :class="{ active: tab === 'orcdf' }" @click="tab = 'orcdf'">ORCDF SHADOW</button>
          <button :class="{ active: tab === 'path' }" @click="tab = 'path'">个性化路径</button>
          <button :class="{ active: tab === 'models' }" @click="tab = 'models'">模型路由</button>
        </nav>
        <div class="cog-badges mono"><span>在线保守画像</span><span>实验结果隔离</span><span>AI内容已标识</span></div>
        <button class="cog-close" aria-label="关闭认知诊断" @click="emit('close')">×</button>
      </header>

      <div v-if="loading" class="cog-state"><span class="cog-seal">析</span><p>正在汇集学习证据、实验快照与推荐约束……</p></div>
      <div v-else-if="error" class="cog-state cog-state--error"><span>!</span><p>{{ error }}</p><button @click="load">重新加载</button></div>

      <main v-else class="cog-content">
        <template v-if="tab === 'diagnosis'">
          <section class="diagnosis-hero">
            <div>
              <p class="kicker mono">ONLINE · {{ adaptive?.policy_version ?? 'evidence-aware-v1' }}</p>
              <h3>Evidence-KT / V0 保守画像</h3>
              <p>只根据当前刑法学生的不可变LearningEvent更新；状态不是校准掌握概率。</p>
            </div>
            <div class="hero-metrics">
              <div><b>{{ profile?.eligible_event_count ?? 0 }}</b><span>合格事件</span></div>
              <div><b>{{ observedCount }}/{{ cards.length }}</b><span>已观察知识</span></div>
              <div><b>{{ insufficientCount }}</b><span>证据不足</span></div>
              <div><b>{{ confusionCount }}</b><span>主动困惑</span></div>
            </div>
          </section>

          <div class="diagnosis-grid">
            <section class="panel knowledge-panel">
              <header><div><p class="kicker mono">KNOWLEDGE EVIDENCE</p><h3>知识点掌握与置信状态</h3></div><span>非概率</span></header>
              <div class="knowledge-table">
                <article v-for="row in knowledgeRows" :key="row.card.knowledge_id">
                  <span :class="['state-dot', `state-dot--${stateTone(row.evidence)}`]"></span>
                  <div><strong>{{ row.card.canonical_name }}</strong><small>{{ row.card.law_article_refs.join(' · ') || row.card.chapter }}</small></div>
                  <div class="evidence-count mono"><b>{{ row.evidence?.event_count ?? 0 }}</b><span>events</span></div>
                  <span :class="['state-pill', `state-pill--${stateTone(row.evidence)}`]">{{ stateLabel(row.evidence) }}</span>
                </article>
              </div>
            </section>

            <section class="panel timeline-panel">
              <header><div><p class="kicker mono">LEARNING EVENT LEDGER</p><h3>行为序列与状态更新</h3></div><span>{{ timeline.length }} events</span></header>
              <ol v-if="timeline.length" class="timeline">
                <li v-for="(event, index) in timeline" :key="event.event_id">
                  <span class="timeline-no mono">{{ String(index + 1).padStart(2, '0') }}</span>
                  <div class="timeline-line"><i></i></div>
                  <div><strong>{{ eventLabel(event.event_type) }}</strong><p>{{ event.knowledge_verdicts.map((row) => `${row.knowledge_name ?? row.kp ?? '知识证据'}:${row.status ?? 'observed'}`).join('；') || event.stage }}</p><small class="mono">{{ event.created_at?.slice(0, 16).replace('T', ' ') }} · {{ event.event_id }}</small></div>
                  <span :class="['eligibility', { yes: event.long_term_profile_eligible }]">{{ event.long_term_profile_eligible ? '画像可用' : '仅形成性' }}</span>
                </li>
              </ol>
              <div v-else class="empty-evidence"><span>0</span><h4>尚无行为事件</h4><p>先完成一题，系统才会从insufficient_evidence开始建立画像。</p></div>
            </section>

            <section class="panel signal-panel">
              <div><p class="kicker mono">REPEATED ERRORS</p><h3>重复错误</h3><ul><li v-for="row in errorCounts" :key="row.tag"><span>{{ row.tag }}</span><b>×{{ row.count }}</b></li><li v-if="!errorCounts.length">暂无重复错误标签</li></ul></div>
              <div><p class="kicker mono">CONFUSIONS</p><h3>困惑信号</h3><ul><li v-for="(row, id) in profile?.confusions ?? {}" :key="id"><span>{{ row.knowledge_name ?? id }}</span><b>×{{ row.count ?? 0 }}</b></li><li v-if="!Object.keys(profile?.confusions ?? {}).length">暂无主动困惑</li></ul></div>
              <footer><strong>证据边界</strong><p>至少3个合格事件且覆盖2道不同任务后才形成provisional；困惑是自报信号，不直接降低掌握。当前状态未经过刑法课堂外部校准。</p></footer>
            </section>
          </div>
        </template>

        <template v-else-if="tab === 'orcdf'">
          <section class="shadow-banner">
            <span>SHADOW</span>
            <div><p class="kicker mono">{{ ORCDF_SHADOW.status }}</p><h3>ORCDF真实训练实验，不进入当前刑法学生画像</h3><p>{{ ORCDF_SHADOW.sourceScope }} · {{ ORCDF_SHADOW.protocol }}</p></div>
            <strong>未校准掌握概率</strong>
          </section>

          <section class="orcdf-versions">
            <article v-for="row in ORCDF_SHADOW.versions" :key="row.id" :class="`version--${row.tone}`">
              <header><span>{{ row.id }}</span><div><h3>{{ row.title }}</h3><p>{{ row.scope }}</p></div></header>
              <dl><div><dt>Q矩阵</dt><dd>{{ row.qMatrix }}</dd></div><div><dt>主范围 AUC</dt><dd>{{ row.mainAuc.toFixed(4) }}</dd></div><div><dt>同47题 AUC</dt><dd>{{ row.common47Auc.toFixed(4) }}</dd></div></dl>
              <div class="auc-track"><i :style="{ width: `${row.common47Auc * 100}%` }"></i></div>
            </article>
          </section>

          <div class="orcdf-detail-grid">
            <section class="panel bootstrap-panel"><header><div><p class="kicker mono">COMMON47 · STUDENT CLUSTER BOOTSTRAP</p><h3>受控47题比较</h3></div><span>seed42 · 1000次</span></header><div class="bootstrap-rows"><article v-for="row in ORCDF_SHADOW.bootstrap" :key="row.pair"><strong>{{ row.pair }}</strong><b :class="{ negative: row.difference < 0 }">{{ row.difference > 0 ? '+' : '' }}{{ row.difference.toFixed(4) }}</b><span class="mono">95% CI {{ row.ci }}</span><em>{{ row.conclusion }}</em></article></div><p class="boundary-note">V0/V1/V2主范围不同；只有同47题比较可讨论Q矩阵差异，且V2没有证明优于V1。</p></section>
            <section class="panel heatmap-panel"><header><div><p class="kicker mono">REAL MASTERY SLICE · V2 S42</p><h3>{{ ORCDF_SHADOW.heatmap.title }}</h3></div><span>6×8切片</span></header><div class="heatmap-scroll"><div class="heatmap" :style="{ gridTemplateColumns: `84px repeat(${ORCDF_SHADOW.heatmap.knowledge.length}, minmax(64px,1fr))` }"><span></span><span v-for="name in ORCDF_SHADOW.heatmap.knowledge" :key="name" class="heat-label">{{ name }}</span><template v-for="row in ORCDF_SHADOW.heatmap.rows" :key="row.student"><strong>{{ row.student }}</strong><span v-for="(value, index) in row.values" :key="`${row.student}-${index}`" class="heat-cell mono" :style="heatStyle(value)">{{ value.toFixed(3) }}</span></template></div></div><p class="boundary-note">{{ ORCDF_SHADOW.heatmap.boundary }}</p></section>
          </div>

          <section class="generic-init"><div><p class="kicker mono">GENERIC PRETRAINING INITIALIZATION</p><h3>通用层迁移，不搬运旧学生/题目/知识参数</h3></div><div class="init-score"><span>V2 seed42 scratch</span><b>{{ ORCDF_SHADOW.genericInitialization.scratchV2Seed42Auc.toFixed(4) }}</b></div><span class="init-arrow">→</span><div class="init-score"><span>同宇宙初始化实验</span><b>{{ ORCDF_SHADOW.genericInitialization.initializedV2Seed42Auc.toFixed(4) }}</b></div><p>{{ ORCDF_SHADOW.genericInitialization.rule }}</p></section>
          <section class="shadow-boundaries"><p v-for="item in ORCDF_SHADOW.boundaries" :key="item"><span>!</span>{{ item }}</p><footer class="mono">summary {{ ORCDF_SHADOW.provenance.summarySha256.slice(0, 16) }} · mastery {{ ORCDF_SHADOW.provenance.masterySha256.slice(0, 16) }}</footer></section>
        </template>

        <template v-else-if="tab === 'path'">
          <section class="path-hero"><div><p class="kicker mono">POLICY · {{ adaptive?.policy_version ?? 'evidence-aware-v1' }}</p><h3>从证据薄弱点到下一条LearningEvent</h3><p>算法排序任务，AI只解释和执行；每次完成后重新计算，不预写“最优路径”。</p></div><button @click="emit('openJourney')">进入当前推荐任务 →</button></section>
          <section class="path-map">
            <article v-for="(node, index) in pathNodes" :key="node.no" :class="[`path-node--${node.status}`]">
              <span class="path-no mono">{{ node.no }}</span><div class="path-card"><p class="kicker mono">{{ node.type }}</p><h3>{{ node.title }}</h3><span>{{ node.detail }}</span><footer>{{ node.reason }}</footer></div><div v-if="index < pathNodes.length - 1" class="path-connector"><i></i><span>证据更新</span></div>
            </article>
          </section>
          <section class="path-legend"><span><i class="current"></i>当前薄弱点</span><span><i class="ready"></i>可执行任务</span><span><i class="future"></i>完成后重排</span><p>选择题、教师批准主观题和案件Rubric可更新长期画像；困惑只改变优先级，不直接降低掌握。</p></section>
        </template>

        <template v-else>
          <section class="model-hero"><div><p class="kicker mono">MODEL ADAPTER · ROUTE WITHOUT UI CHANGE</p><h3>基础模型 / Prompt / RAG / RAG+微调</h3><p>当前运行基线与预留微调端点分开显示；未连接时不生成模拟指标。</p></div><div class="model-status"><span :class="{ connected: modelCatalog?.small_model_enabled }"></span><strong>{{ modelCatalog?.small_model_enabled ? '微调端点已连接' : '微调端点已预留 · 当前未连接' }}</strong></div></section>
          <section class="route-grid"><article v-for="row in relevantRoutes" :key="row.task"><header><span>{{ row.task.slice(0, 2).toUpperCase() }}</span><div><p class="kicker mono">{{ row.task }}</p><h3>{{ row.route?.model_name || '未配置' }}</h3></div></header><dl><div><dt>当前provider</dt><dd>{{ row.route?.provider ?? 'none' }}</dd></div><div><dt>端点主机</dt><dd>{{ row.route?.api_base ?? 'not_configured' }}</dd></div><div><dt>当前基线端点</dt><dd :class="row.route?.configured ? 'ok' : 'off'">{{ row.route?.configured ? 'connected' : 'not_connected' }}</dd></div><div><dt>RAG+微调</dt><dd :class="row.smallConnected ? 'ok' : 'off'">{{ row.smallConnected ? 'connected' : 'not_connected' }}</dd></div></dl><footer>Key不返回前端 · URL私有路径已脱敏</footer></article></section>
          <section class="comparison-lane"><article><span>01</span><h3>基础模型</h3><p>只做离线基线，不直接给正式结论</p></article><i>→</i><article><span>02</span><h3>Prompt / Few-shot</h3><p>固定JSON、Rubric与拒答格式</p></article><i>→</i><article><span>03</span><h3>可信RAG</h3><p>权威法条、版本、Evidence门禁</p></article><i>→</i><article class="pending"><span>04</span><h3>RAG + 微调</h3><p>{{ modelCatalog?.small_model_enabled ? '独立金标准验收后灰度接管' : 'not_connected · 不宣称已完成LoRA/SFT' }}</p></article></section>
          <section class="model-boundary"><strong>验收门禁</strong><p>微调模型必须与基础/Prompt/RAG同条件比较格式遵循、引用忠实度、法学专家评分、拒答、延迟和成本；未通过时继续使用当前基线。</p><span class="mono">failover {{ modelCatalog?.failover.mode }} · {{ modelCatalog?.failover.circuit_seconds }}s circuit</span></section>
        </template>
      </main>
    </section>
  </div>
</template>

<style scoped>
.cog-layer{position:fixed;inset:0;z-index:1360;padding:18px;background:radial-gradient(circle at 75% 8%,rgba(66,111,128,.15),transparent 32%),radial-gradient(circle at 8% 82%,rgba(176,138,62,.1),transparent 30%),rgba(4,4,3,.93);backdrop-filter:blur(13px)}
.cog-board{height:100%;min-height:0;display:flex;flex-direction:column;overflow:hidden;color:var(--parchment);border:1px solid rgba(100,139,153,.46);background:linear-gradient(135deg,#151815,#090b0a 72%);box-shadow:0 40px 110px #000d}
.cog-head{min-height:82px;display:grid;grid-template-columns:minmax(300px,1fr) auto minmax(250px,1fr) 38px;align-items:center;gap:18px;padding:12px 18px 12px 23px;border-bottom:1px solid rgba(100,139,153,.32);background:linear-gradient(180deg,rgba(25,30,28,.98),rgba(12,15,14,.98))}.cog-brand{display:flex;align-items:center;gap:13px}.cog-seal{width:47px;height:47px;display:grid;place-items:center;color:#dce9ec;border:1px solid #789dac;box-shadow:inset 0 0 0 3px #142025;font-family:var(--font-display);font-size:1.08rem;font-weight:800;transform:rotate(-2deg)}.kicker{margin:0 0 3px;color:#87aebb;font-size:.61rem;letter-spacing:.16em}.cog-brand h2{font-size:1.28rem}.cog-tabs{display:flex;border:1px solid var(--line-strong)}.cog-tabs button{padding:9px 13px;color:var(--parchment-dim);border:0;border-right:1px solid var(--line);background:transparent;font-family:var(--font-display);font-size:.75rem;cursor:pointer}.cog-tabs button:last-child{border:0}.cog-tabs button.active{color:#e5eff0;background:rgba(100,139,153,.16);box-shadow:inset 0 -2px #87aebb}.cog-badges{display:flex;justify-content:flex-end;gap:6px}.cog-badges span{padding:4px 6px;color:var(--parchment-faint);border:1px solid var(--line);font-size:.6rem}.cog-close{width:36px;height:36px;color:var(--parchment-muted);border:1px solid var(--line-strong);background:transparent;font-size:1.35rem;cursor:pointer}
.cog-state{flex:1;display:grid;place-content:center;justify-items:center;gap:14px;color:var(--parchment-muted)}.cog-state--error>span{width:43px;height:43px;display:grid;place-items:center;color:#e1a48f;border:1px solid var(--accent)}.cog-state button{padding:7px 12px;color:var(--parchment);border:1px solid var(--line-strong);background:transparent}.cog-content{flex:1;min-height:0;overflow-y:auto;padding:22px clamp(20px,2.7vw,44px) 48px;background:linear-gradient(90deg,rgba(255,255,255,.013) 1px,transparent 1px) 0 0/56px 56px}
.diagnosis-hero,.path-hero,.model-hero{display:flex;align-items:flex-start;justify-content:space-between;gap:22px;padding:0 0 17px;border-bottom:1px solid rgba(100,139,153,.34)}.diagnosis-hero h3,.path-hero h3,.model-hero h3,.shadow-banner h3{font-size:1.4rem}.diagnosis-hero>div>p:last-child,.path-hero>div>p:last-child,.model-hero>div>p:last-child,.shadow-banner div>p:last-child{margin:5px 0 0;color:var(--parchment-dim);font-size:.73rem}.hero-metrics{display:grid!important;grid-template-columns:repeat(4,112px);border:1px solid var(--line)}.hero-metrics div{padding:10px;text-align:center;border-right:1px solid var(--line)}.hero-metrics div:last-child{border:0}.hero-metrics b{display:block;font-family:var(--font-mono);font-size:1.15rem}.hero-metrics span{color:var(--parchment-faint);font-size:.63rem}.diagnosis-grid{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:13px;margin-top:15px}.panel{min-width:0;padding:15px;border:1px solid var(--line);background:rgba(255,255,255,.016)}.panel>header{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;margin-bottom:12px}.panel>header h3{font-size:1rem}.panel>header>span{color:var(--parchment-faint);font-family:var(--font-mono);font-size:.62rem}.knowledge-panel{grid-row:span 2}.knowledge-table{display:grid;gap:4px}.knowledge-table article{display:grid;grid-template-columns:9px minmax(0,1fr) 42px 155px;align-items:center;gap:9px;padding:8px;border-bottom:1px solid var(--line)}.state-dot{width:7px;height:7px;background:#67665f}.state-dot--mastered{background:#85a878}.state-dot--partial{background:#b08a3e}.state-dot--missing{background:#c45b38}.state-dot--provisional{background:#789dac}.state-dot--insufficient{background:#585a56}.knowledge-table article>div:nth-child(2){min-width:0;display:grid}.knowledge-table strong{overflow:hidden;font-family:var(--font-display);font-size:.75rem;white-space:nowrap;text-overflow:ellipsis}.knowledge-table small{color:var(--parchment-faint);font-size:.59rem}.evidence-count{display:grid;text-align:center}.evidence-count b{font-size:.78rem}.evidence-count span{color:var(--parchment-faint);font-size:.5rem}.state-pill{padding:3px 5px;text-align:center;border:1px solid var(--line);font-size:.6rem}.state-pill--mastered{color:#b9d0ad;border-color:rgba(122,153,98,.42)}.state-pill--partial{color:#e0c187;border-color:rgba(176,138,62,.42)}.state-pill--missing{color:#e3a08b;border-color:rgba(196,71,27,.45)}.state-pill--provisional{color:#b9d2db;border-color:rgba(100,139,153,.46)}.state-pill--insufficient{color:var(--parchment-faint)}.timeline{list-style:none;margin:0;padding:0;display:grid}.timeline li{display:grid;grid-template-columns:26px 16px minmax(0,1fr) 66px;gap:7px;min-height:61px}.timeline-no{padding-top:2px;color:#789dac;font-size:.58rem}.timeline-line{position:relative}.timeline-line::before{content:"";position:absolute;left:7px;top:10px;bottom:-3px;width:1px;background:var(--line-strong)}.timeline li:last-child .timeline-line::before{bottom:40px}.timeline-line i{position:absolute;top:5px;left:3px;width:9px;height:9px;border:2px solid #789dac;background:#101412;transform:rotate(45deg)}.timeline strong{font-size:.75rem}.timeline p{margin:3px 0;color:var(--parchment-muted);font-size:.65rem}.timeline small{color:var(--parchment-faint);font-size:.54rem}.eligibility{align-self:start;padding:3px 4px;color:#d6a38d;border:1px solid rgba(196,71,27,.35);font-size:.55rem;text-align:center}.eligibility.yes{color:#b6cba9;border-color:rgba(122,153,98,.38)}.empty-evidence{min-height:220px;display:grid;place-content:center;justify-items:center;text-align:center;color:var(--parchment-faint)}.empty-evidence>span{font-family:var(--font-mono);font-size:2rem}.empty-evidence h4{margin:4px}.empty-evidence p{max-width:300px;font-size:.66rem}.signal-panel{display:grid;grid-template-columns:1fr 1fr;gap:13px}.signal-panel h3{font-size:.9rem}.signal-panel ul{list-style:none;margin:8px 0 0;padding:0}.signal-panel li{display:flex;justify-content:space-between;gap:8px;padding:5px 0;color:var(--parchment-muted);border-bottom:1px solid var(--line);font-size:.66rem}.signal-panel li b{color:#e0a076}.signal-panel footer{grid-column:1/-1;padding:8px 9px;border:1px dashed var(--line-strong)}.signal-panel footer strong{color:var(--accent);font-family:var(--font-display);font-size:.7rem}.signal-panel footer p{margin:3px 0 0;color:var(--parchment-faint);font-size:.61rem}
.shadow-banner{display:grid;grid-template-columns:70px minmax(0,1fr) auto;align-items:center;gap:17px;padding:13px 16px;border:1px solid rgba(196,71,27,.48);background:linear-gradient(90deg,rgba(196,71,27,.09),transparent)}.shadow-banner>span{width:58px;height:58px;display:grid;place-items:center;color:#e5aa93;border:1px solid currentColor;font-family:var(--font-mono);font-size:.67rem;transform:rotate(-2deg)}.shadow-banner>strong{padding:6px 8px;color:#e1aa92;border:1px solid rgba(196,71,27,.42);font-size:.7rem}.orcdf-versions{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0}.orcdf-versions article{padding:14px;border:1px solid var(--line);background:rgba(255,255,255,.016)}.orcdf-versions article.version--llm{border-color:rgba(176,138,62,.42)}.orcdf-versions article.version--teacher{border-color:rgba(100,139,153,.5)}.orcdf-versions header{display:flex;align-items:center;gap:11px}.orcdf-versions header>span{width:38px;height:38px;display:grid;place-items:center;border:1px solid currentColor;font-family:var(--font-mono)}.orcdf-versions h3{font-size:.92rem}.orcdf-versions header p{margin:3px 0 0;color:var(--parchment-faint);font-size:.62rem}.orcdf-versions dl{margin:12px 0}.orcdf-versions dl div{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px solid var(--line);font-size:.65rem}.orcdf-versions dt{color:var(--parchment-faint)}.orcdf-versions dd{margin:0;text-align:right}.auc-track{height:5px;background:var(--line)}.auc-track i{display:block;height:100%;background:linear-gradient(90deg,#7f5945,#b08a3e,#789dac)}.orcdf-detail-grid{display:grid;grid-template-columns:.8fr 1.2fr;gap:12px}.bootstrap-rows{display:grid;gap:6px}.bootstrap-rows article{display:grid;grid-template-columns:70px 64px 1fr 62px;align-items:center;gap:7px;padding:7px;border-bottom:1px solid var(--line)}.bootstrap-rows strong{font-size:.7rem}.bootstrap-rows b{color:#acd09c;font-family:var(--font-mono)}.bootstrap-rows b.negative{color:#e3a08b}.bootstrap-rows span{color:var(--parchment-dim);font-size:.6rem}.bootstrap-rows em{color:var(--parchment-faint);font-size:.59rem;font-style:normal}.boundary-note{margin:10px 0 0;color:var(--parchment-faint);font-size:.61rem;line-height:1.5}.heatmap-scroll{overflow-x:auto}.heatmap{min-width:650px;display:grid;gap:3px;align-items:center}.heat-label{height:47px;display:flex;align-items:flex-end;color:var(--parchment-faint);font-size:.53rem;line-height:1.2;writing-mode:vertical-rl}.heatmap>strong{font-size:.59rem;font-weight:500}.heat-cell{padding:8px 3px;color:#f0e8da;text-align:center;font-size:.56rem}.generic-init{display:grid;grid-template-columns:1fr 120px 28px 120px minmax(220px,.8fr);align-items:center;gap:12px;margin-top:12px;padding:13px;border:1px solid rgba(122,153,98,.38);background:rgba(122,153,98,.035)}.generic-init h3{font-size:.92rem}.init-score{display:grid;text-align:center}.init-score span{color:var(--parchment-faint);font-size:.57rem}.init-score b{font-family:var(--font-mono);font-size:1.2rem}.init-arrow{color:#8eb184;text-align:center}.generic-init>p{margin:0;color:var(--parchment-dim);font-size:.63rem;line-height:1.5}.shadow-boundaries{display:grid;grid-template-columns:repeat(2,1fr);gap:5px;margin-top:10px}.shadow-boundaries p{margin:0;padding:6px 8px;color:var(--parchment-faint);border:1px dashed var(--line);font-size:.61rem}.shadow-boundaries p span{margin-right:6px;color:var(--accent)}.shadow-boundaries footer{grid-column:1/-1;color:var(--parchment-faint);font-size:.54rem;text-align:right}
.path-hero button{padding:9px 14px;color:#e5efdf;border:1px solid rgba(122,153,98,.48);background:rgba(122,153,98,.08);font-family:var(--font-display);cursor:pointer}.path-map{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:20px;margin-top:30px}.path-map article{position:relative;min-width:0}.path-no{position:absolute;z-index:2;top:-13px;left:12px;padding:4px 6px;color:#89afba;border:1px solid rgba(100,139,153,.48);background:#111513;font-size:.6rem}.path-card{height:230px;display:flex;flex-direction:column;padding:22px 12px 12px;border:1px solid var(--line);background:linear-gradient(155deg,rgba(255,255,255,.026),transparent)}.path-card h3{font-size:.82rem;line-height:1.45}.path-card>span{margin-top:7px;color:var(--parchment-faint);font-size:.61rem;line-height:1.45}.path-card footer{margin-top:auto;padding-top:8px;color:var(--parchment-dim);border-top:1px dashed var(--line);font-size:.59rem;line-height:1.45}.path-node--current .path-card{border-color:rgba(196,71,27,.55);box-shadow:inset 0 3px var(--accent)}.path-node--ready .path-card{border-color:rgba(122,153,98,.44);box-shadow:inset 0 3px var(--accent-success)}.path-node--future .path-card{border-style:dashed}.path-node--locked .path-card{opacity:.48}.path-node--complete .path-card{border-color:rgba(100,139,153,.38)}.path-connector{position:absolute;z-index:3;top:104px;left:calc(100% + 2px);width:36px;display:grid;justify-items:center}.path-connector i{width:36px;height:1px;background:linear-gradient(90deg,#789dac,transparent)}.path-connector i::after{content:"";float:right;width:6px;height:6px;margin-top:-3px;border-top:1px solid #789dac;border-right:1px solid #789dac;transform:rotate(45deg)}.path-connector span{margin-top:6px;color:var(--parchment-faint);font-size:.48rem;writing-mode:vertical-rl}.path-legend{display:flex;align-items:center;gap:16px;margin-top:18px;padding:10px;border:1px solid var(--line)}.path-legend>span{display:flex;align-items:center;gap:5px;color:var(--parchment-dim);font-size:.62rem}.path-legend i{width:8px;height:8px;background:#666}.path-legend i.current{background:var(--accent)}.path-legend i.ready{background:var(--accent-success)}.path-legend i.future{background:#789dac}.path-legend p{margin:0 0 0 auto;color:var(--parchment-faint);font-size:.61rem}
.model-status{display:flex;align-items:center;gap:8px;padding:7px 9px;border:1px solid var(--line)}.model-status span{width:8px;height:8px;background:var(--accent)}.model-status span.connected{background:var(--accent-success)}.model-status strong{font-size:.7rem}.route-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:16px}.route-grid article{padding:14px;border:1px solid var(--line);background:rgba(255,255,255,.016)}.route-grid header{display:flex;align-items:center;gap:10px}.route-grid header>span{width:34px;height:34px;display:grid;place-items:center;color:#b9d2db;border:1px solid rgba(100,139,153,.42);font-family:var(--font-mono)}.route-grid h3{overflow:hidden;font-size:.86rem;white-space:nowrap;text-overflow:ellipsis}.route-grid dl{margin:13px 0}.route-grid dl div{display:grid;grid-template-columns:1fr minmax(0,1.3fr);gap:7px;padding:6px 0;border-bottom:1px solid var(--line);font-size:.61rem}.route-grid dt{color:var(--parchment-faint)}.route-grid dd{overflow:hidden;margin:0;text-align:right;white-space:nowrap;text-overflow:ellipsis}.route-grid dd.ok{color:#b7cba9}.route-grid dd.off{color:#df9e86}.route-grid footer{color:var(--parchment-faint);font-size:.57rem}.comparison-lane{display:grid;grid-template-columns:1fr 28px 1fr 28px 1fr 28px 1fr;align-items:center;gap:7px;margin-top:14px}.comparison-lane article{min-height:115px;padding:13px;border:1px solid rgba(122,153,98,.38);background:rgba(122,153,98,.025)}.comparison-lane article.pending{border-style:dashed;border-color:rgba(196,71,27,.45)}.comparison-lane article>span{color:#789dac;font-family:var(--font-mono);font-size:.61rem}.comparison-lane h3{margin:5px 0;font-size:.85rem}.comparison-lane p{margin:0;color:var(--parchment-faint);font-size:.61rem;line-height:1.45}.comparison-lane>i{color:#789dac;text-align:center;font-style:normal}.model-boundary{display:grid;grid-template-columns:80px 1fr auto;align-items:center;gap:12px;margin-top:13px;padding:10px;border:1px dashed var(--line-strong)}.model-boundary strong{color:var(--accent);font-family:var(--font-display)}.model-boundary p{margin:0;color:var(--parchment-dim);font-size:.63rem}.model-boundary span{color:var(--parchment-faint);font-size:.55rem}
@media(max-width:1180px){.cog-head{grid-template-columns:1fr auto 38px}.cog-badges{display:none}.diagnosis-grid{grid-template-columns:1fr}.knowledge-panel{grid-row:auto}.path-map{grid-template-columns:repeat(4,1fr)}.path-connector{display:none}.route-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:820px){.cog-layer{padding:0}.cog-head{grid-template-columns:1fr 38px;padding:10px 12px}.cog-tabs{grid-column:1/-1;grid-row:2;overflow-x:auto}.cog-tabs button{flex:1;white-space:nowrap}.cog-content{padding:16px 13px 40px}.diagnosis-hero,.path-hero,.model-hero{display:block}.hero-metrics{grid-template-columns:repeat(2,1fr);margin-top:12px}.orcdf-versions,.orcdf-detail-grid,.route-grid{grid-template-columns:1fr}.generic-init{grid-template-columns:1fr 1fr}.generic-init>div:first-child,.generic-init>p{grid-column:1/-1}.init-arrow{display:none}.path-map{grid-template-columns:repeat(2,1fr)}.comparison-lane{grid-template-columns:1fr}.comparison-lane>i{transform:rotate(90deg)}.model-boundary{grid-template-columns:1fr}.shadow-boundaries{grid-template-columns:1fr}.shadow-boundaries footer{grid-column:1}.signal-panel{grid-template-columns:1fr}.signal-panel footer{grid-column:1}.knowledge-table article{grid-template-columns:9px minmax(0,1fr) 38px}.state-pill{grid-column:2/-1}.timeline li{grid-template-columns:24px 14px minmax(0,1fr)}.eligibility{grid-column:3}.cog-brand h2{font-size:1.05rem}}
</style>
