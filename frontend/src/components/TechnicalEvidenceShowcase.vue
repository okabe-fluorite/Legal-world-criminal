<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { api } from "../lib/api";
import type { TechnicalEvidenceSnapshot } from "../lib/types";

const emit = defineEmits<{ close: [] }>();
const loading = ref(true);
const error = ref("");
const evidence = ref<TechnicalEvidenceSnapshot | null>(null);
const tab = ref<"overview" | "data" | "reasoning" | "agent">("overview");

const tabs = [
  { id: "overview" as const, label: "总账" },
  { id: "data" as const, label: "数据治理" },
  { id: "reasoning" as const, label: "推理 / 评测" },
  { id: "agent" as const, label: "Agent / 边界" },
];

const typeLabels: Record<string, string> = {
  law_source_qa: "法源问答",
  issue_subsumption: "争点涵摄",
  pro_con_reasoning: "正反论证",
  teaching_feedback: "教学反馈",
  safety_abstention: "安全弃权",
};
const checkLabels: Record<string, string> = {
  schema_valid: "Schema",
  context_identity: "上下文版本",
  evidence_scope: "Evidence范围",
  citation_title_article: "标题/条号",
  quote_exact: "逐字quote",
  student_visible_facts: "学生可见事实",
  required_elements: "必要要件",
  counterargument_present: "反方观点",
  conclusion_strength: "结论强度",
  reliable_abstention: "可靠弃权",
  prompt_injection_resisted: "注入阻断",
};
const fixtureLabels: Record<string, string> = {
  negative_teacher_private_fact: "教师私有事实",
  negative_fabricated_quote: "伪造引文",
  negative_missing_elements_and_counterargument: "漏要件/无反方",
  negative_insufficient_but_strong_conclusion: "证据不足强结论",
  negative_prompt_injection_executed: "提示注入",
  negative_out_of_scope_evidence: "越界Evidence",
};
const pipeline = computed(() => {
  const row = evidence.value;
  if (!row) return [];
  return [
    { no: "01", label: "候选材料", metric: row.summary.candidate_files.toLocaleString(), note: "文件库存，不等于训练集" },
    { no: "02", label: "正式法源", metric: row.summary.formal_articles.toLocaleString(), note: "505刑法 + 308刑诉法" },
    { no: "03", label: "混合检索", metric: row.summary.hybrid_records.toLocaleString(), note: "法源·教材·公开题分库" },
    { no: "04", label: "推理检查", metric: `${row.summary.reasoning_gate_checks}项`, note: "结构、来源与引用检查" },
    { no: "05", label: "统一评测", metric: `${row.summary.benchmark_items}题`, note: "候选题 · 待教师确认" },
    { no: "06", label: "应用验证", metric: "4场景", note: "问答·案件·主观·路径" },
  ];
});
const evalTypes = computed(() => Object.entries(evidence.value?.legal_edu_eval.by_type ?? {}).map(
  ([key, value]) => ({ key, label: typeLabels[key] ?? key, value }),
));
const ratio = (value: number) => Number(value || 0).toFixed(4);
const seconds = (value: number) => `${(Number(value || 0) / 1000).toFixed(1)}s`;
const routeName = computed(() => String(evidence.value?.agent_ablation.model_route.model_name ?? "unknown"));
const conditionLabels: Record<string, string> = {
  E0_base_model: "基础模型",
  E1_prompt_few_shot: "Prompt / Few-shot",
  E2_trusted_rag: "可信RAG",
  E3_rag_finetuned_model: "RAG + 微调模型",
};
function statusLabel(value: unknown): string {
  const status = String(value ?? "");
  if (status === "pending_model_delivery") return "待模型交付";
  if (status.includes("pending")) return "待运行";
  if (status === "not_gold") return "候选评测集";
  return status || "待确认";
}
function boundaryLabel(value: string): string {
  const text = String(value || "");
  if (text.includes("automatic gates")) return "自动检查用于发现软件和引用错误，不代表法学专家准确率";
  if (text.includes("MOOCCubeX")) return "ORCDF来自民法/宪法实验，不能直接当作刑法课堂掌握度";
  if (text.includes("candidate benchmark")) return "100题仍是候选评测集，需要教师逐题确认";
  if (text.includes("fixed scripted E2E")) return "当前软件测试证明流程可运行，不等同真实学习效果";
  return text;
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try { evidence.value = await api.technicalEvidence(); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason); }
  finally { loading.value = false; }
}
function handleKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") emit("close");
}
onMounted(() => { window.addEventListener("keydown", handleKeydown); void load(); });
onUnmounted(() => window.removeEventListener("keydown", handleKeydown));
</script>

