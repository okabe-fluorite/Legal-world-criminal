<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { api } from "../lib/api";
import type { CitationAuditResponse, KnowledgeSearchResponse, TypicalQuestionCase, TypicalQuestionReport } from "../lib/types";
import AITutor from "./AITutor.vue";
import EvidenceCitations from "./EvidenceCitations.vue";
import { toEvidenceReference, typicalSourceReference } from "../lib/evidence";

const emit = defineEmits<{ close: [] }>();
const loading = ref(true);
const error = ref("");
const report = ref<TypicalQuestionReport | null>(null);
const selectedId = ref("");
const badAudit = ref<CitationAuditResponse | null>(null);
const auditing = ref(false);
const viewMode = ref<"examples" | "explore">("examples");
const searchQuery = ref("请从法律、司法解释、指导案例和教材解释正当防卫的成立条件");
const searchResult = ref<KnowledgeSearchResponse | null>(null);
const searching = ref(false);
const searchError = ref("");
const searchPresets = [
  "《中华人民共和国刑法》第二十条如何规定正当防卫？",
  "人民检察院办理行政执法机关移送涉嫌犯罪案件的规定",
  "指导案例144号张那木拉正当防卫案的裁判规则",
  "请用刑法教材解释正当防卫与紧急避险的区别",
  "查找抢劫罪构成要件的相似练习",
];

const selected = computed<TypicalQuestionCase | null>(() =>
  report.value?.cases.find((row) => row.case_id === selectedId.value)
    ?? report.value?.cases[0]
    ?? null,
);
const requiredSources = computed(() => {
  const row = selected.value;
  return row?.sources.filter((source) => row.required_source_ids.includes(source.source_id)) ?? [];
});
const requiredReferences = computed(() => requiredSources.value.map(typicalSourceReference));
const modelReferences = computed(() => {
  const row = selected.value;
  if (!row) return [];
  return row.model_output.citations
    .map((citation) => row.sources.find((source) => source.source_id === citation.source_id))
    .filter((source) => Boolean(source))
    .map((source) => typicalSourceReference(source!));
});
const gateSummary = computed(() => [
  { label: "结构完整", passed: selected.value?.run_status === "model_completed" },
  { label: "要点覆盖", passed: selected.value?.point_coverage === 1 },
  { label: "来源匹配", passed: selected.value?.citation_audit.passed ?? false },
  { label: "原文一致", passed: selected.value?.citation_audit.passed ?? false },
]);
const rejectedBadCitationCount = computed(() =>
  badAudit.value?.items.filter(
    (row) => row.status !== "valid" || row.quote_status === "quote_mismatch",
  ).length ?? 0,
);
const evidenceWarningSpeech = computed(() => badAudit.value
  ? `本次引用检查发现${rejectedBadCitationCount.value}条明显错误。条号和原文可以自动核对，但是否支持当前法律结论仍需人工判断。`
  : "",
);
const searchReferences = computed(() => (searchResult.value?.evidences ?? []).map(
  (row, index) => toEvidenceReference(row, `search:${index}`),
));
const sourceGroups = computed(() => [
  {
    usage: "normative_rule",
    label: "规范依据",
    explanation: "法律与行政法规用于规则陈述；行政法规不得覆盖法律。",
  },
  {
    usage: "judicial_application",
    label: "司法适用",
    explanation: "司法解释和司法规范性文件用于说明司法适用口径。",
  },
  {
    usage: "case_reference",
    label: "案例参考",
    explanation: "指导性或典型案例展示事实适用与裁判理由，不等同法条。",
  },
  {
    usage: "teaching_explanation",
    label: "教材解释",
    explanation: "教材帮助理解概念、要件和争点，但不能覆盖现行规范。",
  },
  {
    usage: "learning_resource",
    label: "下一步练习",
    explanation: "公开题只用于相似练习与诊断，不参与法律结论证明。",
  },
].map((group) => ({
  ...group,
  references: searchReferences.value.filter((row) => row.allowed_usage.includes(group.usage)).slice(0, 4),
})).filter((group) => group.references.length));

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    report.value = await api.typicalQuestionReport();
    selectedId.value = report.value.cases[0]?.case_id ?? "";
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    loading.value = false;
  }
}

function selectCase(row: TypicalQuestionCase): void {
  selectedId.value = row.case_id;
  badAudit.value = null;
}

