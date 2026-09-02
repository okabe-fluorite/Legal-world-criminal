<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import type { EvidenceReference } from "../lib/types";
import { shortEvidenceText } from "../lib/evidence";

const props = withDefaults(defineProps<{
  references: EvidenceReference[];
  compact?: boolean;
}>(), { compact: false });

const hovered = ref<EvidenceReference | null>(null);
const selected = ref<EvidenceReference | null>(null);
const tooltipPosition = ref({ left: 0, top: 0, above: false });
const uniqueReferences = computed(() => {
  const seen = new Set<string>();
  return props.references.filter((row) => {
    if (!row?.id || seen.has(row.id)) return false;
    seen.add(row.id);
    return true;
  });
});

type SourceKind = "law" | "regulation" | "judicial" | "case" | "course" | "resource";

function sourceKind(row: EvidenceReference): SourceKind {
  const value = `${row.source_type} ${row.id}`.toLowerCase();
  if (value.includes("case") || value.includes("案例") || value.includes("裁判")) return "case";
  if (value.includes("judicial") || value.includes("司法解释") || value.includes("司法规范")) return "judicial";
  if (value.includes("regulation") || value.includes("行政法规")) return "regulation";
  if (value.includes("textbook") || value.includes("card") || value.includes("教材") || value.includes("课程") || value.includes("knowledge")) return "course";
  if (value.includes("resource") || value.includes("question") || value.includes("题目") || value.includes("练习")) return "resource";
  return "law";
}

function kindLabel(row: EvidenceReference): string {
  return ({ law: "法", regulation: "规", judicial: "司", case: "案", course: "教", resource: "练" })[sourceKind(row)];
}

function typeLabel(row: EvidenceReference): string {
  return ({ law: "法律", regulation: "行政法规", judicial: "司法解释 / 司法文件", case: "指导性 / 典型案例", course: "教材解释", resource: "公开学习资源" })[sourceKind(row)];
}

function statusLabel(row: EvidenceReference): string {
  const status = String(row.effective_status || "");
  if (status === "verified_current" || status === "effective_as_of_download_snapshot") return "已核实当前版本";
  if (status === "verified_historical") return "已核实发布记录";
  if (status === "superseded") return "已有后续版本";
  if (status === "repealed") return "已废止";
  if (status === "unresolved") return "效力尚未完全核实";
  if (status === "edition_unknown") return "教材版次待补充";
  if (status === "not_applicable_learning_resource") return "学习资源不适用法律效力状态";
  return status || "效力信息待补充";
}

function usageLabel(value: string): string {
  return ({
    normative_rule: "规范依据",
    judicial_application: "司法适用依据",
    case_reference: "裁判参考 / 事实示例",
    teaching_explanation: "课堂与学理解释",
    learning_resource: "相似题 / 练习推荐",
  } as Record<string, string>)[value] ?? value;
}

function versionLabel(row: EvidenceReference): string {
  const value = String(row.version || row.effective_status || "").trim();
  if (!value) return "版本信息待补充";
  if (/^[a-f0-9]{40,}$/i.test(value)) return "资料版本已记录";
  if (value.startsWith("npc-flk-")) return "国家法律法规数据库资料版本";
  if (value === "以冻结版本为准") return "以当前课程资料版本为准";
  return value;
}

function citationTitle(row: EvidenceReference): string {
  return `${row.title}${row.article_ref ? ` ${row.article_ref}` : ""}`;
}

function riskLabel(value: string): string {
  return ({
    official_item_url_not_preserved: "原始详情页待补充",
    recheck_validity_before_classroom_term: "开课前请复核时效",
    official_item_url_not_preserved_in_download: "原始详情页待补充",
    candidate_requires_semantic_audit: "适用关系需进一步判断",
    teacher_review_required: "建议教师复核",
    case_relevance_not_legal_entailment: "相关案例不代表结论必然成立",
    edition_unknown: "教材版本信息待补充",
    textbook_does_not_override_current_law: "教材解释不能替代现行法",
    effect_not_fully_verified: "效力尚未完全核实",
    source_cannot_prove_normative_conclusion: "该来源不能单独证明规范结论",
  } as Record<string, string>)[value] ?? value.replaceAll("_", " ");
}

function showTooltip(row: EvidenceReference, event: Event): void {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
  const above = rect.bottom + 190 > window.innerHeight;
  tooltipPosition.value = {
    left: Math.min(Math.max(12, rect.left - 18), Math.max(12, window.innerWidth - 350)),
    top: above ? rect.top - 10 : rect.bottom + 9,
    above,
  };
  hovered.value = row;
}

