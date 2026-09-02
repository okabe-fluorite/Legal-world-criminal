<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { api } from "../lib/api";
import { ORCDF_SHADOW } from "../data/orcdfShadow";
import AITutor from "./AITutor.vue";
import RealtimeVoicePanel from "./RealtimeVoicePanel.vue";
import type {
  AdaptiveKnowledgeEvidence,
  AdaptiveRecommendationResponse,
  CasePickerEntry,
  EvidenceTimelineEvent,
  KnowledgeCard,
  MediaAsset,
  MediaCapabilitiesResponse,
  MediaJob,
  ModelCatalogResponse,
  SubjectiveTask,
} from "../lib/types";

const emit = defineEmits<{ close: []; openJourney: [] }>();
const tab = ref<"diagnosis" | "orcdf" | "path" | "graphs" | "models" | "media">("diagnosis");
const loading = ref(true);
const error = ref("");
const adaptive = ref<AdaptiveRecommendationResponse | null>(null);
const cards = ref<KnowledgeCard[]>([]);
const timeline = ref<EvidenceTimelineEvent[]>([]);
const subjectiveTasks = ref<SubjectiveTask[]>([]);
const cases = ref<CasePickerEntry[]>([]);
const modelCatalog = ref<ModelCatalogResponse | null>(null);
const mediaCatalog = ref<MediaCapabilitiesResponse | null>(null);
const mediaAsset = ref<MediaAsset | null>(null);
const mediaJob = ref<MediaJob | null>(null);
const mediaBusy = ref(false);
const mediaMessage = ref("");
const browserSpeechSupported = ref(false);
const browserSpeaking = ref(false);
const serverAudioUrl = ref("");
const lastTtsAssetId = ref("");
const speechText = ref("罪刑法定原则要求法无明文规定不为罪，法无明文规定不处罚。本段为AI合成语音。");

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
const knowledgeGraph = computed(() => {
  const byId = new Map(cards.value.map((card) => [card.knowledge_id, card]));
  const levelCache = new Map<string, number>();
  const visiting = new Set<string>();
  const levelOf = (id: string): number => {
    if (levelCache.has(id)) return levelCache.get(id) ?? 0;
    if (visiting.has(id)) return 0;
    visiting.add(id);
    const card = byId.get(id);
    const parentLevels = (card?.prerequisite_ids ?? [])
      .filter((parent) => byId.has(parent))
      .map((parent) => levelOf(parent));
    const level = parentLevels.length ? Math.max(...parentLevels) + 1 : 0;
    visiting.delete(id);
    levelCache.set(id, level);
    return level;
  };
  const groups = new Map<number, KnowledgeCard[]>();
  for (const card of cards.value) {
    const level = levelOf(card.knowledge_id);
    groups.set(level, [...(groups.get(level) ?? []), card]);
  }
  const positions = new Map<string, { x: number; y: number }>();
  const nodes = [...groups.entries()].flatMap(([level, rows]) =>
    rows.map((card, index) => {
      const gap = rows.length > 1 ? 760 / (rows.length - 1) : 0;
      const x = rows.length > 1 ? 120 + gap * index : 500;
      const y = 65 + level * 128;
      positions.set(card.knowledge_id, { x, y });
      return { card, x, y, level };
    }),
  );
  const edges = cards.value.flatMap((card) =>
    card.prerequisite_ids
      .filter((parent) => positions.has(parent) && positions.has(card.knowledge_id))
      .map((parent) => ({
        id: `${parent}:${card.knowledge_id}`,
        from: positions.get(parent)!,
        to: positions.get(card.knowledge_id)!,
      })),
  );
  return { nodes, edges };
});
const argumentTemplate = computed(() => {
  const target = targetKnowledge.value;
  const recommendation = recommendations.value[0];
  const caseRow = cases.value[0];
  return [
    { code: "ISSUE", title: "争点", detail: target?.canonical_name ?? "等待诊断目标", tone: "issue" },
    { code: "FACT", title: "关键事实", detail: recommendation?.stem ?? recommendation?.question ?? "完成推荐任务后提取", tone: "fact" },
    { code: "EVID", title: "受治理证据", detail: `${target?.standard_evidence_ids.length ?? 0}条Evidence · ${target?.law_article_refs.join(" / ") || "待检索"}`, tone: "evidence" },
    { code: "CLAIM", title: "学生主张", detail: "由学生提交，不预生成标准结论", tone: "claim" },
    { code: "CHAL", title: "对抗质询", detail: caseRow ? `${caseRow.title} · AI检查遗漏与反方观点` : "进入案件后生成", tone: "challenge" },
    { code: "GATE", title: "核验与复盘", detail: "引用检查 + Rubric + 教师确认", tone: "gate" },
  ];
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
      detail: roleReversal ? "反方立场 · 教师确认" : "未映射",
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
const pathTutorSpeech = computed(() => {
  const first = pathNodes.value[0];
  if (!first) return "";
  return `当前下一步围绕${first.title}。${first.detail}。推荐依据来自当前Evidence事件、先修关系和已完成任务；这是一条可解释候选路径，不是因果最优证明。`;
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
const mediaTranscript = computed(() => String(mediaJob.value?.result?.transcript ?? ""));

function mediaCapabilityStatus(capabilityId: string): string {
  return mediaCatalog.value?.capabilities.find((row) => row.capability_id === capabilityId)?.connection_status
    ?? "not_connected";
}

function statusLabelFriendly(value?: string): string {
  return ({
    available: "可用",
    configured_not_verified: "已配置，等待首次使用",
    not_configured: "未配置",
    not_connected: "尚未连接",
    succeeded: "已完成",
    needs_review: "待复核",
    failed: "处理失败",
    queued: "排队中",
    running: "处理中",
  } as Record<string, string>)[String(value || "")] ?? "状态待确认";
}

function providerLabel(value?: string): string {
  const provider = String(value || "").toLowerCase();
  if (provider.includes("iflytek") || provider.includes("xfyun")) return "讯飞在线语音";
  if (provider === "none" || !provider) return "暂无外部服务";
  return "已配置服务";
}

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

function capabilityLabel(id: string): string {
  const labels: Record<string, string> = {
    private_asset_upload: "私有媒体上传",
    speech_to_text: "语音识别 ASR",
    vision_understanding: "图像理解 / OCR",
    text_to_speech: "语音合成 TTS",
    digital_human: "数字人渲染",
  };
  return labels[id] ?? id;
}

function newJobId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

function readWithBrowserSpeech(): void {
  if (!browserSpeechSupported.value) {
    mediaMessage.value = "当前浏览器不支持SpeechSynthesis，本地朗读降级不可用。";
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(speechText.value);
  utterance.lang = "zh-CN";
  utterance.rate = 0.94;
  utterance.onend = () => { browserSpeaking.value = false; };
  utterance.onerror = () => {
    browserSpeaking.value = false;
    mediaMessage.value = "浏览器朗读失败；可改用讯飞在线TTS生成可下载音频。";
  };
  browserSpeaking.value = true;
  mediaMessage.value = "正在使用浏览器SpeechSynthesis本地降级；本次未调用讯飞。";
  window.speechSynthesis.speak(utterance);
}

async function refreshMediaCapabilities(): Promise<void> {
  mediaCatalog.value = await api.mediaCapabilities();
}

async function checkServerSpeech(): Promise<void> {
  mediaBusy.value = true;
  mediaMessage.value = "";
  try {
    mediaJob.value = await api.synthesizeSpeech({
      job_id: newJobId("tts"),
      text: speechText.value,
      voice: "standard_zh",
      audio_format: "wav",
      provider: "xfyun_online_tts",
      ai_generated_disclosure: true,
    });
    if (mediaJob.value.status !== "succeeded") {
      mediaMessage.value = `讯飞TTS未成功：${mediaJob.value.error?.code ?? mediaJob.value.status}`;
      return;
    }
    const assetId = String(mediaJob.value.result?.output_asset_id ?? "");
    if (!assetId) throw new Error("讯飞TTS成功但未返回音频资产");
    if (serverAudioUrl.value) URL.revokeObjectURL(serverAudioUrl.value);
    const audio = await api.downloadMediaAsset(assetId);
    serverAudioUrl.value = URL.createObjectURL(audio);
    lastTtsAssetId.value = assetId;
    mediaMessage.value = `讯飞TTS真实生成${audio.size.toLocaleString()}字节WAV；AI合成标识保留。`;
    await refreshMediaCapabilities();
  } catch (reason) {
    mediaMessage.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    mediaBusy.value = false;
  }
}

async function transcribeLastTts(): Promise<void> {
  if (!lastTtsAssetId.value) return;
  mediaBusy.value = true;
  mediaMessage.value = "正在将刚生成的讯飞WAV送入讯飞IAT……";
  try {
    mediaJob.value = await api.startTranscription({
      job_id: newJobId("iat"),
      asset_id: lastTtsAssetId.value,
      language: "zh_cn",
      hotwords: ["罪刑法定", "明文规定", "不为罪", "不处罚"],
      provider: "xfyun_streaming_asr",
    });
    if (mediaJob.value.status !== "needs_review") {
      mediaMessage.value = `讯飞ASR未成功：${mediaJob.value.error?.code ?? mediaJob.value.status}`;
      return;
    }
    mediaMessage.value = "讯飞ASR已返回真实转写；结果需要复核，不进入画像或正式评分。";
    await refreshMediaCapabilities();
  } catch (reason) {
    mediaMessage.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    mediaBusy.value = false;
  }
}

async function checkAvatarInterface(): Promise<void> {
  mediaBusy.value = true;
  mediaMessage.value = "";
  try {
    mediaJob.value = await api.renderAvatar({
      job_id: newJobId("avatar"),
      script: speechText.value,
      avatar_id: "standard_presenter",
      provider: "auto",
      ai_generated_disclosure: true,
      likeness_consent_confirmed: false,
    });
    mediaMessage.value = "数字人接口已准备，但当前服务尚未连接。";
  } catch (reason) {
    mediaMessage.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    mediaBusy.value = false;
  }
}

async function handleAudioUpload(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  mediaBusy.value = true;
  mediaMessage.value = "正在安全保存音频并开始转写……";
  try {
    mediaAsset.value = await api.uploadMediaAsset(file, "transcription");
    mediaJob.value = await api.startTranscription({
      job_id: newJobId("asr"),
      asset_id: mediaAsset.value.asset_id,
      language: "zh_cn",
      hotwords: ["刑法", "正当防卫", "罪刑法定", "要件涵摄"],
      provider: "xfyun_streaming_asr",
    });
    mediaMessage.value = mediaJob.value.status === "needs_review"
      ? "讯飞ASR已生成真实转写；等待规则或教师复核，不进入画像。"
      : `音频已私有保存；ASR状态${mediaJob.value.status}。`;
    await refreshMediaCapabilities();
  } catch (reason) {
    mediaMessage.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    mediaBusy.value = false;
    input.value = "";
  }
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [catalog, adaptiveResult, timelineResult, subjective, caseResult, models, media] = await Promise.all([
      api.knowledgeCatalog(),
      api.adaptiveRecommendations(),
      api.adaptiveEvidenceTimeline(),
      api.subjectiveCatalog("review"),
      api.listCases(),
      api.modelCatalog(),
      api.mediaCapabilities().catch(() => null),
    ]);
    cards.value = catalog.knowledge_cards;
    adaptive.value = adaptiveResult;
    timeline.value = timelineResult.events;
    subjectiveTasks.value = subjective.tasks;
    cases.value = caseResult.cases;
    modelCatalog.value = models;
    mediaCatalog.value = media;
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
  browserSpeechSupported.value = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
  void load();
});
onUnmounted(() => {
  window.removeEventListener("keydown", handleKeydown);
  if (browserSpeechSupported.value) window.speechSynthesis.cancel();
  if (serverAudioUrl.value) URL.revokeObjectURL(serverAudioUrl.value);
});
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
          <button :class="{ active: tab === 'graphs' }" @click="tab = 'graphs'">知识 / 论证图</button>
          <button :class="{ active: tab === 'models' }" @click="tab = 'models'">模型路由</button>
          <button :class="{ active: tab === 'media' }" @click="tab = 'media'">多模态 / 数字人</button>
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
          <section class="shadow-boundaries"><p v-for="item in ORCDF_SHADOW.boundaries" :key="item"><span>!</span>{{ item }}</p><footer>实验版本和来源已在技术报告中记录</footer></section>
        </template>

        <template v-else-if="tab === 'path'">
          <section class="path-hero"><div><p class="kicker mono">POLICY · {{ adaptive?.policy_version ?? 'evidence-aware-v1' }}</p><h3>从证据薄弱点到下一条LearningEvent</h3><p>算法排序任务，AI只解释和执行；每次完成后重新计算，不预写“最优路径”。</p></div><button @click="emit('openJourney')">进入当前推荐任务 →</button></section>
          <div class="path-tutor"><AITutor context="path" :speech-text="pathTutorSpeech" compact /></div>
          <section class="path-map">
            <article v-for="(node, index) in pathNodes" :key="node.no" :class="[`path-node--${node.status}`]">
              <span class="path-no mono">{{ node.no }}</span><div class="path-card"><p class="kicker mono">{{ node.type }}</p><h3>{{ node.title }}</h3><span>{{ node.detail }}</span><footer>{{ node.reason }}</footer></div><div v-if="index < pathNodes.length - 1" class="path-connector"><i></i><span>证据更新</span></div>
            </article>
          </section>
          <section class="path-legend"><span><i class="current"></i>当前薄弱点</span><span><i class="ready"></i>可执行任务</span><span><i class="future"></i>完成后重排</span><p>选择题、教师批准主观题和案件Rubric可更新长期画像；困惑只改变优先级，不直接降低掌握。</p></section>
        </template>

        <template v-else-if="tab === 'graphs'">
          <section class="graph-hero"><div><p class="kicker mono">GOVERNED DAG · ARGUMENT SCAFFOLD</p><h3>课程先修图与法律论证模板</h3><p>知识图直接来自10张审核KnowledgeCard；论证图是交互脚手架，不是学生既有证据。</p></div><div class="graph-counts"><span><b>{{ knowledgeGraph.nodes.length }}</b>知识节点</span><span><b>{{ knowledgeGraph.edges.length }}</b>先修关系</span><span><b>0</b>伪造结论</span></div></section>
          <div class="graph-grid">
            <section class="knowledge-graph-panel">
              <header><div><p class="kicker mono">PREREQUISITE DAG · SOURCE OF TRUTH</p><h3>刑法课程轻量知识图</h3></div><span>KnowledgeCard.version bound</span></header>
              <svg viewBox="0 0 1000 430" role="img" aria-label="刑法知识点先修关系图">
                <defs><marker id="knowledge-arrow" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" /></marker></defs>
                <path v-for="edge in knowledgeGraph.edges" :key="edge.id" :d="`M ${edge.from.x} ${edge.from.y + 28} C ${edge.from.x} ${edge.from.y + 74}, ${edge.to.x} ${edge.to.y - 74}, ${edge.to.x} ${edge.to.y - 28}`" class="knowledge-edge" marker-end="url(#knowledge-arrow)" />
                <g v-for="node in knowledgeGraph.nodes" :key="node.card.knowledge_id" :transform="`translate(${node.x},${node.y})`" :class="['knowledge-node', { target: node.card.knowledge_id === targetKnowledge?.knowledge_id }]">
                  <rect x="-86" y="-28" width="172" height="56" rx="2" />
                  <text y="-3" text-anchor="middle">{{ node.card.canonical_name }}</text>
                  <text y="15" text-anchor="middle" class="node-law">{{ node.card.law_article_refs.slice(0, 2).join(' · ') || node.card.chapter }}</text>
                </g>
              </svg>
              <footer><span>绿色边框：当前诊断/推荐目标</span><span>箭头：prerequisite → target</span><span>无LLM补边</span></footer>
            </section>

            <section class="argument-graph-panel">
              <header><div><p class="kicker mono">FACT → EVIDENCE → RULE → CLAIM</p><h3>案件论证脚手架</h3></div><span>template_only</span></header>
              <div class="argument-chain">
                <article v-for="(node, index) in argumentTemplate" :key="node.code" :class="`argument--${node.tone}`"><span class="mono">{{ node.code }}</span><div><h4>{{ node.title }}</h4><p>{{ node.detail }}</p></div><i v-if="index < argumentTemplate.length - 1">→</i></article>
              </div>
              <footer><strong>边界：</strong>只有学生提交、引用核验、Rubric或教师决定形成的事件才可进入画像；这张图当前只组织交互，不生成LearningEvent。</footer>
            </section>
          </div>
        </template>

        <template v-else-if="tab === 'models'">
          <section class="model-hero"><div><p class="kicker mono">MODEL ADAPTER · ROUTE WITHOUT UI CHANGE</p><h3>基础模型 / Prompt / RAG / RAG+微调</h3><p>当前运行基线与预留微调端点分开显示；未连接时不生成模拟指标。</p></div><div class="model-status"><span :class="{ connected: modelCatalog?.small_model_enabled }"></span><strong>{{ modelCatalog?.small_model_enabled ? '微调端点已连接' : '微调端点已预留 · 当前未连接' }}</strong></div></section>
          <section class="route-grid"><article v-for="row in relevantRoutes" :key="row.task"><header><span>{{ row.task.slice(0, 2).toUpperCase() }}</span><div><p class="kicker mono">{{ row.task }}</p><h3>{{ row.route?.model_name || '未配置' }}</h3></div></header><dl><div><dt>当前provider</dt><dd>{{ row.route?.provider ?? 'none' }}</dd></div><div><dt>端点主机</dt><dd>{{ row.route?.api_base ?? 'not_configured' }}</dd></div><div><dt>当前基线端点</dt><dd :class="row.route?.configured ? 'ok' : 'off'">{{ row.route?.configured ? 'connected' : 'not_connected' }}</dd></div><div><dt>RAG+微调</dt><dd :class="row.smallConnected ? 'ok' : 'off'">{{ row.smallConnected ? 'connected' : 'not_connected' }}</dd></div></dl><footer>Key不返回前端 · URL私有路径已脱敏</footer></article></section>
          <section class="comparison-lane"><article><span>01</span><h3>基础模型</h3><p>只做离线基线，不直接给正式结论</p></article><i>→</i><article><span>02</span><h3>Prompt / Few-shot</h3><p>固定回答结构与拒答方式</p></article><i>→</i><article><span>03</span><h3>可信RAG</h3><p>权威法条、版本和引用检查</p></article><i>→</i><article class="pending"><span>04</span><h3>RAG + 微调</h3><p>{{ modelCatalog?.small_model_enabled ? '独立评测通过后逐步接入' : '尚未连接 · 当前继续使用稳定基线' }}</p></article></section>
          <section class="model-boundary"><strong>接入条件</strong><p>微调模型需要比较引用质量、法学专家评分、拒答、延迟和成本；未达到预期时继续使用当前稳定基线。</p><span class="mono">故障时自动回退 · 不影响主要学习流程</span></section>
        </template>

        <template v-else>
          <section class="media-hero">
            <div><p class="kicker mono">P1 LIVE VOICE CONVERSATION · P2 AVATAR POSTPONED</p><h3>实时语音多模态与数字人边界</h3><p>主交互是浏览器麦克风持续分片→讯飞实时partial/final→Evidence回复→讯飞TTS自动播放；文件上传只作兼容工具。</p></div>
            <div class="media-truth"><span>实时麦克风 + 多轮语音</span><strong>LearningEvent 0</strong><small>ASR固定needs_review · 数字人后置</small></div>
          </section>

          <RealtimeVoicePanel :asr-status="mediaCapabilityStatus('speech_to_text')" :tts-status="mediaCapabilityStatus('text_to_speech')" @verified="refreshMediaCapabilities" />

          <section v-if="mediaCatalog" class="media-capability-grid">
            <article v-for="row in mediaCatalog.capabilities" :key="row.capability_id" :class="{ ready: row.connection_status === 'available' }">
              <header><span>{{ row.priority }}</span><div><p class="kicker mono">{{ capabilityLabel(row.capability_id) }}</p><h3>{{ capabilityLabel(row.capability_id) }}</h3></div></header>
              <dl>
                <div><dt>功能</dt><dd>{{ row.implementation_status === 'implemented' ? '已实现' : '已预留' }}</dd></div>
                <div><dt>状态</dt><dd :class="row.connection_status === 'available' ? 'ok' : 'off'">{{ statusLabelFriendly(row.connection_status) }}</dd></div>
              </dl>
              <footer v-if="row.provider_options?.length"><span v-for="provider in row.provider_options" :key="provider.provider_id">{{ providerLabel(provider.provider_id) }}</span></footer>
              <footer v-else><span>{{ row.client_fallback ? '浏览器本地降级可用' : '本地能力' }}</span></footer>
            </article>
          </section>
          <section v-else class="media-missing"><strong>能力目录未加载</strong><p>核心诊断仍可运行；媒体能力不会被假设为已连接。</p></section>

          <section class="compatibility-label"><p class="kicker mono">COMPATIBILITY TOOLS · NOT THE LIVE VOICE MAIN FLOW</p><h3>文件式语音兼容与数字人预留</h3><span>以下是兼容工具，不是实时语音主流程</span></section>
          <div class="media-lab-grid">
            <section class="media-lab">
              <header><div><p class="kicker mono">IFLYTEK ONLINE TTS · CLIENT FALLBACK</p><h3>语音快问快答朗读</h3></div><span :class="mediaCapabilityStatus('text_to_speech') === 'available' ? 'ok' : 'off'">{{ statusLabelFriendly(mediaCapabilityStatus('text_to_speech')) }}</span></header>
              <textarea v-model="speechText" maxlength="2000" aria-label="待朗读文本"></textarea>
              <div class="media-actions"><button :disabled="mediaBusy" @click="checkServerSpeech">生成讯飞WAV</button><button :disabled="mediaBusy || !lastTtsAssetId" @click="transcribeLastTts">将WAV送入ASR</button><button :disabled="!browserSpeechSupported || browserSpeaking" @click="readWithBrowserSpeech">{{ browserSpeaking ? '正在朗读…' : '浏览器降级' }}</button></div>
              <audio v-if="serverAudioUrl" class="media-audio" :src="serverAudioUrl" controls aria-label="讯飞AI合成音频"></audio>
              <p>讯飞成功后返回当前用户私有可下载WAV；浏览器SpeechSynthesis只作降级，不冒充云调用。</p>
            </section>

            <section class="media-lab">
              <header><div><p class="kicker mono">FILE COMPATIBILITY IAT</p><h3>录音文件转写兼容入口</h3></div><span :class="mediaCapabilityStatus('speech_to_text') === 'available' ? 'ok' : 'off'">{{ statusLabelFriendly(mediaCapabilityStatus('speech_to_text')) }}</span></header>
              <label class="media-upload"><input type="file" accept="audio/wav,audio/mpeg,audio/mp3,audio/mp4,audio/webm,audio/ogg" :disabled="mediaBusy" @change="handleAudioUpload"><strong>选择≤15MB短音频</strong><span>私有保存 · 登录用户隔离</span></label>
              <dl v-if="mediaAsset" class="media-proof"><div><dt>状态</dt><dd>已安全保存</dd></div><div><dt>范围</dt><dd>仅当前用户可用</dd></div></dl>
              <p>仅用于历史录音兼容，不是实时语音主交互；转写需要复核且不形成LearningEvent。</p>
            </section>

            <section class="media-lab avatar-lab">
              <header><div><p class="kicker mono">P2 · 计划接入</p><h3>数字人异步渲染</h3></div><span class="off">尚未连接</span></header>
              <div class="avatar-flow"><span>审核文本</span><i>→</i><span>TTS / voice</span><i>→</i><span>Avatar render</span><i>→</i><span>AI显著标识</span></div>
              <button :disabled="mediaBusy" @click="checkAvatarInterface">调用预留接口验证状态</button>
              <p>推荐讯飞作为赛事主Provider，Azure作替代；自定义肖像必须确认授权。数字人只负责呈现，不参与评分或画像。</p>
            </section>
          </div>

          <section v-if="mediaMessage || mediaJob" class="media-result">
            <div><p class="kicker mono">处理结果</p><h3>{{ mediaMessage || '任务状态已更新' }}</h3></div>
            <dl v-if="mediaJob"><div><dt>服务</dt><dd>{{ providerLabel(mediaJob.provider_resolved) }}</dd></div><div><dt>状态</dt><dd :class="['succeeded','needs_review'].includes(mediaJob.status) ? 'ok' : 'off'">{{ statusLabelFriendly(mediaJob.status) }}</dd></div><div><dt>转写</dt><dd>{{ mediaTranscript || '—' }}</dd></div></dl>
          </section>
        </template>
      </main>
    </section>
  </div>
</template>

<style scoped>
.path-tutor{margin-top:14px}
.cog-layer{position:fixed;inset:0;z-index:1360;padding:18px;background:radial-gradient(circle at 75% 8%,rgba(66,111,128,.15),transparent 32%),radial-gradient(circle at 8% 82%,rgba(176,138,62,.1),transparent 30%),rgba(4,4,3,.93);backdrop-filter:blur(13px)}
.cog-board{height:100%;min-height:0;display:flex;flex-direction:column;overflow:hidden;color:var(--parchment);border:1px solid rgba(100,139,153,.46);background:linear-gradient(135deg,#151815,#090b0a 72%);box-shadow:0 40px 110px #000d}
.cog-head{min-height:82px;display:grid;grid-template-columns:minmax(300px,1fr) auto minmax(250px,1fr) 38px;align-items:center;gap:18px;padding:12px 18px 12px 23px;border-bottom:1px solid rgba(100,139,153,.32);background:linear-gradient(180deg,rgba(25,30,28,.98),rgba(12,15,14,.98))}.cog-brand{display:flex;align-items:center;gap:13px}.cog-seal{width:47px;height:47px;display:grid;place-items:center;color:#dce9ec;border:1px solid #789dac;box-shadow:inset 0 0 0 3px #142025;font-family:var(--font-display);font-size:1.08rem;font-weight:800;transform:rotate(-2deg)}.kicker{margin:0 0 3px;color:#87aebb;font-size:.61rem;letter-spacing:.16em}.cog-brand h2{font-size:1.28rem}.cog-tabs{display:flex;border:1px solid var(--line-strong)}.cog-tabs button{padding:9px 13px;color:var(--parchment-dim);border:0;border-right:1px solid var(--line);background:transparent;font-family:var(--font-display);font-size:.75rem;cursor:pointer}.cog-tabs button:last-child{border:0}.cog-tabs button.active{color:#e5eff0;background:rgba(100,139,153,.16);box-shadow:inset 0 -2px #87aebb}.cog-badges{display:flex;justify-content:flex-end;gap:6px}.cog-badges span{padding:4px 6px;color:var(--parchment-faint);border:1px solid var(--line);font-size:.6rem}.cog-close{width:36px;height:36px;color:var(--parchment-muted);border:1px solid var(--line-strong);background:transparent;font-size:1.35rem;cursor:pointer}
.cog-state{flex:1;display:grid;place-content:center;justify-items:center;gap:14px;color:var(--parchment-muted)}.cog-state--error>span{width:43px;height:43px;display:grid;place-items:center;color:#e1a48f;border:1px solid var(--accent)}.cog-state button{padding:7px 12px;color:var(--parchment);border:1px solid var(--line-strong);background:transparent}.cog-content{flex:1;min-height:0;overflow-y:auto;padding:22px clamp(20px,2.7vw,44px) 48px;background:linear-gradient(90deg,rgba(255,255,255,.013) 1px,transparent 1px) 0 0/56px 56px}
.diagnosis-hero,.path-hero,.model-hero{display:flex;align-items:flex-start;justify-content:space-between;gap:22px;padding:0 0 17px;border-bottom:1px solid rgba(100,139,153,.34)}.diagnosis-hero h3,.path-hero h3,.model-hero h3,.shadow-banner h3{font-size:1.4rem}.diagnosis-hero>div>p:last-child,.path-hero>div>p:last-child,.model-hero>div>p:last-child,.shadow-banner div>p:last-child{margin:5px 0 0;color:var(--parchment-dim);font-size:.73rem}.hero-metrics{display:grid!important;grid-template-columns:repeat(4,112px);border:1px solid var(--line)}.hero-metrics div{padding:10px;text-align:center;border-right:1px solid var(--line)}.hero-metrics div:last-child{border:0}.hero-metrics b{display:block;font-family:var(--font-mono);font-size:1.15rem}.hero-metrics span{color:var(--parchment-faint);font-size:.63rem}.diagnosis-grid{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:13px;margin-top:15px}.panel{min-width:0;padding:15px;border:1px solid var(--line);background:rgba(255,255,255,.016)}.panel>header{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;margin-bottom:12px}.panel>header h3{font-size:1rem}.panel>header>span{color:var(--parchment-faint);font-family:var(--font-mono);font-size:.62rem}.knowledge-panel{grid-row:span 2}.knowledge-table{display:grid;gap:4px}.knowledge-table article{display:grid;grid-template-columns:9px minmax(0,1fr) 42px 155px;align-items:center;gap:9px;padding:8px;border-bottom:1px solid var(--line)}.state-dot{width:7px;height:7px;background:#67665f}.state-dot--mastered{background:#85a878}.state-dot--partial{background:#b08a3e}.state-dot--missing{background:#c45b38}.state-dot--provisional{background:#789dac}.state-dot--insufficient{background:#585a56}.knowledge-table article>div:nth-child(2){min-width:0;display:grid}.knowledge-table strong{overflow:hidden;font-family:var(--font-display);font-size:.75rem;white-space:nowrap;text-overflow:ellipsis}.knowledge-table small{color:var(--parchment-faint);font-size:.59rem}.evidence-count{display:grid;text-align:center}.evidence-count b{font-size:.78rem}.evidence-count span{color:var(--parchment-faint);font-size:.5rem}.state-pill{padding:3px 5px;text-align:center;border:1px solid var(--line);font-size:.6rem}.state-pill--mastered{color:#b9d0ad;border-color:rgba(122,153,98,.42)}.state-pill--partial{color:#e0c187;border-color:rgba(176,138,62,.42)}.state-pill--missing{color:#e3a08b;border-color:rgba(196,71,27,.45)}.state-pill--provisional{color:#b9d2db;border-color:rgba(100,139,153,.46)}.state-pill--insufficient{color:var(--parchment-faint)}.timeline{list-style:none;margin:0;padding:0;display:grid}.timeline li{display:grid;grid-template-columns:26px 16px minmax(0,1fr) 66px;gap:7px;min-height:61px}.timeline-no{padding-top:2px;color:#789dac;font-size:.58rem}.timeline-line{position:relative}.timeline-line::before{content:"";position:absolute;left:7px;top:10px;bottom:-3px;width:1px;background:var(--line-strong)}.timeline li:last-child .timeline-line::before{bottom:40px}.timeline-line i{position:absolute;top:5px;left:3px;width:9px;height:9px;border:2px solid #789dac;background:#101412;transform:rotate(45deg)}.timeline strong{font-size:.75rem}.timeline p{margin:3px 0;color:var(--parchment-muted);font-size:.65rem}.timeline small{color:var(--parchment-faint);font-size:.54rem}.eligibility{align-self:start;padding:3px 4px;color:#d6a38d;border:1px solid rgba(196,71,27,.35);font-size:.55rem;text-align:center}.eligibility.yes{color:#b6cba9;border-color:rgba(122,153,98,.38)}.empty-evidence{min-height:220px;display:grid;place-content:center;justify-items:center;text-align:center;color:var(--parchment-faint)}.empty-evidence>span{font-family:var(--font-mono);font-size:2rem}.empty-evidence h4{margin:4px}.empty-evidence p{max-width:300px;font-size:.66rem}.signal-panel{display:grid;grid-template-columns:1fr 1fr;gap:13px}.signal-panel h3{font-size:.9rem}.signal-panel ul{list-style:none;margin:8px 0 0;padding:0}.signal-panel li{display:flex;justify-content:space-between;gap:8px;padding:5px 0;color:var(--parchment-muted);border-bottom:1px solid var(--line);font-size:.66rem}.signal-panel li b{color:#e0a076}.signal-panel footer{grid-column:1/-1;padding:8px 9px;border:1px dashed var(--line-strong)}.signal-panel footer strong{color:var(--accent);font-family:var(--font-display);font-size:.7rem}.signal-panel footer p{margin:3px 0 0;color:var(--parchment-faint);font-size:.61rem}
.shadow-banner{display:grid;grid-template-columns:70px minmax(0,1fr) auto;align-items:center;gap:17px;padding:13px 16px;border:1px solid rgba(196,71,27,.48);background:linear-gradient(90deg,rgba(196,71,27,.09),transparent)}.shadow-banner>span{width:58px;height:58px;display:grid;place-items:center;color:#e5aa93;border:1px solid currentColor;font-family:var(--font-mono);font-size:.67rem;transform:rotate(-2deg)}.shadow-banner>strong{padding:6px 8px;color:#e1aa92;border:1px solid rgba(196,71,27,.42);font-size:.7rem}.orcdf-versions{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0}.orcdf-versions article{padding:14px;border:1px solid var(--line);background:rgba(255,255,255,.016)}.orcdf-versions article.version--llm{border-color:rgba(176,138,62,.42)}.orcdf-versions article.version--teacher{border-color:rgba(100,139,153,.5)}.orcdf-versions header{display:flex;align-items:center;gap:11px}.orcdf-versions header>span{width:38px;height:38px;display:grid;place-items:center;border:1px solid currentColor;font-family:var(--font-mono)}.orcdf-versions h3{font-size:.92rem}.orcdf-versions header p{margin:3px 0 0;color:var(--parchment-faint);font-size:.62rem}.orcdf-versions dl{margin:12px 0}.orcdf-versions dl div{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px solid var(--line);font-size:.65rem}.orcdf-versions dt{color:var(--parchment-faint)}.orcdf-versions dd{margin:0;text-align:right}.auc-track{height:5px;background:var(--line)}.auc-track i{display:block;height:100%;background:linear-gradient(90deg,#7f5945,#b08a3e,#789dac)}.orcdf-detail-grid{display:grid;grid-template-columns:.8fr 1.2fr;gap:12px}.bootstrap-rows{display:grid;gap:6px}.bootstrap-rows article{display:grid;grid-template-columns:70px 64px 1fr 62px;align-items:center;gap:7px;padding:7px;border-bottom:1px solid var(--line)}.bootstrap-rows strong{font-size:.7rem}.bootstrap-rows b{color:#acd09c;font-family:var(--font-mono)}.bootstrap-rows b.negative{color:#e3a08b}.bootstrap-rows span{color:var(--parchment-dim);font-size:.6rem}.bootstrap-rows em{color:var(--parchment-faint);font-size:.59rem;font-style:normal}.boundary-note{margin:10px 0 0;color:var(--parchment-faint);font-size:.61rem;line-height:1.5}.heatmap-scroll{overflow-x:auto}.heatmap{min-width:650px;display:grid;gap:3px;align-items:center}.heat-label{height:47px;display:flex;align-items:flex-end;color:var(--parchment-faint);font-size:.53rem;line-height:1.2;writing-mode:vertical-rl}.heatmap>strong{font-size:.59rem;font-weight:500}.heat-cell{padding:8px 3px;color:#f0e8da;text-align:center;font-size:.56rem}.generic-init{display:grid;grid-template-columns:1fr 120px 28px 120px minmax(220px,.8fr);align-items:center;gap:12px;margin-top:12px;padding:13px;border:1px solid rgba(122,153,98,.38);background:rgba(122,153,98,.035)}.generic-init h3{font-size:.92rem}.init-score{display:grid;text-align:center}.init-score span{color:var(--parchment-faint);font-size:.57rem}.init-score b{font-family:var(--font-mono);font-size:1.2rem}.init-arrow{color:#8eb184;text-align:center}.generic-init>p{margin:0;color:var(--parchment-dim);font-size:.63rem;line-height:1.5}.shadow-boundaries{display:grid;grid-template-columns:repeat(2,1fr);gap:5px;margin-top:10px}.shadow-boundaries p{margin:0;padding:6px 8px;color:var(--parchment-faint);border:1px dashed var(--line);font-size:.61rem}.shadow-boundaries p span{margin-right:6px;color:var(--accent)}.shadow-boundaries footer{grid-column:1/-1;color:var(--parchment-faint);font-size:.54rem;text-align:right}
.path-hero button{padding:9px 14px;color:#e5efdf;border:1px solid rgba(122,153,98,.48);background:rgba(122,153,98,.08);font-family:var(--font-display);cursor:pointer}.path-map{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:20px;margin-top:30px}.path-map article{position:relative;min-width:0}.path-no{position:absolute;z-index:2;top:-13px;left:12px;padding:4px 6px;color:#89afba;border:1px solid rgba(100,139,153,.48);background:#111513;font-size:.6rem}.path-card{height:230px;display:flex;flex-direction:column;padding:22px 12px 12px;border:1px solid var(--line);background:linear-gradient(155deg,rgba(255,255,255,.026),transparent)}.path-card h3{font-size:.82rem;line-height:1.45}.path-card>span{margin-top:7px;color:var(--parchment-faint);font-size:.61rem;line-height:1.45}.path-card footer{margin-top:auto;padding-top:8px;color:var(--parchment-dim);border-top:1px dashed var(--line);font-size:.59rem;line-height:1.45}.path-node--current .path-card{border-color:rgba(196,71,27,.55);box-shadow:inset 0 3px var(--accent)}.path-node--ready .path-card{border-color:rgba(122,153,98,.44);box-shadow:inset 0 3px var(--accent-success)}.path-node--future .path-card{border-style:dashed}.path-node--locked .path-card{opacity:.48}.path-node--complete .path-card{border-color:rgba(100,139,153,.38)}.path-connector{position:absolute;z-index:3;top:104px;left:calc(100% + 2px);width:36px;display:grid;justify-items:center}.path-connector i{width:36px;height:1px;background:linear-gradient(90deg,#789dac,transparent)}.path-connector i::after{content:"";float:right;width:6px;height:6px;margin-top:-3px;border-top:1px solid #789dac;border-right:1px solid #789dac;transform:rotate(45deg)}.path-connector span{margin-top:6px;color:var(--parchment-faint);font-size:.48rem;writing-mode:vertical-rl}.path-legend{display:flex;align-items:center;gap:16px;margin-top:18px;padding:10px;border:1px solid var(--line)}.path-legend>span{display:flex;align-items:center;gap:5px;color:var(--parchment-dim);font-size:.62rem}.path-legend i{width:8px;height:8px;background:#666}.path-legend i.current{background:var(--accent)}.path-legend i.ready{background:var(--accent-success)}.path-legend i.future{background:#789dac}.path-legend p{margin:0 0 0 auto;color:var(--parchment-faint);font-size:.61rem}
.graph-hero{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;padding-bottom:16px;border-bottom:1px solid rgba(100,139,153,.34)}.graph-hero h3{font-size:1.4rem}.graph-hero>div>p:last-child{margin:5px 0 0;color:var(--parchment-dim);font-size:.73rem}.graph-counts{display:flex;border:1px solid var(--line)}.graph-counts span{min-width:100px;padding:9px 12px;color:var(--parchment-faint);border-right:1px solid var(--line);font-size:.6rem;text-align:center}.graph-counts span:last-child{border:0}.graph-counts b{display:block;color:var(--parchment);font-family:var(--font-mono);font-size:1.05rem}.graph-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(360px,.65fr);gap:12px;margin-top:14px}.knowledge-graph-panel,.argument-graph-panel{min-width:0;padding:14px;border:1px solid var(--line);background:rgba(255,255,255,.014)}.knowledge-graph-panel>header,.argument-graph-panel>header{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.knowledge-graph-panel h3,.argument-graph-panel h3{font-size:.94rem}.knowledge-graph-panel>header>span,.argument-graph-panel>header>span{color:var(--parchment-faint);font-family:var(--font-mono);font-size:.55rem}.knowledge-graph-panel svg{width:100%;height:min(56vh,500px);min-height:390px;margin-top:8px;border:1px dashed var(--line);background:radial-gradient(circle,rgba(100,139,153,.14) 1px,transparent 1px) 0 0/18px 18px}.knowledge-edge{fill:none;stroke:rgba(120,157,172,.55);stroke-width:1.5}.knowledge-graph-panel marker path{fill:#789dac}.knowledge-node rect{fill:#121714;stroke:rgba(100,139,153,.62);stroke-width:1.2}.knowledge-node.target rect{fill:rgba(122,153,98,.1);stroke:#8cae7f;stroke-width:2}.knowledge-node text{fill:#ece2d1;font-family:var(--font-display);font-size:12px}.knowledge-node .node-law{fill:#82949a;font-family:var(--font-mono);font-size:8px}.knowledge-graph-panel>footer{display:flex;gap:12px;margin-top:8px;color:var(--parchment-faint);font-size:.56rem}.argument-chain{display:grid;gap:7px;margin-top:12px}.argument-chain article{position:relative;display:grid;grid-template-columns:44px 1fr;gap:9px;min-height:61px;padding:9px;border:1px solid var(--line)}.argument-chain article>span{align-self:start;padding:3px 4px;color:#a9c3cc;border:1px solid rgba(100,139,153,.45);font-size:.52rem;text-align:center}.argument-chain h4{font-size:.72rem}.argument-chain p{margin:3px 0 0;color:var(--parchment-faint);font-size:.57rem;line-height:1.45}.argument-chain i{position:absolute;right:13px;bottom:-13px;z-index:2;color:#789dac;font-style:normal;transform:rotate(90deg)}.argument--evidence,.argument--gate{border-color:rgba(122,153,98,.42)!important}.argument--challenge{border-color:rgba(196,71,27,.42)!important}.argument-graph-panel>footer{margin-top:10px;padding:8px;color:var(--parchment-faint);border:1px dashed var(--line-strong);font-size:.57rem;line-height:1.5}.argument-graph-panel>footer strong{color:#df9d84}
.model-status{display:flex;align-items:center;gap:8px;padding:7px 9px;border:1px solid var(--line)}.model-status span{width:8px;height:8px;background:var(--accent)}.model-status span.connected{background:var(--accent-success)}.model-status strong{font-size:.7rem}.route-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:16px}.route-grid article{padding:14px;border:1px solid var(--line);background:rgba(255,255,255,.016)}.route-grid header{display:flex;align-items:center;gap:10px}.route-grid header>span{width:34px;height:34px;display:grid;place-items:center;color:#b9d2db;border:1px solid rgba(100,139,153,.42);font-family:var(--font-mono)}.route-grid h3{overflow:hidden;font-size:.86rem;white-space:nowrap;text-overflow:ellipsis}.route-grid dl{margin:13px 0}.route-grid dl div{display:grid;grid-template-columns:1fr minmax(0,1.3fr);gap:7px;padding:6px 0;border-bottom:1px solid var(--line);font-size:.61rem}.route-grid dt{color:var(--parchment-faint)}.route-grid dd{overflow:hidden;margin:0;text-align:right;white-space:nowrap;text-overflow:ellipsis}.route-grid dd.ok{color:#b7cba9}.route-grid dd.off{color:#df9e86}.route-grid footer{color:var(--parchment-faint);font-size:.57rem}.comparison-lane{display:grid;grid-template-columns:1fr 28px 1fr 28px 1fr 28px 1fr;align-items:center;gap:7px;margin-top:14px}.comparison-lane article{min-height:115px;padding:13px;border:1px solid rgba(122,153,98,.38);background:rgba(122,153,98,.025)}.comparison-lane article.pending{border-style:dashed;border-color:rgba(196,71,27,.45)}.comparison-lane article>span{color:#789dac;font-family:var(--font-mono);font-size:.61rem}.comparison-lane h3{margin:5px 0;font-size:.85rem}.comparison-lane p{margin:0;color:var(--parchment-faint);font-size:.61rem;line-height:1.45}.comparison-lane>i{color:#789dac;text-align:center;font-style:normal}.model-boundary{display:grid;grid-template-columns:80px 1fr auto;align-items:center;gap:12px;margin-top:13px;padding:10px;border:1px dashed var(--line-strong)}.model-boundary strong{color:var(--accent);font-family:var(--font-display)}.model-boundary p{margin:0;color:var(--parchment-dim);font-size:.63rem}.model-boundary span{color:var(--parchment-faint);font-size:.55rem}
.media-hero{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;padding-bottom:16px;border-bottom:1px solid rgba(100,139,153,.34)}.media-hero h3{font-size:1.4rem}.media-hero>div>p:last-child{margin:5px 0 0;color:var(--parchment-dim);font-size:.73rem}.media-truth{display:grid;justify-items:end;gap:4px;padding:9px 11px;border:1px solid rgba(196,71,27,.45);background:rgba(196,71,27,.05)}.media-truth span{color:#e0a28b;font-family:var(--font-display);font-size:.72rem}.media-truth strong{font-family:var(--font-mono);font-size:.82rem}.media-truth small{color:var(--parchment-faint);font-size:.56rem}.media-capability-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-top:15px}.media-capability-grid article{min-width:0;padding:12px;border:1px dashed rgba(196,71,27,.42);background:rgba(255,255,255,.014)}.media-capability-grid article.ready{border-style:solid;border-color:rgba(122,153,98,.45)}.media-capability-grid header{display:flex;align-items:center;gap:8px}.media-capability-grid header>span{width:31px;height:31px;display:grid;place-items:center;color:#b7ced6;border:1px solid currentColor;font-family:var(--font-mono);font-size:.61rem}.media-capability-grid h3{font-size:.78rem}.media-capability-grid dl{margin:10px 0}.media-capability-grid dl div{display:grid;grid-template-columns:52px minmax(0,1fr);gap:4px;padding:4px 0;border-bottom:1px solid var(--line);font-size:.57rem}.media-capability-grid dt{color:var(--parchment-faint)}.media-capability-grid dd{overflow:hidden;margin:0;text-align:right;white-space:nowrap;text-overflow:ellipsis}.media-capability-grid dd.ok,.media-lab .ok,.media-result dd.ok{color:#b8d0ac}.media-capability-grid dd.off,.media-lab .off,.media-result dd.off{color:#e0a087}.media-capability-grid footer{display:grid;gap:3px;color:var(--parchment-faint);font-size:.52rem}.media-missing{margin-top:15px;padding:13px;border:1px dashed var(--line-strong)}.media-missing p{margin:4px 0 0;color:var(--parchment-faint);font-size:.63rem}.media-lab-grid{display:grid;grid-template-columns:1fr 1fr 1.1fr;gap:11px;margin-top:14px}.media-lab{min-width:0;padding:14px;border:1px solid var(--line);background:rgba(255,255,255,.016)}.media-lab>header{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.media-lab h3{font-size:.9rem}.media-lab>header>span{padding:3px 5px;border:1px solid currentColor;font-family:var(--font-mono);font-size:.56rem}.media-lab textarea{width:100%;min-height:96px;margin:11px 0 8px;padding:9px;color:var(--parchment);border:1px solid var(--line-strong);background:#0c0f0e;resize:vertical;font:inherit;font-size:.66rem;line-height:1.55}.media-actions{display:flex;gap:7px}.media-lab button,.media-upload{padding:8px 10px;color:var(--parchment);border:1px solid rgba(100,139,153,.5);background:rgba(100,139,153,.07);font-family:var(--font-display);font-size:.66rem;cursor:pointer}.media-lab button:disabled{opacity:.42;cursor:not-allowed}.media-lab>p{margin:9px 0 0;color:var(--parchment-faint);font-size:.58rem;line-height:1.5}.media-upload{display:grid;gap:4px;margin-top:12px;text-align:center}.media-upload input{position:absolute;width:1px;height:1px;opacity:0}.media-upload strong{font-size:.7rem}.media-upload span{color:var(--parchment-faint);font-size:.56rem}.media-proof{margin:9px 0 0}.media-proof div{display:grid;grid-template-columns:48px 1fr;gap:8px;padding:4px 0;border-bottom:1px solid var(--line);font-size:.56rem}.media-proof dt{color:var(--parchment-faint)}.media-proof dd{overflow:hidden;margin:0;text-align:right;white-space:nowrap;text-overflow:ellipsis}.avatar-flow{display:flex;align-items:center;justify-content:center;gap:6px;min-height:92px;margin:10px 0;padding:8px;border:1px dashed var(--line-strong)}.avatar-flow span{padding:5px 6px;color:var(--parchment-dim);border:1px solid var(--line);font-size:.56rem}.avatar-flow i{color:#789dac;font-style:normal}.avatar-lab>button{width:100%}.media-result{display:grid;grid-template-columns:minmax(0,1fr) minmax(420px,.9fr);align-items:center;gap:16px;margin-top:12px;padding:11px 13px;border:1px solid rgba(176,138,62,.43);background:rgba(176,138,62,.035)}.media-result h3{font-size:.74rem}.media-result dl{display:grid;grid-template-columns:repeat(4,1fr);margin:0}.media-result dl div{min-width:0;padding:0 8px;border-left:1px solid var(--line)}.media-result dt{color:var(--parchment-faint);font-size:.52rem}.media-result dd{overflow:hidden;margin:2px 0 0;font-family:var(--font-mono);font-size:.58rem;white-space:nowrap;text-overflow:ellipsis}
.compatibility-label{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:10px;margin-top:18px;padding:10px 12px;border-left:3px solid rgba(196,71,27,.55);background:rgba(196,71,27,.035)}.compatibility-label .kicker{grid-column:1/-1}.compatibility-label h3{font-size:.84rem}.compatibility-label span{color:#b98672;font-size:.59rem}
.media-audio{width:100%;height:34px;margin-top:9px;filter:sepia(.3) saturate(.55) brightness(.82)}
@media(max-width:1180px){.cog-head{grid-template-columns:1fr auto 38px}.cog-badges{display:none}.diagnosis-grid{grid-template-columns:1fr}.knowledge-panel{grid-row:auto}.path-map{grid-template-columns:repeat(4,1fr)}.path-connector{display:none}.route-grid{grid-template-columns:repeat(2,1fr)}.graph-grid{grid-template-columns:1fr}.media-capability-grid{grid-template-columns:repeat(3,1fr)}.media-lab-grid{grid-template-columns:1fr 1fr}.avatar-lab{grid-column:1/-1}}
@media(max-width:820px){.cog-layer{padding:0}.cog-head{grid-template-columns:1fr 38px;padding:10px 12px}.cog-tabs{grid-column:1/-1;grid-row:2;overflow-x:auto}.cog-tabs button{flex:1;white-space:nowrap}.cog-content{padding:16px 13px 40px}.diagnosis-hero,.path-hero,.model-hero,.graph-hero,.media-hero{display:block}.graph-counts{margin-top:12px;overflow-x:auto}.media-truth{justify-items:start;margin-top:12px}.hero-metrics{grid-template-columns:repeat(2,1fr);margin-top:12px}.orcdf-versions,.orcdf-detail-grid,.route-grid,.media-capability-grid,.media-lab-grid{grid-template-columns:1fr}.avatar-lab{grid-column:auto}.generic-init{grid-template-columns:1fr 1fr}.generic-init>div:first-child,.generic-init>p{grid-column:1/-1}.init-arrow{display:none}.path-map{grid-template-columns:repeat(2,1fr)}.comparison-lane{grid-template-columns:1fr}.comparison-lane>i{transform:rotate(90deg)}.model-boundary,.media-result{grid-template-columns:1fr}.media-result dl{grid-template-columns:1fr 1fr}.shadow-boundaries{grid-template-columns:1fr}.shadow-boundaries footer{grid-column:1}.signal-panel{grid-template-columns:1fr}.signal-panel footer{grid-column:1}.knowledge-table article{grid-template-columns:9px minmax(0,1fr) 38px}.state-pill{grid-column:2/-1}.timeline li{grid-template-columns:24px 14px minmax(0,1fr)}.eligibility{grid-column:3}.cog-brand h2{font-size:1.05rem}.avatar-flow{flex-wrap:wrap}.knowledge-graph-panel{overflow-x:auto}.knowledge-graph-panel svg{min-width:760px}.knowledge-graph-panel>footer{min-width:760px}.compatibility-label{grid-template-columns:1fr}.compatibility-label .kicker{grid-column:1}}
</style>