async function runBadCitationAudit(): Promise<void> {
  auditing.value = true;
  error.value = "";
  try {
    badAudit.value = await api.auditKnowledgeCitations([
      {
        title: "刑法",
        article_ref: "第九百九十九条",
        quote: "不存在的法条和伪造原文。",
        claim: "该条能够直接支持当前结论。",
      },
      {
        title: "刑法",
        article_ref: "第二百六十四条",
        quote: "以暴力、胁迫方式抢劫财物的，适用本条。",
        claim: "用盗窃罪条文支持抢劫罪结论。",
      },
    ]);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    auditing.value = false;
  }
}

async function runKnowledgeSearch(query = searchQuery.value): Promise<void> {
  const normalized = String(query || "").trim();
  if (!normalized) {
    searchError.value = "请输入要检索的刑法问题。";
    return;
  }
  viewMode.value = "explore";
  searchQuery.value = normalized;
  searching.value = true;
  searchError.value = "";
  try {
    searchResult.value = await api.searchKnowledge({
      query: normalized,
      top_k: 8,
      collections: ["legal_authority", "textbook_explanation", "question_public"],
    });
  } catch (reason) {
    searchError.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    searching.value = false;
  }
}

function versionLabel(value?: string): string {
  const text = String(value || "").trim();
  if (!text) return "版本信息待补充";
  if (/^[a-f0-9]{40,}$/i.test(text)) return "课程版本已记录";
  if (text.startsWith("npc-flk-")) return "国家法律法规数据库资料版本";
  return text.length > 36 ? "资料版本已记录" : text;
}

function auditStatusLabel(value: string): string {
  return ({
    valid: "条号存在",
    invalid_title: "法律名称无效",
    invalid_article: "条号不存在",
  } as Record<string, string>)[value] ?? value;
}

function quoteStatusLabel(value: string): string {
  return ({
    not_requested: "未请求引文",
    exact_fragment: "逐字片段通过",
    quote_mismatch: "引文不匹配",
  } as Record<string, string>)[value] ?? value;
}