function hideTooltip(): void {
  hovered.value = null;
}

function openDrawer(row: EvidenceReference): void {
  hovered.value = null;
  selected.value = row;
}

function closeDrawer(): void {
  selected.value = null;
}

async function copyCitation(row: EvidenceReference): Promise<void> {
  const text = `${citationTitle(row)}：${row.quote}`;
  try {
    await navigator.clipboard?.writeText(text);
  } catch {
    // Clipboard permission is optional; the full citation remains visible.
  }
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape" && selected.value) closeDrawer();
}

onMounted(() => window.addEventListener("keydown", handleKeydown));
onUnmounted(() => window.removeEventListener("keydown", handleKeydown));
</script>

<template>
  <span v-if="uniqueReferences.length" :class="['evidence-citations', { compact }]" aria-label="正文引用">
    <button
      v-for="(row, index) in uniqueReferences"
      :key="row.id"
      type="button"
      :class="`citation-mark citation-mark--${sourceKind(row)}`"
      :aria-label="`引用${index + 1}：${citationTitle(row)}，点击查看完整证据`"
      @mouseenter="showTooltip(row, $event)"
      @mouseleave="hideTooltip"
      @focus="showTooltip(row, $event)"
      @blur="hideTooltip"
      @click="openDrawer(row)"
    >{{ index + 1 }}</button>
  </span>

  <Teleport to="body">
    <Transition name="evidence-tip">
      <aside
        v-if="hovered"
        class="evidence-tooltip"
        :class="{ above: tooltipPosition.above }"
        :style="{ left: `${tooltipPosition.left}px`, top: `${tooltipPosition.top}px` }"
        role="tooltip"
      >
        <header><span>{{ kindLabel(hovered) }}</span><strong>{{ citationTitle(hovered) }}</strong></header>
        <p>{{ shortEvidenceText(hovered.quote) }}</p>
        <footer>{{ hovered.authority || "受治理来源" }} · 点击展开完整证据</footer>
      </aside>
    </Transition>

    <Transition name="evidence-drawer">
      <div v-if="selected" class="evidence-drawer-backdrop" @click.self="closeDrawer">
        <aside class="evidence-drawer" role="dialog" aria-modal="true" aria-labelledby="evidence-drawer-title">
          <header class="drawer-head">
            <div><p>来源详情 · 可查看原文</p><h2 id="evidence-drawer-title">{{ citationTitle(selected) }}</h2></div>
            <button type="button" aria-label="关闭完整证据" @click="closeDrawer">×</button>
          </header>
          <div class="drawer-scroll">
            <section class="drawer-identity">
              <span :class="`kind kind--${sourceKind(selected)}`">{{ kindLabel(selected) }}</span>
              <dl>
                <div><dt>类型</dt><dd>{{ typeLabel(selected) }}</dd></div>
                <div><dt>效力层级</dt><dd>{{ selected.authority || "待复核" }}</dd></div>
                <div><dt>版本</dt><dd>{{ versionLabel(selected) }}</dd></div>
              </dl>
            </section>
            <section class="drawer-quote">
              <p>FULL GOVERNED EXCERPT</p>
              <blockquote>{{ selected.quote || "当前证据未返回可公开全文片段。" }}</blockquote>
            </section>
            <section class="drawer-provenance">
              <h3>来源与适用信息</h3>
              <dl>
                <div><dt>效力状态</dt><dd>{{ statusLabel(selected) }}</dd></div>
                <div v-if="selected.document_number"><dt>文号</dt><dd>{{ selected.document_number }}</dd></div>
                <div v-if="selected.issuing_authority"><dt>发布机关</dt><dd>{{ selected.issuing_authority }}</dd></div>
                <div v-if="selected.promulgated_date"><dt>公布 / 印发</dt><dd>{{ selected.promulgated_date }}</dd></div>
                <div v-if="selected.effective_date"><dt>施行时间</dt><dd>{{ selected.effective_date }}</dd></div>
                <div><dt>来源</dt><dd>{{ selected.source_url ? "可打开官方来源" : "国家法律资料本地归档" }}</dd></div>
              </dl>
            </section>
            <section v-if="selected.allowed_usage.length" class="drawer-risks drawer-usage">
              <h3>允许用途</h3><span v-for="usage in selected.allowed_usage" :key="usage">{{ usageLabel(usage) }}</span>
            </section>
            <section v-if="selected.parent_context?.content" class="drawer-parent">
              <p>CASE PARENT CONTEXT</p><h3>{{ selected.parent_context.section_title || selected.parent_context.title || "完整语义父段" }}</h3><blockquote>{{ selected.parent_context.content }}</blockquote>
            </section>
            <section v-if="selected.risk_flags.length" class="drawer-risks">
              <h3>使用提示</h3><span v-for="risk in selected.risk_flags" :key="risk">{{ riskLabel(risk) }}</span>
            </section>
          </div>
          <footer class="drawer-actions">
            <button type="button" @click="copyCitation(selected)">复制引用</button>
            <a v-if="selected.source_url" :href="selected.source_url" target="_blank" rel="noopener noreferrer">打开官方来源 ↗</a>
            <span>{{ selected.source_use || "检索相关不等于法律蕴含；请结合来源身份和效力层级使用。" }}</span>
          </footer>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.evidence-citations{display:inline-flex;align-items:center;gap:3px;margin-left:.38em;vertical-align:.15em}.citation-mark{width:1.42em;height:1.42em;padding:0;color:#d6bf83;border:1px solid rgba(176,138,62,.58);background:rgba(176,138,62,.09);font:700 .68em/1 var(--font-mono);cursor:pointer;transition:transform .16s ease,color .16s ease,background .16s ease}.citation-mark:hover,.citation-mark:focus-visible{color:#fff;background:#916e28;outline:none;transform:translateY(-2px)}.citation-mark--case{color:#9fc1cc;border-color:rgba(100,139,153,.62);background:rgba(100,139,153,.1)}.citation-mark--case:hover,.citation-mark--case:focus-visible{background:#426f80}.citation-mark--course{color:#b9cba9;border-color:rgba(122,153,98,.58);background:rgba(122,153,98,.09)}.citation-mark--course:hover,.citation-mark--course:focus-visible{background:#5f774f}.compact .citation-mark{width:1.25em;height:1.25em;font-size:.62em}
.evidence-tooltip{position:fixed;z-index:4000;width:min(330px,calc(100vw - 24px));padding:12px 13px;color:#ede5d6;border:1px solid rgba(176,138,62,.55);background:linear-gradient(145deg,#211d14,#0d100e);box-shadow:0 18px 48px #000b;pointer-events:none}.evidence-tooltip.above{transform:translateY(-100%)}.evidence-tooltip header{display:grid;grid-template-columns:27px 1fr;align-items:center;gap:8px}.evidence-tooltip header span{width:26px;height:26px;display:grid;place-items:center;color:#d6bf83;border:1px solid currentColor;font-family:var(--font-display)}.evidence-tooltip strong{font-size:.72rem}.evidence-tooltip p{margin:8px 0;color:#bfb5a4;font-size:.68rem;line-height:1.55}.evidence-tooltip footer{padding-top:7px;color:#81796a;border-top:1px solid rgba(255,255,255,.08);font-size:.57rem}.evidence-tip-enter-active,.evidence-tip-leave-active{transition:opacity .14s ease,transform .14s ease}.evidence-tip-enter-from,.evidence-tip-leave-to{opacity:0;transform:translateY(4px)}.evidence-tip-enter-from.above,.evidence-tip-leave-to.above{transform:translateY(calc(-100% + 4px))}
.evidence-drawer-backdrop{position:fixed;inset:0;z-index:3990;background:rgba(1,2,2,.94);backdrop-filter:blur(6px);isolation:isolate}.evidence-drawer{position:absolute;top:0;right:0;width:min(520px,100vw);height:100%;display:flex;flex-direction:column;color:#e9e0cf;border-left:1px solid rgba(176,138,62,.58);background:#0b0e0c;box-shadow:-32px 0 90px #000c;isolation:isolate}.drawer-head{display:grid;grid-template-columns:1fr 38px;gap:16px;align-items:start;padding:22px 22px 17px;border-bottom:1px solid rgba(176,138,62,.32)}.drawer-head p{margin:0 0 5px;color:#ad9157;font:600 .58rem var(--font-mono);letter-spacing:.12em}.drawer-head h2{margin:0;font-size:1.16rem;line-height:1.4}.drawer-head button{width:36px;height:36px;color:#bdb2a0;border:1px solid rgba(255,255,255,.15);background:transparent;font-size:1.3rem;cursor:pointer}.drawer-scroll{flex:1;overflow-y:auto;padding:18px 22px 36px;background:repeating-linear-gradient(0deg,transparent 0 31px,rgba(255,255,255,.025) 31px 32px)}.drawer-identity{display:grid;grid-template-columns:52px 1fr;gap:14px;align-items:start}.drawer-identity .kind{width:50px;height:50px;display:grid;place-items:center;color:#d6bf83;border:1px solid currentColor;font:700 1.2rem var(--font-display);transform:rotate(-2deg)}.drawer-identity .kind--case{color:#9fc1cc}.drawer-identity .kind--course{color:#b9cba9}.drawer-identity dl,.drawer-provenance dl{margin:0}.drawer-identity dl div,.drawer-provenance dl div{display:grid;grid-template-columns:92px minmax(0,1fr);gap:8px;padding:5px 0;border-bottom:1px solid rgba(255,255,255,.07);font-size:.67rem}.drawer-identity dt,.drawer-provenance dt{color:#777264}.drawer-identity dd,.drawer-provenance dd{margin:0;overflow-wrap:anywhere}.drawer-quote{margin-top:22px}.drawer-quote>p{margin:0 0 8px;color:#ad9157;font:600 .59rem var(--font-mono);letter-spacing:.13em}.drawer-quote blockquote{margin:0;padding:16px 17px;color:#ded5c5;border-left:2px solid #b08a3e;background:rgba(176,138,62,.055);font-family:var(--font-display);font-size:.86rem;line-height:1.85;white-space:pre-wrap}.drawer-provenance,.drawer-risks{margin-top:22px}.drawer-provenance h3,.drawer-risks h3{margin:0 0 8px;font-size:.82rem}.drawer-risks{display:flex;flex-wrap:wrap;gap:6px}.drawer-risks h3{flex-basis:100%}.drawer-risks span{padding:4px 6px;color:#d9a38e;border:1px solid rgba(196,71,27,.35);font-size:.59rem}.drawer-actions{display:flex;align-items:center;flex-wrap:wrap;gap:8px;padding:14px 22px;border-top:1px solid rgba(176,138,62,.3);background:#0b0d0c}.drawer-actions button,.drawer-actions a{padding:8px 10px;color:#ded4c0;border:1px solid rgba(176,138,62,.45);background:rgba(176,138,62,.07);font-family:var(--font-display);font-size:.68rem;text-decoration:none;cursor:pointer}.drawer-actions a{color:#b8d0da;border-color:rgba(100,139,153,.45)}.drawer-actions span{flex-basis:100%;color:#706b60;font-size:.56rem}.evidence-drawer-enter-active,.evidence-drawer-leave-active{transition:opacity .22s ease}.evidence-drawer-enter-active .evidence-drawer,.evidence-drawer-leave-active .evidence-drawer{transition:transform .22s cubic-bezier(.2,.8,.2,1)}.evidence-drawer-enter-from,.evidence-drawer-leave-to{opacity:0}.evidence-drawer-enter-from .evidence-drawer,.evidence-drawer-leave-to .evidence-drawer{transform:translateX(100%)}
@media(max-width:620px){.evidence-drawer{width:100%}.drawer-head{padding:16px}.drawer-scroll{padding:15px 16px 30px}.drawer-actions{padding:12px 16px}.evidence-tooltip{display:none}}
.evidence-tooltip{z-index:3980!important}
.evidence-drawer-backdrop{background:rgba(1,2,2,.94)!important;backdrop-filter:blur(6px)!important;isolation:isolate}
.evidence-drawer{background:#0b0e0c!important;isolation:isolate}
.citation-mark--regulation{color:#d8c89a;border-color:rgba(190,157,75,.58);background:rgba(190,157,75,.09)}.citation-mark--regulation:hover,.citation-mark--regulation:focus-visible{background:#88702f}.citation-mark--judicial{color:#b2a8d8;border-color:rgba(132,116,181,.6);background:rgba(132,116,181,.1)}.citation-mark--judicial:hover,.citation-mark--judicial:focus-visible{background:#66558e}.citation-mark--resource{color:#d1ab96;border-color:rgba(179,115,80,.58);background:rgba(179,115,80,.09)}.citation-mark--resource:hover,.citation-mark--resource:focus-visible{background:#86533a}.drawer-identity .kind--regulation{color:#d8c89a}.drawer-identity .kind--judicial{color:#b2a8d8}.drawer-identity .kind--resource{color:#d1ab96}.drawer-parent{margin-top:22px}.drawer-parent>p{margin:0 0 5px;color:#83aebb;font:600 .59rem var(--font-mono);letter-spacing:.12em}.drawer-parent h3{margin:0 0 8px;font-size:.8rem}.drawer-parent blockquote{margin:0;padding:13px 15px;color:#cbd5d7;border-left:2px solid #648b99;background:rgba(100,139,153,.065);font-family:var(--font-display);font-size:.78rem;line-height:1.75;white-space:pre-wrap}.drawer-usage span{color:#b9cba9;border-color:rgba(122,153,98,.38)}
</style>