<template>
  <div class="tech-layer">
    <section class="tech-board" role="dialog" aria-modal="true" aria-label="学科技术说明">
      <header class="tech-head">
        <div class="tech-brand"><span class="tech-seal">证</span><div><p class="kicker mono">TECHNICAL EVIDENCE · TRACEABLE · HONEST PENDING</p><h2>刑法学科技术说明</h2></div></div>
        <nav class="tech-tabs" aria-label="技术说明分区"><button v-for="item in tabs" :key="item.id" :class="{ active: tab === item.id }" @click="tab = item.id">{{ item.label }}</button></nav>
        <div v-if="evidence" class="tech-state mono"><span>核心技术结果</span><strong>只读展示</strong></div>
        <button class="tech-close" aria-label="关闭技术说明" @click="emit('close')">×</button>
      </header>

      <div v-if="loading" class="tech-loading"><span class="tech-seal">验</span><p>正在读取技术结果与当前状态……</p></div>
      <div v-else-if="error || !evidence" class="tech-loading tech-loading--error"><span>!</span><p>{{ error || "技术结果暂不可用" }}</p><button @click="load">重新读取</button></div>

      <main v-else class="tech-content">
        <section class="tech-purpose" role="note" aria-label="技术说明页面用途">
          <strong>比赛 / 答辩只读视图</strong>
          <p>用于展示数据治理、推理检查、评测、Agent对比与未完成事项，让核心技术在现场能够快速看懂。</p>
          <span>不参与学生作答、评分、LearningEvent或长期画像</span>
        </section>
        <template v-if="tab === 'overview'">
          <section class="overview-statement"><div><p class="kicker mono">核心技术结果</p><h3>不是“功能很多”，<br>而是数据、推理与应用相互支撑</h3></div><div class="overview-number"><b>{{ evidence.summary.formal_articles }}</b><span>正式法源</span><small>{{ evidence.data_governance.version_as_of }}版本</small></div></section>
          <section class="pipeline"><article v-for="(item, index) in pipeline" :key="item.no"><span class="mono">{{ item.no }}</span><strong>{{ item.metric }}</strong><h4>{{ item.label }}</h4><p>{{ item.note }}</p><i v-if="index < pipeline.length - 1">→</i></article></section>
          <section class="overview-grid"><article><p class="kicker mono">DATA</p><b>{{ evidence.data_governance.gates_passed }}/{{ evidence.data_governance.gates_total }}</b><h4>资料检查完成</h4><span>{{ evidence.summary.formal_articles }}条正式法源</span></article><article><p class="kicker mono">REASONING</p><b>{{ evidence.legal_reasoning.positive_passed }} / {{ evidence.legal_reasoning.negative_blocked }}</b><h4>正常示例 / 错误示例</h4><span>关键错误可自动发现</span></article><article><p class="kicker mono">EVAL</p><b>{{ evidence.legal_edu_eval.by_split.dev }} / {{ evidence.legal_edu_eval.by_split.test }}</b><h4>开发集 / 测试集</h4><span>按来源分组避免泄漏</span></article><article class="pending"><p class="kicker mono">真实人员</p><b>待完成</b><h4>专家 · 用户 · 签署</h4><span>等待真实人员完成</span></article></section>
          <section class="global-boundary"><strong>使用说明</strong><p v-for="item in evidence.global_boundary" :key="item"><span>!</span>{{ boundaryLabel(item) }}</p></section>
        </template>

        <template v-else-if="tab === 'data'">
          <section class="section-title"><div><p class="kicker mono">4,173 → GOVERNANCE → 813</p><h3>候选资料与正式法源分层</h3></div><span class="status-pass">资料检查已完成</span></section>
          <div class="data-grid"><section class="data-ledger"><article><b>{{ evidence.data_governance.inventory_files.toLocaleString() }}</b><div><h4>候选文件库存</h4><p>原始文档、派生文本、压缩包、脚本和缓存</p></div><span>RAW</span></article><article><b>{{ evidence.data_governance.formal_articles }}</b><div><h4>正式规范法源</h4><p>{{ evidence.data_governance.criminal_law_articles }}刑法 + {{ evidence.data_governance.criminal_procedure_articles }}刑诉法</p></div><span>L1</span></article><article><b>{{ evidence.hybrid_rag.records.toLocaleString() }}</b><div><h4>分层混合检索记录</h4><p>法源案例 {{ evidence.hybrid_rag.collections.legal_authority?.toLocaleString() }} · 教材 {{ evidence.hybrid_rag.collections.textbook_explanation?.toLocaleString() }} · 公开题 {{ evidence.hybrid_rag.collections.question_public?.toLocaleString() }}</p></div><span>RAG</span></article><article><b>{{ evidence.data_governance.l2_candidates }} / {{ evidence.data_governance.l3_candidates }}</b><div><h4>司法解释 / 案例候选</h4><p>保持法律、版权与隐私复核状态</p></div><span>L2/L3</span></article><article><b>{{ evidence.data_governance.knowledge_evidence_links }}</b><div><h4>知识—Evidence链接</h4><p>课程知识、正式法条与CaseBundle锚定</p></div><span>LINK</span></article></section>
            <section class="version-audit"><header><p class="kicker mono">2024 CRIMINAL LAW AUDIT</p><h3>年份正确，不代表文件可直接准入</h3></header><div class="version-hero"><b>{{ evidence.data_governance.version_as_of }}</b><span>刑法修正案十二施行版本</span></div><dl><div><dt>七处修正案匹配</dt><dd>{{ evidence.data_governance.amendment_12_matches }}/7</dd></div><div><dt>清理后逐字一致</dt><dd>{{ evidence.data_governance.reference_exact_articles }}/{{ evidence.data_governance.criminal_law_articles }}</dd></div><div><dt>剩余差异条文</dt><dd>{{ evidence.data_governance.reference_differences }}</dd></div><div><dt>参考文件正式准入</dt><dd class="reject">{{ evidence.data_governance.reference_formal_admission ? "允许" : "拒绝" }}</dd></div></dl><footer>正式库继续采用官方正文 + 官方修正案确定性合并；真实课堂前仍需核验届时有效性。</footer></section></div>
        </template>

        <template v-else-if="tab === 'reasoning'">
          <section class="section-title"><div><p class="kicker mono">LEGAL REASONING CHECKS</p><h3>结构化推理与100题评测共用来源检查</h3></div><span class="status-pass">{{ evidence.legal_reasoning.fixtures }}/{{ evidence.legal_reasoning.fixtures }} 示例符合预期</span></section>
          <section class="rag-experiment"><div><p class="kicker mono">HYBRID RETRIEVAL · CANDIDATE EVAL</p><h3>{{ evidence.hybrid_rag.retrieval_pipeline }}</h3><span>{{ evidence.hybrid_rag.embedding_model }} · {{ evidence.hybrid_rag.vector_dimension }}维</span></div><dl><div><dt>检索记录</dt><dd>{{ evidence.hybrid_rag.records.toLocaleString() }}</dd></div><div><dt>候选Recall@5</dt><dd>{{ ratio(evidence.hybrid_rag.candidate_recall_at_5) }}</dd></div><div><dt>候选NDCG@10</dt><dd>{{ ratio(evidence.hybrid_rag.candidate_ndcg_at_10) }}</dd></div><div><dt>不存在法条误返回</dt><dd>{{ ratio(evidence.hybrid_rag.no_answer_false_positive_rate) }}</dd></div></dl><footer>{{ evidence.hybrid_rag.candidate_qrels }}条候选查询尚待教师复核；当前数字用于比较检索方案，不代表专家准确率。</footer></section>
          <div class="reasoning-grid"><section class="gate-panel"><header><div><p class="kicker mono">11 AUTOMATED CHECKS</p><h3>关键错误可以自动发现</h3></div><div class="gate-score"><b>{{ evidence.legal_reasoning.positive_passed }}</b><span>正常示例</span><b>{{ evidence.legal_reasoning.negative_blocked }}</b><span>错误示例</span></div></header><div class="check-grid"><span v-for="check in evidence.legal_reasoning.checks" :key="check"><i>✓</i>{{ checkLabels[check] ?? check }}</span></div><div class="fixture-list"><article v-for="row in evidence.legal_reasoning.negative_fixtures" :key="row.fixture_id"><strong>{{ fixtureLabels[row.fixture_id] ?? row.fixture_id }}</strong><small>{{ row.failed_checks.map(check => checkLabels[check] ?? check).join(' / ') }}</small></article></div><footer>自动检查用于发现明显错误，争议性法律判断仍由教师或专家确认。</footer></section>
            <section class="eval-panel"><header><p class="kicker mono">LEGALEDUEVAL-V1 · CANDIDATE</p><h3>{{ evidence.legal_edu_eval.items }}题模型无关评测</h3><span>{{ statusLabel(evidence.legal_edu_eval.gold_status) }}</span></header><div class="eval-types"><article v-for="row in evalTypes" :key="row.key"><b>{{ row.value }}</b><span>{{ row.label }}</span></article></div><div class="split-proof"><div><b>{{ evidence.legal_edu_eval.by_split.dev }} / {{ evidence.legal_edu_eval.by_split.test }}</b><span>开发集 / 测试集</span></div><div><b>{{ evidence.legal_edu_eval.cross_split_family_overlap }}</b><span>来源重复</span></div></div><div class="eval-matrix"><article v-for="(status, condition) in evidence.legal_edu_eval.evaluation_matrix" :key="condition"><span>{{ conditionLabels[String(condition)] ?? condition }}</span><strong :class="{ pending: String(status).includes('pending') }">{{ statusLabel(status) }}</strong></article></div><footer v-if="evidence.legal_edu_eval.training_manifest_check_required">接入训练模型前需检查测试题是否与训练数据重复；当前100题仍待教师逐题确认。</footer></section></div>
        </template>

        <template v-else>
          <section class="section-title"><div><p class="kicker mono">AGENT C0 / C1 · SAME CASE · SAME MODEL</p><h3>增加反方的收益，必须与成本一起展示</h3></div><span class="status-pending">TEACHER {{ evidence.agent_ablation.teacher_blind_review }}</span></section>
          <div class="agent-grid"><section class="condition"><header><span>C0</span><div><p class="kicker mono">STATIC RESPONSE</p><h3>静态材料 + 单次提示</h3></div></header><div class="condition-metrics"><div><b>{{ evidence.agent_ablation.c0.required_element_coverage }}/{{ evidence.agent_ablation.c0.required_element_total }}</b><span>要件</span></div><div><b>{{ evidence.agent_ablation.c0.counterargument_count }}</b><span>反方</span></div><div><b>{{ seconds(evidence.agent_ablation.c0.elapsed_ms) }}</b><span>耗时</span></div><div><b>{{ evidence.agent_ablation.c0.total_tokens.toLocaleString() }}</b><span>tokens</span></div></div><footer><span :class="{ pass: evidence.agent_ablation.c0.gate_pass }">结果检查 {{ evidence.agent_ablation.c0.gate_pass ? "通过" : "需处理" }}</span><small>{{ routeName }}</small></footer></section>
            <section class="agent-delta"><p class="kicker mono">C1 / C0 COST</p><div><b>+{{ evidence.agent_ablation.comparison.counterargument_count_delta }}</b><span>反方观点</span></div><div><strong>×{{ ratio(evidence.agent_ablation.comparison.elapsed_ratio_c1_over_c0) }}</strong><small>耗时</small></div><div><strong>×{{ ratio(evidence.agent_ablation.comparison.token_ratio_c1_over_c0) }}</strong><small>tokens</small></div></section>
            <section class="condition c1"><header><span>C1</span><div><p class="kicker mono">ORCHESTRATED REASONING</p><h3>事实检查 → 质询 → 修订</h3></div></header><div class="condition-metrics"><div><b>{{ evidence.agent_ablation.c1.required_element_coverage }}/{{ evidence.agent_ablation.c1.required_element_total }}</b><span>要件</span></div><div><b>{{ evidence.agent_ablation.c1.counterargument_count }}</b><span>反方</span></div><div><b>{{ seconds(evidence.agent_ablation.c1.elapsed_ms) }}</b><span>耗时</span></div><div><b>{{ evidence.agent_ablation.c1.total_tokens.toLocaleString() }}</b><span>tokens</span></div></div><footer><span :class="{ pass: evidence.agent_ablation.c1.gate_pass }">结果检查 {{ evidence.agent_ablation.c1.gate_pass ? "通过" : "需处理" }}</span><small>{{ evidence.agent_ablation.c1.raw_schema_pass ? "格式完整" : "已自动整理格式" }}</small></footer></section></div>
          <section class="agent-bottom"><article><p class="kicker mono">FORMAT NORMALIZATION</p><h4>不增加模型调用 · 不改变法律判断</h4><p>只整理结果格式，原始结果保留在内部实验记录中。</p></article><article><p class="kicker mono">LIGHTWEIGHT TUTOR</p><h4>{{ evidence.interaction.tutor_states }}态 · {{ evidence.interaction.allowed_contexts.length }}场景 · 画像更新0</h4><p>{{ evidence.interaction.label }}；不是Live2D或已连接的讯飞数字人。</p></article><section class="pending-list"><header><p class="kicker mono">NEXT STEPS</p><h4>下一步仍需完成</h4></header><div><article v-for="row in evidence.pending" :key="row.item"><span>{{ statusLabel(row.status) }}</span><strong>{{ row.item }}</strong><p>{{ row.required_evidence }}</p></article></div></section></section>
        </template>

      </main>
    </section>
  </div>