function riskLabel(value: string): string {
  return ({
    invalid_title: "法律名称无效",
    invalid_article: "条号不存在",
    quote_mismatch: "伪造或错引原文",
    semantic_entailment_not_evaluated: "语义支持未自动确认",
  } as Record<string, string>)[value] ?? value;
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
  <div class="rag-layer">
    <section class="rag-board" role="dialog" aria-modal="true" aria-label="可信RAG与三个典型问题验证">
      <header class="rag-head">
        <div class="rag-brand"><span class="rag-seal">证</span><div><p class="kicker mono">TRUSTED RAG · EXACT EVIDENCE · HUMAN REVIEW</p><h2>{{ viewMode === "examples" ? "刑法可信问答验证台" : "刑法多来源证据检索" }}</h2></div></div>
        <div class="rag-score" v-if="report && viewMode === 'examples'"><div><b>{{ report.automated_gate_pass_count }}/{{ report.case_count }}</b><span>引用检查</span></div><div><b>3</b><span>典型问题</span></div><div><b>待复核</b><span>法学专家</span></div></div>
        <div class="rag-score" v-else><div><b>5类</b><span>来源角色</span></div><div><b>RRF</b><span>混合召回</span></div><div><b>显式</b><span>效力提示</span></div></div>
        <nav class="rag-modes" aria-label="可信RAG视图"><button :class="{ active: viewMode === 'examples' }" @click="viewMode = 'examples'">典型问题</button><button :class="{ active: viewMode === 'explore' }" @click="viewMode = 'explore'">自由检索</button></nav>
        <button class="rag-close" aria-label="关闭可信RAG验证" @click="emit('close')">×</button>
      </header>

      <div v-if="loading && viewMode === 'examples'" class="rag-state"><span class="rag-seal">检</span><p>正在装载问题、系统输出、标准答案与权威Evidence……</p></div>
      <div v-else-if="error && !report && viewMode === 'examples'" class="rag-state rag-state--error"><span>!</span><p>{{ error }}</p><button @click="load">重试</button></div>

      <div v-else-if="viewMode === 'examples' && report && selected" class="rag-body">
        <aside class="question-index">
          <div class="index-title"><p class="kicker mono">CONTENT QUALITY · 20 POINTS</p><h3>三个典型问题</h3><span>模型不自评</span></div>
          <div class="question-list">
            <button v-for="(row, index) in report.cases" :key="row.case_id" :class="{ active: row.case_id === selected.case_id }" @click="selectCase(row)">
              <span class="mono">0{{ index + 1 }}</span><div><strong>{{ row.title }}</strong><small>{{ row.automated_gate_pass ? '引用检查通过' : '引用需要处理' }} · 专家{{ row.expert_review_status }}</small></div><i :class="{ pass: row.automated_gate_pass }"></i>
            </button>
          </div>
          <section class="suite-boundary"><strong>来源说明</strong><p>系统会检查条号、来源和引用原文；只有独立法学专家才能确认争议结论是否正确。</p></section>
          <button class="bad-audit-action" :disabled="auditing" @click="runBadCitationAudit">{{ auditing ? '正在检查…' : '演示错误引用检查 →' }}</button>
          <section v-if="badAudit" class="bad-audit-result"><header><span>拦</span><div><p class="kicker mono">引用检查</p><h3>{{ rejectedBadCitationCount }}/{{ badAudit.items.length }} 条错误已发现</h3></div></header><article v-for="row in badAudit.items" :key="row.index"><strong>{{ row.title }} {{ row.article_ref }}</strong><span>{{ auditStatusLabel(row.status) }} · {{ quoteStatusLabel(row.quote_status) }}</span><small>{{ row.risk_flags.map(riskLabel).join(' / ') }}</small></article><p>条号与引用原文可自动核对；是否支持当前结论仍需教师或专家判断。</p></section>
        </aside>

        <main class="answer-column">
          <section class="question-brief"><p class="kicker mono">典型问题</p><h3>{{ selected.question }}</h3><div><span>当前AI基线回答</span><span>引用来源可展开查看</span><span>AI生成内容</span></div></section>

          <div v-if="badAudit" class="evidence-tutor"><AITutor context="evidence" :speech-text="evidenceWarningSpeech" compact /></div>

          <section class="ai-answer"><header><span class="ai-stamp">AI</span><div><p class="kicker mono">GOVERNED MODEL OUTPUT</p><h3>系统回答</h3><span>置信度 {{ Math.round((selected.model_output.confidence ?? 0) * 100) }}% · 非正式法律意见</span></div></header><p class="answer-text"><span>{{ selected.model_output.answer }}</span><EvidenceCitations :references="modelReferences" /></p><ol><li v-for="step in selected.model_output.rule_steps" :key="step">{{ step }}</li></ol><blockquote><strong>结论</strong><span>{{ selected.model_output.conclusion }}</span><EvidenceCitations :references="modelReferences" compact /></blockquote><p class="uncertainty"><b>边界：</b>{{ selected.model_output.uncertainty || '模型未声明额外不确定性；仍需专家复核。' }}</p></section>

          <section class="gate-strip"><article v-for="gate in gateSummary" :key="gate.label" :class="{ pass: gate.passed }"><span>{{ gate.passed ? '✓' : '×' }}</span><strong>{{ gate.label }}</strong></article><div><b>{{ Math.round(selected.point_coverage * 100) }}%</b><span>标准要点覆盖</span></div></section>

          <section class="point-audit"><header><p class="kicker mono">回答质量检查</p><h3>应覆盖的关键要点</h3></header><div><span v-for="point in selected.point_audit" :key="point.point_id" :class="{ pass: point.passed }"><i>{{ point.passed ? '✓' : '×' }}</i>{{ point.label }}</span></div></section>
        </main>

        <aside class="evidence-column">
          <section class="expert-status"><span>师</span><div><p class="kicker mono">INDEPENDENT REVIEW</p><h3>法学专家：待复核</h3><p>自动3/3不等于专家确认准确；此状态必须保留到真实审核完成。</p></div></section>

          <section class="standard-answer"><p class="kicker mono">REFERENCE ANSWER</p><h3>标准答案对照</h3><p><span>{{ selected.standard_answer }}</span><EvidenceCitations :references="requiredReferences" compact /></p></section>

          <section class="sources"><header><div><p class="kicker mono">权威来源</p><h3>法律与案例依据</h3></div><span>{{ requiredSources.length }} 项</span></header><article v-for="source in requiredSources" :key="source.source_id"><div class="source-head"><span>{{ source.source_type === '法律条文' ? '法' : '案' }}</span><div><strong>{{ source.title }}</strong><small>{{ source.article_ref }} · {{ source.authority }}</small></div></div><blockquote>{{ source.quote }}</blockquote><dl><div><dt>版本</dt><dd>{{ versionLabel(source.version) }}</dd></div><div><dt>来源</dt><dd>{{ source.source_url || '课程资料库' }}</dd></div></dl></article></section>

          <section class="citation-proof"><p class="kicker mono">回答引用</p><h3>系统实际使用的原文</h3><article v-for="citation in selected.model_output.citations" :key="`${citation.source_id}:${citation.quote}`"><span>✓</span><div><strong>{{ citation.title }} {{ citation.article_ref }}</strong><p>{{ citation.quote }}</p></div></article></section>
        </aside>
      </div>

      <div v-else class="explorer-body">
        <aside class="explorer-query">
          <header><p class="kicker mono">MULTI-SOURCE EVIDENCE</p><h3>自由检索</h3><span>输入问题，查看不同法源各自能做什么</span></header>
          <label for="rag-free-query">刑法问题</label>
          <textarea id="rag-free-query" v-model="searchQuery" rows="5" maxlength="2000" placeholder="例如：正当防卫的成立条件是什么？" @keydown.ctrl.enter.prevent="runKnowledgeSearch()"></textarea>
          <button class="explorer-submit" :disabled="searching" @click="runKnowledgeSearch()">{{ searching ? "正在混合检索…" : "检索多来源Evidence →" }}</button>
          <section class="explorer-presets"><strong>快速验证五类来源</strong><button v-for="preset in searchPresets" :key="preset" @click="runKnowledgeSearch(preset)">{{ preset }}</button></section>
          <section class="explorer-rule"><strong>法源顺序</strong><p>法律 / 行政法规 → 司法解释与司法文件 → 案例 → 教材 → 练习。低层级材料不得覆盖高层级规范。</p></section>
        </aside>

        <main class="explorer-results">
          <section v-if="searchError" class="explorer-error"><strong>本次检索未完成</strong><p>{{ searchError }}</p></section>
          <section v-else-if="!searchResult" class="explorer-empty"><span class="rag-seal">检</span><h3>从一个真实问题开始</h3><p>系统会同时使用BM25F与Embedding召回，经RRF、精确条号保护和Reranker排序，再按来源身份生成EvidencePack。</p></section>
          <template v-else>
            <header class="explorer-result-head"><div><p class="kicker mono">GOVERNED RETRIEVAL RESULT</p><h3>{{ searchResult.query }}</h3></div><span>{{ searchReferences.length }}项公开证据</span></header>
            <section v-if="searchResult.knowledge_context.matched" class="graph-context"><div><strong>知识图已参与检索</strong><p>知识点、条号与先修节点用于扩展查询；检索结果再支撑诊断解释与下一任务。</p></div><article v-for="node in searchResult.knowledge_context.nodes" :key="node.name"><span>{{ node.chapter }}</span><h4>{{ node.name }}</h4><p>{{ node.law_article_refs.join(" · ") || "无直接条号" }}</p><small v-if="node.prerequisites.length">先修：{{ node.prerequisites.join(" / ") }}</small></article></section>
            <section v-if="sourceGroups.length" class="source-role-answer"><header><p class="kicker mono">SOURCE-AWARE SUMMARY</p><h3>同一问题，来源承担不同角色</h3></header><article v-for="group in sourceGroups" :key="group.usage"><strong>{{ group.label }}</strong><p><span>{{ group.explanation }}</span><EvidenceCitations :references="group.references" /></p></article><footer>行末编号可悬停看摘要、点击看完整原文和来源。检索相关不等于法律蕴含，具体事实适用仍需判断。</footer></section>
            <section v-else class="explorer-empty compact"><h3>当前证据不足</h3><p>系统不会用语义相近材料冒充明确法名或条号。请核对名称、条号，或补充事实后重试。</p></section>
          </template>
        </main>
      </div>
    </section>
  </div>
</template>

<style scoped>
.evidence-tutor{margin-top:14px}
.rag-layer{position:fixed;inset:0;z-index:1370;padding:18px;background:radial-gradient(circle at 12% 8%,rgba(176,138,62,.13),transparent 31%),radial-gradient(circle at 88% 80%,rgba(92,122,138,.12),transparent 34%),rgba(4,3,2,.93);backdrop-filter:blur(13px)}.rag-board{height:100%;min-height:0;display:flex;flex-direction:column;overflow:hidden;color:var(--parchment);border:1px solid rgba(176,138,62,.44);background:linear-gradient(140deg,#17150f,#090a09 72%);box-shadow:0 40px 110px #000d}.rag-head{min-height:82px;display:grid;grid-template-columns:minmax(300px,1fr) auto minmax(250px,1fr) 38px;align-items:center;gap:18px;padding:12px 18px 12px 23px;border-bottom:1px solid rgba(176,138,62,.3);background:linear-gradient(180deg,rgba(29,27,20,.98),rgba(13,14,12,.98))}.rag-brand{display:flex;align-items:center;gap:13px}.rag-seal{width:47px;height:47px;display:grid;place-items:center;color:#ead8b1;border:1px solid var(--accent-amber);box-shadow:inset 0 0 0 3px #271f10;font-family:var(--font-display);font-size:1.08rem;font-weight:800;transform:rotate(-2deg)}.kicker{margin:0 0 3px;color:#c5a661;font-size:.6rem;letter-spacing:.16em}.rag-brand h2{font-size:1.28rem}.rag-score{display:grid;grid-template-columns:repeat(3,100px);border:1px solid var(--line)}.rag-score div{padding:8px;text-align:center;border-right:1px solid var(--line)}.rag-score div:last-child{border:0}.rag-score b{display:block;font-family:var(--font-mono);font-size:.95rem}.rag-score span{color:var(--parchment-faint);font-size:.58rem}.rag-score div:last-child b{color:#df9e86;font-size:.72rem}.rag-badges{display:flex;justify-content:flex-end;gap:6px}.rag-badges span{padding:4px 6px;color:var(--parchment-faint);border:1px solid var(--line);font-size:.59rem}.rag-close{width:36px;height:36px;color:var(--parchment-muted);border:1px solid var(--line-strong);background:transparent;font-size:1.35rem}.rag-state{flex:1;display:grid;place-content:center;justify-items:center;gap:13px;color:var(--parchment-muted)}.rag-state--error>span{width:42px;height:42px;display:grid;place-items:center;color:#df9e86;border:1px solid var(--accent)}.rag-state button{padding:7px 12px;color:var(--parchment);border:1px solid var(--line);background:transparent}.rag-body{flex:1;min-height:0;display:grid;grid-template-columns:250px minmax(0,1fr) 390px;background:linear-gradient(90deg,rgba(255,255,255,.012) 1px,transparent 1px) 0 0/56px 56px}.question-index,.answer-column,.evidence-column{min-height:0;overflow-y:auto;padding:19px 14px}.question-index{border-right:1px solid var(--line-strong);background:rgba(10,9,6,.66)}.answer-column{padding:23px clamp(20px,2.3vw,37px) 45px}.evidence-column{border-left:1px solid var(--line-strong);background:rgba(8,10,9,.62)}.index-title{position:relative}.index-title h3{font-size:1.06rem}.index-title>span{position:absolute;right:0;bottom:1px;color:var(--parchment-faint);font-size:.58rem}.question-list{display:grid;gap:7px;margin-top:14px}.question-list button{display:grid;grid-template-columns:26px minmax(0,1fr) 8px;gap:8px;padding:11px 8px;color:var(--parchment-muted);text-align:left;border:1px solid transparent;background:transparent;cursor:pointer}.question-list button.active{color:var(--parchment);border-color:rgba(176,138,62,.42);background:linear-gradient(90deg,rgba(176,138,62,.1),transparent)}.question-list button>span{color:var(--parchment-faint);font-size:.6rem}.question-list div{min-width:0;display:grid}.question-list strong{font-family:var(--font-display);font-size:.78rem}.question-list small{margin-top:3px;color:var(--parchment-faint);font-size:.58rem}.question-list i{width:7px;height:7px;align-self:center;background:var(--accent)}.question-list i.pass{background:var(--accent-success)}.suite-boundary{margin-top:16px;padding:10px;border:1px dashed var(--line-strong)}.suite-boundary strong{color:var(--accent);font-family:var(--font-display);font-size:.72rem}.suite-boundary p{margin:5px 0 0;color:var(--parchment-faint);font-size:.64rem;line-height:1.55}.suite-sha{margin:12px 0}.suite-sha div{display:flex;justify-content:space-between;padding:4px 0;color:var(--parchment-faint);border-bottom:1px solid var(--line);font-size:.55rem}.suite-sha dd{margin:0}.bad-audit-action{width:100%;padding:8px;color:#e8b398;border:1px solid rgba(196,71,27,.48);background:rgba(196,71,27,.06);font-family:var(--font-display);cursor:pointer}.bad-audit-result{margin-top:10px;padding:10px;border:1px solid rgba(196,71,27,.45);background:rgba(196,71,27,.035)}.bad-audit-result header{display:flex;align-items:center;gap:9px}.bad-audit-result header>span{width:31px;height:31px;display:grid;place-items:center;color:#e3a18b;border:1px solid currentColor;font-family:var(--font-display)}.bad-audit-result h3{font-size:.82rem}.bad-audit-result article{display:grid;margin-top:7px;padding-top:6px;border-top:1px solid var(--line)}.bad-audit-result article strong{font-size:.65rem}.bad-audit-result article span,.bad-audit-result article small{color:#df9e86;font-size:.56rem}.bad-audit-result>p{color:var(--parchment-faint);font-size:.55rem}.question-brief{padding-bottom:16px;border-bottom:1px solid rgba(176,138,62,.3)}.question-brief h3{font-size:1.12rem;font-weight:520;line-height:1.65}.question-brief>div{display:flex;gap:6px;margin-top:9px}.question-brief>div span{padding:3px 6px;color:var(--parchment-dim);border:1px solid var(--line);font-size:.59rem}.question-brief>div span:last-child{color:#e3a18b;border-color:rgba(196,71,27,.38)}.ai-answer{margin-top:14px;padding:15px;border:1px solid rgba(122,153,98,.42);background:linear-gradient(130deg,rgba(122,153,98,.055),rgba(255,255,255,.01))}.ai-answer header{display:flex;gap:11px}.ai-stamp{width:41px;height:41px;display:grid;place-items:center;color:#bcd0b1;border:1px solid rgba(122,153,98,.55);font-family:var(--font-mono)}.ai-answer h3{font-size:.98rem}.ai-answer header div>span{color:var(--parchment-faint);font-size:.61rem}.answer-text{color:var(--parchment);font-size:.8rem;line-height:1.75}.ai-answer ol{padding-left:22px;color:var(--parchment-muted);font-size:.72rem;line-height:1.65}.ai-answer blockquote{margin:10px 0;padding:9px 11px;color:#d7e5d1;border-left:2px solid var(--accent-success);background:rgba(0,0,0,.16);font-size:.73rem}.ai-answer blockquote strong{margin-right:8px;color:var(--accent-success)}.uncertainty{margin:8px 0 0;color:var(--parchment-faint);font-size:.63rem}.gate-strip{display:grid;grid-template-columns:repeat(4,1fr) 100px;gap:6px;margin-top:12px}.gate-strip article,.gate-strip>div{display:flex;align-items:center;justify-content:center;gap:6px;padding:8px;border:1px solid var(--line);font-size:.62rem}.gate-strip article span{color:var(--accent)}.gate-strip article.pass span{color:var(--accent-success)}.gate-strip article.pass{border-color:rgba(122,153,98,.35)}.gate-strip>div{display:grid;text-align:center}.gate-strip>div b{font-family:var(--font-mono);font-size:.9rem}.gate-strip>div span{color:var(--parchment-faint);font-size:.53rem}.point-audit{margin-top:12px;padding:12px;border:1px solid var(--line)}.point-audit h3{font-size:.88rem}.point-audit>div{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}.point-audit span{padding:4px 6px;color:#df9e86;border:1px solid rgba(196,71,27,.33);font-size:.6rem}.point-audit span.pass{color:#b8cdaa;border-color:rgba(122,153,98,.35)}.point-audit i{margin-right:4px;font-style:normal}.expert-status{display:flex;gap:10px;padding:10px;border:1px solid rgba(196,71,27,.45);background:rgba(196,71,27,.035)}.expert-status>span{width:35px;height:35px;display:grid;place-items:center;color:#e4a790;border:1px solid currentColor;font-family:var(--font-display)}.expert-status h3{font-size:.82rem}.expert-status p{margin:4px 0 0;color:var(--parchment-faint);font-size:.58rem}.standard-answer{margin-top:11px;padding:11px;border:1px solid rgba(100,139,153,.4);background:rgba(100,139,153,.035)}.standard-answer h3{font-size:.85rem}.standard-answer p{margin:7px 0 0;color:var(--parchment-muted);font-size:.69rem;line-height:1.65}.sources{margin-top:12px}.sources>header{display:flex;justify-content:space-between;align-items:flex-end}.sources h3,.citation-proof h3{font-size:.88rem}.sources>header>span{color:var(--parchment-faint);font-size:.58rem}.sources>article{margin-top:8px;padding:10px;border:1px solid var(--line);background:rgba(255,255,255,.012)}.source-head{display:grid;grid-template-columns:30px minmax(0,1fr);gap:8px}.source-head>span{width:28px;height:28px;display:grid;place-items:center;color:#d8c184;border:1px solid rgba(176,138,62,.42);font-family:var(--font-display)}.source-head div{min-width:0;display:grid}.source-head strong{font-size:.68rem}.source-head small{color:var(--parchment-faint);font-size:.55rem}.sources blockquote{max-height:115px;overflow-y:auto;margin:8px 0;padding:8px;color:var(--parchment-muted);border-left:2px solid var(--accent-amber);background:rgba(0,0,0,.17);font-size:.61rem;line-height:1.55;white-space:pre-wrap}.sources dl{margin:0}.sources dl div{display:grid;grid-template-columns:55px minmax(0,1fr);gap:6px;padding:3px 0;border-bottom:1px solid var(--line);font-size:.53rem}.sources dt{color:var(--parchment-faint)}.sources dd{overflow:hidden;margin:0;color:var(--parchment-dim);white-space:nowrap;text-overflow:ellipsis}.citation-proof{margin-top:12px;padding-top:11px;border-top:1px solid var(--line-strong)}.citation-proof article{display:grid;grid-template-columns:22px minmax(0,1fr);gap:7px;margin-top:7px}.citation-proof article>span{width:20px;height:20px;display:grid;place-items:center;color:#b8cdaa;border:1px solid rgba(122,153,98,.38);font-size:.6rem}.citation-proof strong{font-size:.63rem}.citation-proof p{margin:3px 0;color:var(--parchment-faint);font-size:.56rem;line-height:1.45}.citation-proof small{color:#85a8b5;font-size:.51rem}
.rag-modes{display:flex;justify-content:flex-end;border:1px solid var(--line)}
.rag-modes button{padding:8px 11px;color:var(--parchment-faint);border:0;border-right:1px solid var(--line);background:transparent;font:inherit;font-size:.65rem;cursor:pointer}
.rag-modes button:last-child{border:0}
.rag-modes button.active{color:#f0dfba;background:rgba(176,138,62,.12);box-shadow:inset 0 -2px var(--accent-amber)}
.explorer-body{flex:1;min-height:0;display:grid;grid-template-columns:minmax(290px,340px) minmax(0,1fr);background:linear-gradient(90deg,rgba(255,255,255,.012) 1px,transparent 1px) 0 0/56px 56px}
.explorer-query,.explorer-results{min-height:0;overflow-y:auto}
.explorer-query{padding:24px 20px 42px;border-right:1px solid var(--line-strong);background:rgba(10,9,6,.72)}
.explorer-query header h3{font-size:1.35rem}.explorer-query header span{color:var(--parchment-faint);font-size:.72rem}
.explorer-query>label{display:block;margin-top:24px;color:#d6bd83;font-family:var(--font-display);font-size:.78rem}
.explorer-query textarea{width:100%;min-height:126px;margin-top:8px;padding:12px;color:var(--parchment);border:1px solid rgba(176,138,62,.38);border-radius:0;background:rgba(0,0,0,.23);font:inherit;font-size:.76rem;line-height:1.65;resize:vertical}
.explorer-query textarea:focus{outline:1px solid #c6a65e;outline-offset:2px}
.explorer-submit{width:100%;margin-top:10px;padding:11px;color:#f1dfb6;border:1px solid rgba(176,138,62,.62);background:rgba(176,138,62,.12);font-family:var(--font-display);cursor:pointer}.explorer-submit:disabled{cursor:wait;opacity:.55}
.explorer-presets{display:grid;gap:5px;margin-top:22px}.explorer-presets strong,.explorer-rule strong{color:#d8c184;font-family:var(--font-display);font-size:.73rem}
.explorer-presets button{padding:8px 9px;color:var(--parchment-muted);text-align:left;border:1px solid var(--line);background:rgba(255,255,255,.012);font:inherit;font-size:.65rem;line-height:1.45;cursor:pointer}.explorer-presets button:hover{color:var(--parchment);border-color:rgba(176,138,62,.5)}
.explorer-rule{margin-top:20px;padding:11px;border-left:2px solid #b08a3e;background:rgba(176,138,62,.045)}.explorer-rule p{margin:6px 0 0;color:var(--parchment-faint);font-size:.65rem;line-height:1.6}
.explorer-results{padding:28px clamp(24px,3vw,48px) 52px}
.explorer-empty{min-height:100%;display:grid;place-content:center;justify-items:center;gap:12px;text-align:center}.explorer-empty.compact{min-height:260px}.explorer-empty h3{font-size:1.25rem}.explorer-empty p{max-width:65ch;color:var(--parchment-faint);font-size:.76rem;line-height:1.7}
.explorer-error{padding:16px;color:#efb19a;border:1px solid rgba(196,71,27,.5);background:rgba(196,71,27,.04)}.explorer-error p{margin:6px 0 0}
.explorer-result-head{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;padding-bottom:17px;border-bottom:1px solid rgba(176,138,62,.32)}.explorer-result-head h3{max-width:900px;font-size:clamp(1.2rem,2vw,2rem);font-weight:520;line-height:1.45}.explorer-result-head>span{flex:none;padding:6px 9px;color:#d8c184;border:1px solid rgba(176,138,62,.38);font-size:.66rem}
.graph-context{display:grid;grid-template-columns:minmax(260px,1.25fr) repeat(2,minmax(190px,1fr));gap:8px;margin-top:15px}.graph-context>div,.graph-context>article{padding:13px;border:1px solid rgba(100,139,153,.34);background:rgba(100,139,153,.035)}.graph-context>div strong{color:#b8d1d7;font-family:var(--font-display);font-size:.8rem}.graph-context>div p,.graph-context article p,.graph-context article small{margin:5px 0 0;color:var(--parchment-faint);font-size:.63rem;line-height:1.5}.graph-context article>span{color:#86aab5;font-size:.57rem}.graph-context article h4{margin-top:4px;font-size:.78rem}
.source-role-answer{margin-top:18px;border:1px solid var(--line-strong);background:linear-gradient(135deg,rgba(122,153,98,.035),rgba(176,138,62,.02))}.source-role-answer>header{padding:15px 17px;border-bottom:1px solid var(--line)}.source-role-answer>header h3{font-size:1rem}.source-role-answer>article{display:grid;grid-template-columns:125px minmax(0,1fr);gap:18px;padding:14px 17px;border-bottom:1px solid var(--line)}.source-role-answer>article>strong{color:#dac48f;font-family:var(--font-display);font-size:.78rem}.source-role-answer>article p{margin:0;color:var(--parchment-muted);font-size:.74rem;line-height:1.7}.source-role-answer>footer{padding:12px 17px;color:var(--parchment-faint);font-size:.65rem;line-height:1.55}
@media(max-width:1180px){.rag-head{grid-template-columns:1fr auto 38px}.rag-modes{grid-column:2}.rag-score{display:none}.rag-body{grid-template-columns:220px minmax(0,1fr)}.evidence-column{grid-column:1/-1;border-top:1px solid var(--line-strong);border-left:0;display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.sources,.citation-proof{margin-top:0}.expert-status,.standard-answer{align-self:start}.graph-context{grid-template-columns:1fr 1fr}.graph-context>div{grid-column:1/-1}}
@media(max-width:820px){.rag-layer{padding:0}.rag-head{grid-template-columns:1fr 38px;padding:10px 12px}.rag-score{grid-column:1/-1;grid-row:2;grid-template-columns:repeat(3,1fr)}.rag-body{display:block;overflow-y:auto}.question-index,.answer-column,.evidence-column{min-height:auto;overflow:visible;border:0}.evidence-column{display:block}.gate-strip{grid-template-columns:repeat(2,1fr)}.question-list{grid-template-columns:1fr}.rag-brand h2{font-size:1.05rem}}
@media(max-width:820px){.rag-modes{grid-column:1/-1;grid-row:2;justify-content:stretch}.rag-modes button{flex:1}.explorer-body{display:block;overflow-y:auto}.explorer-query,.explorer-results{min-height:auto;overflow:visible}.graph-context{grid-template-columns:1fr}.graph-context>div{grid-column:auto}.source-role-answer>article{grid-template-columns:1fr;gap:6px}}
</style>