</template>

<style scoped>
.tech-layer{position:fixed;inset:0;z-index:1500;padding:18px;background:radial-gradient(circle at 82% 12%,rgba(48,95,117,.14),transparent 34%),rgba(3,4,4,.94);backdrop-filter:blur(14px)}.tech-board{height:100%;min-height:0;display:flex;flex-direction:column;overflow:hidden;color:var(--parchment);border:1px solid rgba(100,139,153,.48);background:linear-gradient(145deg,#111714,#070908 72%);box-shadow:0 40px 110px #000d}.tech-head{min-height:82px;display:grid;grid-template-columns:minmax(330px,1fr) auto 120px 38px;align-items:center;gap:18px;padding:11px 18px 11px 23px;border-bottom:1px solid rgba(100,139,153,.34);background:rgba(17,22,19,.98)}.tech-brand{display:flex;align-items:center;gap:13px}.tech-seal{width:47px;height:47px;display:grid;place-items:center;color:#dce9ec;border:1px solid #7199a8;box-shadow:inset 0 0 0 3px #112126;font-family:var(--font-display);font-size:1.08rem;font-weight:800;transform:rotate(-2deg)}.kicker{margin:0 0 3px;color:#88adba;font-size:.59rem;letter-spacing:.16em}.tech-brand h2{font-size:1.25rem}.tech-tabs{display:flex;border:1px solid var(--line)}.tech-tabs button{padding:9px 14px;color:var(--parchment-dim);border:0;border-right:1px solid var(--line);background:transparent;font:inherit;font-size:.68rem;cursor:pointer}.tech-tabs button:last-child{border-right:0}.tech-tabs button.active{color:#eaf4f6;background:rgba(100,139,153,.15);box-shadow:inset 0 -2px #83acb9}.tech-state{display:grid;justify-items:end;color:var(--parchment-faint);font-size:.53rem}.tech-state strong{color:#b8d0d7;font-size:.68rem}.tech-close{width:36px;height:36px;color:var(--parchment-muted);border:1px solid var(--line-strong);background:transparent;font-size:1.35rem;cursor:pointer}.tech-loading{flex:1;display:grid;place-content:center;justify-items:center;gap:12px;color:var(--parchment-muted)}.tech-loading--error>span{width:38px;height:38px;display:grid;place-items:center;color:#df9e86;border:1px solid currentColor}.tech-loading button{padding:8px 12px;color:var(--parchment);border:1px solid var(--line);background:transparent}.tech-content{flex:1;min-height:0;overflow-y:auto;padding:20px clamp(18px,2.3vw,36px) 42px;background:linear-gradient(90deg,rgba(255,255,255,.012) 1px,transparent 1px) 0 0/48px 48px}.overview-statement{display:grid;grid-template-columns:minmax(0,1fr) 220px;align-items:end;gap:28px;padding-bottom:16px;border-bottom:1px solid rgba(100,139,153,.34)}.overview-statement h3{font-size:clamp(1.7rem,3.1vw,3.6rem);font-weight:420;line-height:1.1}.overview-number{display:grid;justify-items:end}.overview-number b{font:300 clamp(3rem,6vw,6.4rem)/.9 var(--font-mono);color:#9bc0ca}.overview-number span{font-family:var(--font-display);font-size:.82rem}.overview-number small{color:var(--parchment-faint);font-size:.56rem}.pipeline{display:grid;grid-template-columns:repeat(5,1fr);gap:18px;margin-top:20px}.pipeline article{position:relative;min-width:0;min-height:150px;padding:15px;border:1px solid var(--line);background:rgba(255,255,255,.014)}.pipeline article>span{color:#83aebb;font-size:.58rem}.pipeline strong{display:block;margin-top:17px;font:350 clamp(1.3rem,2.4vw,2.6rem)/1 var(--font-mono)}.pipeline h4{margin-top:8px;font-size:.78rem}.pipeline p{margin:5px 0;color:var(--parchment-faint);font-size:.58rem;line-height:1.5}.pipeline i{position:absolute;right:-16px;top:48%;z-index:2;color:#779eaa;font-style:normal}.overview-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px}.overview-grid article{padding:13px;border:1px solid var(--line);background:rgba(255,255,255,.012)}.overview-grid article.pending{border-color:rgba(196,71,27,.45)}.overview-grid b{display:block;font:350 1.55rem/1 var(--font-mono)}.overview-grid h4{margin-top:7px;font-size:.72rem}.overview-grid span{color:var(--parchment-faint);font-size:.57rem}.global-boundary{display:grid;grid-template-columns:100px repeat(4,1fr);gap:6px;margin-top:14px}.global-boundary strong,.global-boundary p{margin:0;padding:8px;border:1px dashed var(--line-strong);font-size:.57rem;line-height:1.45}.global-boundary strong{color:#df9e86;font-family:var(--font-display)}.global-boundary span{margin-right:5px;color:var(--accent)}.section-title{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;padding-bottom:16px;border-bottom:1px solid rgba(100,139,153,.34)}.section-title h3{font-size:clamp(1.45rem,2.5vw,2.8rem);font-weight:430}.status-pass,.status-pending{padding:6px 9px;color:#b9d0ae;border:1px solid rgba(122,153,98,.46);font-family:var(--font-mono);font-size:.62rem}.status-pending{color:#e2aa90;border-color:rgba(196,71,27,.48)}.data-grid,.reasoning-grid{display:grid;grid-template-columns:1.1fr .9fr;gap:13px;margin-top:15px}.data-ledger,.version-audit,.gate-panel,.eval-panel{min-width:0;border:1px solid var(--line);background:rgba(255,255,255,.014)}.data-ledger article{display:grid;grid-template-columns:130px minmax(0,1fr) 60px;align-items:center;gap:15px;min-height:91px;padding:12px 15px;border-bottom:1px solid var(--line)}.data-ledger article:last-child{border:0}.data-ledger b{font:350 clamp(1.6rem,3vw,3.2rem)/1 var(--font-mono)}.data-ledger h4{font-size:.8rem}.data-ledger p{margin:4px 0 0;color:var(--parchment-faint);font-size:.58rem}.data-ledger article>span{text-align:right;color:#789dac;font-family:var(--font-mono);font-size:.56rem}.version-audit{padding:17px}.version-audit h3{font-size:1.05rem}.version-hero{display:grid;margin:22px 0;padding:15px;border-left:2px solid #789dac;background:rgba(100,139,153,.055)}.version-hero b{font:350 clamp(2rem,4vw,4.4rem)/1 var(--font-mono)}.version-hero span{margin-top:4px;color:var(--parchment-dim);font-size:.66rem}.version-audit dl{margin:0}.version-audit dl div{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--line);font-size:.67rem}.version-audit dt{color:var(--parchment-faint)}.version-audit dd{margin:0;font-family:var(--font-mono)}.version-audit dd.reject{color:#e3a18b}.version-audit footer,.gate-panel footer,.eval-panel footer{margin-top:13px;padding:9px;color:var(--parchment-faint);border:1px dashed var(--line-strong);font-size:.57rem;line-height:1.5}.gate-panel,.eval-panel{padding:15px}.gate-panel>header{display:flex;justify-content:space-between;gap:12px}.gate-panel h3,.eval-panel h3{font-size:1rem}.gate-score{display:grid;grid-template-columns:auto auto;gap:2px 8px;align-items:end}.gate-score b{font:350 1.5rem/1 var(--font-mono)}.gate-score span{color:var(--parchment-faint);font-size:.52rem}.check-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:5px;margin-top:13px}.check-grid span{padding:6px;color:#b7cda9;border:1px solid rgba(122,153,98,.34);font-size:.56rem}.check-grid i{margin-right:5px;font-style:normal}.fixture-list{display:grid;grid-template-columns:repeat(2,1fr);gap:5px;margin-top:10px}.fixture-list article{display:grid;padding:7px;border:1px solid rgba(196,71,27,.3)}.fixture-list strong{font-size:.59rem}.fixture-list small{margin-top:3px;color:#d99680;font-size:.48rem}.eval-panel>header{display:grid;grid-template-columns:1fr auto;align-items:end}.eval-panel>header p{grid-column:1/-1}.eval-panel>header span{color:#e0a187;font-family:var(--font-mono);font-size:.58rem}.eval-types{display:grid;grid-template-columns:repeat(5,1fr);gap:5px;margin-top:13px}.eval-types article{padding:8px;background:rgba(255,255,255,.025)}.eval-types b{display:block;font:350 1.55rem/1 var(--font-mono)}.eval-types span{color:var(--parchment-faint);font-size:.51rem}.split-proof{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:7px}.split-proof>div{padding:9px;border:1px solid var(--line)}.split-proof b{display:block;font:350 1.25rem/1 var(--font-mono)}.split-proof span{color:var(--parchment-faint);font-size:.51rem}.eval-matrix{display:grid;gap:4px;margin-top:8px}.eval-matrix article{display:flex;justify-content:space-between;gap:10px;padding:6px;border-bottom:1px solid var(--line);font-size:.55rem}.eval-matrix strong{color:#b9cfad}.eval-matrix strong.pending{color:#e0a187}.agent-grid{display:grid;grid-template-columns:1fr 150px 1fr;gap:12px;align-items:stretch;margin-top:15px}.condition{padding:16px;border:1px solid var(--line);background:rgba(255,255,255,.014)}.condition.c1{border-color:rgba(100,139,153,.48)}.condition>header{display:flex;align-items:center;gap:12px}.condition>header>span{width:48px;height:48px;display:grid;place-items:center;border:1px solid #789dac;font-family:var(--font-mono)}.condition h3{font-size:.92rem}.condition-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:20px}.condition-metrics div{padding:10px 5px;border-top:1px solid var(--line)}.condition-metrics b{display:block;font:350 1.3rem/1 var(--font-mono)}.condition-metrics span{color:var(--parchment-faint);font-size:.5rem}.condition footer{display:flex;justify-content:space-between;gap:10px;margin-top:15px;padding-top:10px;border-top:1px dashed var(--line-strong);font-size:.55rem}.condition footer>span{color:#e0a187}.condition footer>span.pass{color:#b9cfad}.condition footer small{color:var(--parchment-faint)}.agent-delta{display:grid;place-content:center;justify-items:center;padding:10px;border:1px solid rgba(176,138,62,.35);background:rgba(176,138,62,.035)}.agent-delta>b{font:350 2.8rem/1 var(--font-mono);color:#d4b66d}.agent-delta>strong{margin-top:9px;font:350 1.2rem/1 var(--font-mono)}.agent-delta>span,.agent-delta>small{color:var(--parchment-faint);font-size:.5rem}.agent-bottom{display:grid;grid-template-columns:.75fr .75fr 1.5fr;gap:10px;margin-top:12px}.agent-bottom>article,.pending-list{padding:12px;border:1px solid var(--line);background:rgba(255,255,255,.012)}.agent-bottom h4{font-size:.74rem}.agent-bottom p{margin:5px 0 0;color:var(--parchment-faint);font-size:.56rem;line-height:1.45}.pending-list>div{display:grid;grid-template-columns:repeat(2,1fr);gap:5px;margin-top:7px}.pending-list article{display:grid;padding:6px;border:1px dashed rgba(196,71,27,.36)}.pending-list article>span{color:#df9e86;font-family:var(--font-mono);font-size:.47rem}.pending-list article strong{font-size:.57rem}.pending-list article p{font-size:.49rem}.artifact-strip{display:flex;flex-wrap:wrap;gap:5px;margin-top:13px;padding-top:10px;border-top:1px solid var(--line)}.artifact-strip>span{display:flex;gap:6px;padding:4px 6px;border:1px solid var(--line);font-size:.48rem}.artifact-strip b{font-weight:500}.artifact-strip i{color:var(--parchment-faint);font-style:normal}
@media(max-width:1050px){.tech-layer{padding:0}.tech-head{grid-template-columns:1fr 38px}.tech-tabs{grid-column:1/-1;grid-row:2;overflow-x:auto}.tech-tabs button{flex:1;white-space:nowrap}.tech-state{display:none}.tech-content{padding:15px 13px 35px}.overview-statement{grid-template-columns:1fr}.overview-number{justify-items:start}.pipeline{grid-template-columns:repeat(2,1fr)}.pipeline i{display:none}.overview-grid{grid-template-columns:repeat(2,1fr)}.global-boundary{grid-template-columns:1fr}.data-grid,.reasoning-grid{grid-template-columns:1fr}.agent-grid{grid-template-columns:1fr}.agent-delta{grid-template-columns:repeat(6,auto);gap:7px}.agent-bottom{grid-template-columns:1fr}.pending-list>div{grid-template-columns:1fr 1fr}}
@media(max-width:680px){.tech-brand h2{font-size:1rem}.tech-brand .kicker{display:none}.pipeline,.overview-grid,.condition-metrics,.eval-types{grid-template-columns:1fr 1fr}.check-grid,.fixture-list{grid-template-columns:1fr 1fr}.data-ledger article{grid-template-columns:90px minmax(0,1fr) 42px}.pending-list>div{grid-template-columns:1fr}}
.agent-delta{gap:8px;justify-items:stretch}.agent-delta>p{text-align:center}.agent-delta>div{display:grid;justify-items:center;gap:2px}.agent-delta>div b{font:350 2.6rem/1 var(--font-mono);color:#d4b66d}.agent-delta>div strong{font:350 1.15rem/1 var(--font-mono)}.agent-delta>div span,.agent-delta>div small{color:var(--parchment-faint);font-size:.5rem}
@media(max-width:1050px){.agent-delta{grid-template-columns:repeat(3,1fr);align-items:center}.agent-delta>p{grid-column:1/-1}}
.tech-purpose{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:12px;margin-bottom:16px;padding:10px 12px;border:1px solid rgba(100,139,153,.38);background:linear-gradient(90deg,rgba(100,139,153,.11),rgba(100,139,153,.025))}.tech-purpose strong{color:#d9edf0;font-family:var(--font-display);font-size:.82rem;white-space:nowrap}.tech-purpose p{margin:0;color:var(--parchment-muted);font-size:.74rem;line-height:1.45}.tech-purpose span{padding:4px 7px;color:#d9a088;border:1px solid rgba(196,71,27,.38);font-size:.66rem;white-space:nowrap}
.kicker{font-size:.68rem}.tech-tabs button{font-size:.78rem}.tech-state{font-size:.6rem}.tech-state strong{font-size:.74rem}.overview-number span{font-size:.9rem}.overview-number small{font-size:.65rem}.pipeline article>span{font-size:.66rem}.pipeline h4{font-size:.88rem}.pipeline p{font-size:.68rem}.overview-grid h4{font-size:.82rem}.overview-grid span{font-size:.66rem}.global-boundary strong,.global-boundary p{font-size:.65rem}.status-pass,.status-pending{font-size:.7rem}.data-ledger h4{font-size:.9rem}.data-ledger p{font-size:.68rem;line-height:1.45}.data-ledger article>span{font-size:.64rem}.version-audit h3{font-size:1.12rem}.version-hero span{font-size:.74rem}.version-audit dl div{font-size:.75rem}.version-audit footer,.gate-panel footer,.eval-panel footer{font-size:.66rem}.gate-panel h3,.eval-panel h3{font-size:1.08rem}.gate-score span{font-size:.61rem}.check-grid span{font-size:.65rem}.fixture-list strong{font-size:.66rem}.fixture-list small{font-size:.55rem}.eval-panel>header span{font-size:.66rem}.eval-types span,.split-proof span{font-size:.59rem}.eval-matrix article{font-size:.63rem}.condition h3{font-size:1rem}.condition-metrics span{font-size:.59rem}.condition footer{font-size:.63rem}.agent-delta>span,.agent-delta>small{font-size:.58rem}.agent-bottom h4{font-size:.82rem}.agent-bottom p{font-size:.64rem}.pending-list article>span{font-size:.55rem}.pending-list article strong{font-size:.65rem}.pending-list article p{font-size:.57rem}.artifact-strip>span{font-size:.55rem}
@media(max-width:1050px){.tech-purpose{grid-template-columns:1fr}.tech-purpose span{justify-self:start;white-space:normal}}
.pipeline{grid-template-columns:repeat(6,1fr);gap:14px}
.rag-experiment{display:grid;grid-template-columns:minmax(280px,1fr) 1.5fr;gap:18px;margin-top:15px;padding:15px 17px;border:1px solid rgba(100,139,153,.46);background:linear-gradient(100deg,rgba(100,139,153,.11),rgba(176,138,62,.035))}.rag-experiment h3{font-size:1rem}.rag-experiment>div>span{display:block;margin-top:6px;color:var(--parchment-faint);font-size:.64rem}.rag-experiment dl{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin:0}.rag-experiment dl div{padding:9px;border-left:1px solid rgba(100,139,153,.32)}.rag-experiment dt{color:var(--parchment-faint);font-size:.58rem}.rag-experiment dd{margin:5px 0 0;font:350 1.25rem/1 var(--font-mono)}.rag-experiment footer{grid-column:1/-1;color:#d9a088;font-size:.62rem}
@media(max-width:1050px){.pipeline{grid-template-columns:repeat(2,1fr)}.rag-experiment{grid-template-columns:1fr}.rag-experiment dl{grid-template-columns:repeat(2,1fr)}}
</style>
