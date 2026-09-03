from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..teaching import law_corpus
from ..hybrid_rag.runtime import get_hybrid_rag_retriever


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTENT_DIR = REPO_ROOT / "adaptive_service" / "data"
LAW_MANIFEST_PATH = REPO_ROOT / "backend" / "legal_corpus" / "processed" / "law_corpus_manifest.json"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_id(prefix: str, value: str, length: int = 20) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:length].upper()
    return f"{prefix}_{digest}"


def _evidence_id(record: dict[str, Any]) -> str:
    return _stable_id(
        "EVID",
        f"{record.get('document_id')}|{record.get('source_bundle_sha256')}",
    )


def _normalize(value: Any) -> str:
    return re.sub(r"[\s　《》“”。，；：、（）()]+", "", str(value or "")).lower()


def _ngrams(value: str, size: int = 2) -> set[str]:
    text = _normalize(value)
    if len(text) < size:
        return {text} if text else set()
    return {text[index : index + size] for index in range(len(text) - size + 1)}


def _lexical_overlap(left: str, right: str) -> float:
    a, b = _ngrams(left), _ngrams(right)
    if not a or not b:
        return 0.0
    return round(len(a & b) / len(a), 4)


class KnowledgeService:
    def __init__(
        self,
        *,
        content_dir: Path = CONTENT_DIR,
        law_manifest_path: Path = LAW_MANIFEST_PATH,
        hybrid_retriever: Any = ...,
    ) -> None:
        self.content_dir = Path(content_dir)
        self.cards = _read_jsonl(self.content_dir / "knowledge_cards.jsonl")
        self.tasks = _read_jsonl(self.content_dir / "task_items.jsonl")
        self.evidence_catalog = _read_jsonl(self.content_dir / "evidence_catalog.jsonl")
        self.manifest = json.loads((self.content_dir / "manifest.json").read_text(encoding="utf-8"))
        self.law_manifest = json.loads(Path(law_manifest_path).read_text(encoding="utf-8"))
        self.card_by_id = {row["knowledge_id"]: row for row in self.cards}
        self.task_by_id = {row["task_id"]: row for row in self.tasks}
        self.evidence_by_id = {row["evidence_id"]: row for row in self.evidence_catalog}
        self.evidence_by_article = {
            (row["source_title"], row["article_ref"]): row
            for row in self.evidence_catalog
        }
        self.hybrid_retriever = (
            get_hybrid_rag_retriever() if hybrid_retriever is ... else hybrid_retriever
        )

    @staticmethod
    def _canonical_formal_title(value: Any) -> str | None:
        title = str(value or "")
        if "刑事诉讼法" in title:
            return "中华人民共和国刑事诉讼法"
        if "刑法" in title:
            return "中华人民共和国刑法"
        return None

    def _hybrid_results(
        self,
        query: str,
        top_k: int,
        collections: list[str],
    ) -> tuple[list[dict[str, Any]], str, bool]:
        if self.hybrid_retriever is None:
            return [], "词法检索", False
        rows: list[dict[str, Any]] = []
        methods: set[str] = set()
        abstained = False
        for collection in collections:
            try:
                result = self.hybrid_retriever.search(
                    query,
                    collection=collection,
                    top_k=max(5, top_k),
                )
            except Exception:
                methods.add("词法检索（语义服务暂不可用）")
                continue
            abstained = abstained or bool(result.get("abstained"))
            rows.extend(result.get("results") or [])
            if result.get("stages", {}).get("dense") == "fallback_to_bm25f":
                methods.add("词法检索（语义服务暂不可用）")
            elif result.get("stages", {}).get("reranker") == "fallback_to_rrf":
                methods.add("词法与语义融合（重排服务暂不可用）")
            else:
                methods.add("词法与语义融合检索")
        return (
            [] if abstained else rows,
            "；".join(sorted(methods)) or "词法检索",
            abstained,
        )

    @staticmethod
    def public_task(task: dict[str, Any]) -> dict[str, Any]:
        hidden = {"answer_private", "rationale_private", "misconceptions_private"}
        row = {key: value for key, value in task.items() if key not in hidden}
        row["answer_included"] = False
        return row

    def catalog(self) -> dict[str, Any]:
        return {
            "schema_version": "criminal-law-course-catalog-v1",
            "domain": "刑法",
            "review_status": "pilot_teacher_approved",
            "knowledge_cards": self.cards,
            "counts": {
                "knowledge_cards": len(self.cards),
                "task_items": len(self.tasks),
                "evidence_items": len(self.evidence_catalog),
            },
            "content_manifest_sha256": _sha256(self.content_dir / "manifest.json"),
            "law_corpus_manifest_sha256": _sha256(LAW_MANIFEST_PATH),
            "limits": list(self.manifest.get("limits") or []),
        }

    def get_public_task(self, task_id: str) -> dict[str, Any] | None:
        task = self.task_by_id.get(str(task_id or "").strip())
        return self.public_task(task) if task else None

    def _knowledge_graph_context(
        self,
        query: str,
        requested_ids: list[str] | None,
    ) -> tuple[list[str], dict[str, Any]]:
        selected: list[str] = []
        for knowledge_id in requested_ids or []:
            if knowledge_id in self.card_by_id and knowledge_id not in selected:
                selected.append(knowledge_id)
        if not selected:
            query_normalized = _normalize(query)
            candidates = []
            for card in self.cards:
                name = str(card.get("canonical_name") or "")
                exact_name = bool(name and _normalize(name) in query_normalized)
                exact_articles = sum(
                    _normalize(article) in query_normalized
                    for article in card.get("law_article_refs") or []
                )
                description = " ".join(
                    [
                        name,
                        str(card.get("chapter") or ""),
                        str(card.get("learning_objective") or ""),
                        str(card.get("summary") or ""),
                    ]
                )
                overlap = _lexical_overlap(query, description)
                score = (1.0 if exact_name else 0.0) + exact_articles * 0.6 + overlap
                if score >= 0.22:
                    candidates.append((score, str(card["knowledge_id"])))
            selected = [identifier for _, identifier in sorted(candidates, reverse=True)[:2]]
        selected_cards = [self.card_by_id[identifier] for identifier in selected]
        nodes = []
        expansion_terms: list[str] = []
        for card in selected_cards:
            prerequisites = [
                self.card_by_id[identifier]["canonical_name"]
                for identifier in card.get("prerequisite_ids") or []
                if identifier in self.card_by_id
            ]
            expansion_terms.extend(
                [str(card["canonical_name"]), *[str(value) for value in card.get("law_article_refs") or []], *prerequisites]
            )
            nodes.append(
                {
                    "name": card["canonical_name"],
                    "chapter": card.get("chapter") or "",
                    "prerequisites": prerequisites,
                    "law_article_refs": list(card.get("law_article_refs") or []),
                    "standard_evidence_count": len(card.get("standard_evidence_ids") or []),
                }
            )
        return selected, {
            "matched": bool(nodes),
            "nodes": nodes,
            "query_expansion_terms": list(dict.fromkeys(expansion_terms)),
            "fusion_method": "知识节点与先修关系扩展检索；Evidence结果反向支撑诊断解释和学习路径",
            "boundary": "图谱约束学习目标和先修顺序，RAG提供可引用材料；两者均不单独证明掌握或法律结论。",
        }

    def evidence_for_article(
        self,
        title: str,
        article_ref: str,
    ) -> dict[str, Any] | None:
        article = law_corpus.resolve_article(title, article_ref)
        if article is None:
            return None
        return self._evidence_from_hit({**article, "score": 1.0})

    def _evidence_from_hit(self, hit: dict[str, Any]) -> dict[str, Any]:
        existing = self.evidence_by_article.get(
            (str(hit.get("source_title") or ""), str(hit.get("article_ref") or ""))
        )
        if existing:
            row = dict(existing)
        else:
            row = {
                "schema_version": "evidence-pack-item-v1",
                "evidence_id": _evidence_id(hit),
                "source_type": "法律条文",
                "document_id": hit.get("document_id"),
                "title": f"{hit.get('source_title', '')}{hit.get('article_ref', '')}",
                "source_title": hit.get("source_title"),
                "article_ref": hit.get("article_ref"),
                "quote": hit.get("content"),
                "authority_level": "法律",
                "effective_from": hit.get("version_as_of"),
                "effective_to": None,
                "effective_status": hit.get("effective_status"),
                "source_url": hit.get("source_url"),
                "source_url_scope": hit.get("source_url_scope"),
                "source_snapshot_id": hit.get("source_snapshot_id"),
                "source_bundle_sha256": hit.get("source_bundle_sha256"),
                "risk_flags": [
                    "official_item_url_not_preserved",
                    "recheck_validity_before_classroom_term",
                ],
            }
        row["relevance"] = float(hit.get("score") or 0.0)
        row["match_reasons"] = ["bm25_retrieval"]
        row.setdefault("allowed_usage", ["normative_rule"])
        row.setdefault("document_number", "")
        row.setdefault("parent_context", None)
        row.setdefault("issuing_authority", "全国人民代表大会或其常务委员会")
        row.setdefault("promulgated_date", "")
        row.setdefault("effective_date", str(row.get("effective_from") or ""))
        row.setdefault("expiry_date", str(row.get("effective_to") or ""))
        row.setdefault("version", str(row.get("source_snapshot_id") or row.get("effective_from") or ""))
        row.setdefault("official_source_url", str(row.get("source_url") or ""))
        row.setdefault("verification_method", "governed_core_manifest")
        row.setdefault("verification_status", "legacy_governed_core")
        row.setdefault("source_use", "刑法课程核心规范，可作为规范依据使用。")
        return row

    def _evidence_from_hybrid(self, candidate: dict[str, Any]) -> dict[str, Any]:
        source_type = str(candidate.get("source_type") or "")
        title = str(candidate.get("source_title") or candidate.get("title") or "")
        article_ref = str(candidate.get("article_ref") or "")
        if source_type == "law" and article_ref:
            formal_title = self._canonical_formal_title(title)
            article = law_corpus.resolve_article(formal_title, article_ref) if formal_title else None
            if article is not None:
                row = self._evidence_from_hit({**article, "score": 1.0})
                row["match_reasons"] = ["hybrid_retrieval", "core_norm_projection"]
                return row
        quote = str(candidate.get("quote") or "")
        content_hash = str(candidate.get("content_sha256") or "")
        if not re.fullmatch(r"[a-f0-9]{64}", content_hash):
            content_hash = hashlib.sha256(quote.encode("utf-8")).hexdigest()
        source_url = str(candidate.get("official_source_url") or candidate.get("source_url") or "")
        scores = candidate.get("scores") if isinstance(candidate.get("scores"), dict) else {}
        relevance = float(scores.get("reranker") or scores.get("rrf") or scores.get("dense_cosine") or 0.0)
        return {
            "schema_version": "evidence-pack-item-v1",
            "evidence_id": _stable_id("EVID", str(candidate.get("retrieval_id") or content_hash)),
            "source_type": source_type or "learning_resource",
            "document_id": str(candidate.get("document_id") or candidate.get("retrieval_id") or "resource"),
            "title": f"{title}{article_ref}",
            "source_title": title,
            "article_ref": article_ref,
            "quote": quote,
            "authority_level": str(candidate.get("authority_level") or "学习资源"),
            "effective_from": str(candidate.get("effective_date") or ""),
            "effective_to": str(candidate.get("expiry_date") or "") or None,
            "effective_status": str(candidate.get("effective_status") or "unresolved"),
            "source_url": source_url,
            "source_url_scope": "official_detail" if source_url else "official_archive_no_direct_detail",
            "source_snapshot_id": str(candidate.get("source_snapshot_id") or candidate.get("version") or "hybrid-rag-v1"),
            "source_bundle_sha256": content_hash,
            "risk_flags": list(candidate.get("risk_flags") or []),
            "relevance": relevance,
            "match_reasons": ["hybrid_retrieval"],
            "allowed_usage": list(candidate.get("allowed_usage") or ["learning_resource"]),
            "document_number": str(candidate.get("document_number") or ""),
            "parent_context": candidate.get("parent_context"),
            "issuing_authority": str(candidate.get("issuing_authority") or ""),
            "promulgated_date": str(candidate.get("promulgated_date") or ""),
            "effective_date": str(candidate.get("effective_date") or ""),
            "expiry_date": str(candidate.get("expiry_date") or ""),
            "version": str(candidate.get("version") or ""),
            "official_source_url": source_url,
            "verification_method": str(candidate.get("verification_method") or "local_index_metadata"),
            "verification_status": str(candidate.get("verification_status") or "unresolved"),
            "source_use": str(candidate.get("source_use") or "请结合来源身份和效力提示使用。"),
        }

    def search(
        self,
        *,
        query: str,
        task_type: str = "课程检索",
        top_k: int = 5,
        knowledge_ids: list[str] | None = None,
        key_judgments: list[str] | None = None,
        collections: list[str] | None = None,
    ) -> dict[str, Any]:
        query_text = str(query or "").strip()
        if not query_text:
            raise ValueError("query is required")
        top_k = max(1, min(int(top_k), 10))
        selected_collections = list(
            dict.fromkeys(collections or ["legal_authority"])
        )
        allowed_collections = {"legal_authority", "textbook_explanation", "question_public"}
        if not selected_collections or any(value not in allowed_collections for value in selected_collections):
            raise ValueError("collections contains an unsupported retrieval layer")
        graph_ids, knowledge_context = self._knowledge_graph_context(
            query_text, knowledge_ids
        )
        expansion = " ".join(knowledge_context["query_expansion_terms"])
        retrieval_query = f"{query_text} {expansion}".strip() if expansion else query_text
        hybrid_candidates, retrieval_method, explicit_abstention = self._hybrid_results(
            retrieval_query, top_k, selected_collections
        )
        hits = [] if explicit_abstention or "legal_authority" not in selected_collections else law_corpus.search_law(
            query_text, top_k=top_k, title="中华人民共和国刑法"
        )
        evidence_rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate in hybrid_candidates:
            row = self._evidence_from_hybrid(candidate)
            if row["evidence_id"] in seen:
                continue
            seen.add(row["evidence_id"])
            evidence_rows.append(row)
        for hit in hits:
            row = self._evidence_from_hit(hit)
            if row["evidence_id"] in seen:
                continue
            seen.add(row["evidence_id"])
            evidence_rows.append(row)

        valid_knowledge_ids = []
        for knowledge_id in graph_ids:
            card = self.card_by_id.get(str(knowledge_id))
            if not card:
                continue
            valid_knowledge_ids.append(str(knowledge_id))
            for evidence_id in card.get("standard_evidence_ids") or []:
                if evidence_id in seen or evidence_id not in self.evidence_by_id:
                    continue
                row = dict(self.evidence_by_id[evidence_id])
                row = self._evidence_from_hit({
                    **row,
                    "source_title": row.get("source_title"),
                    "article_ref": row.get("article_ref"),
                    "content": row.get("quote"),
                    "score": 1.0,
                })
                row["relevance"] = 1.0
                row["match_reasons"] = ["knowledge_card_standard"]
                evidence_rows.append(row)
                seen.add(evidence_id)

        maximum = max((float(row.get("relevance") or 0.0) for row in evidence_rows), default=1.0)
        if maximum > 1.0:
            for row in evidence_rows:
                row["relevance"] = round(float(row.get("relevance") or 0.0) / maximum, 4)
        evidence_rows.sort(key=lambda row: float(row.get("relevance") or 0.0), reverse=True)
        evidence_rows = evidence_rows[: max(top_k, len(seen))]

        coverage: dict[str, Any] = {}
        judgments = [value.strip() for value in key_judgments or [] if value.strip()]
        if not judgments:
            judgments = [query_text]
        for judgment in judgments:
            claim_hits = [] if explicit_abstention or "legal_authority" not in selected_collections else law_corpus.search_law(
                judgment, top_k=min(3, top_k), title="中华人民共和国刑法"
            )
            ids = [self._evidence_from_hit(hit)["evidence_id"] for hit in claim_hits]
            coverage[judgment] = {
                "evidence_ids": ids,
                "status": "candidate_requires_semantic_audit" if ids else "insufficient_evidence",
            }

        return {
            "schema_version": "evidence-pack-v1",
            "query_id": _stable_id("Q", f"{task_type}|{query_text}|{valid_knowledge_ids}"),
            "task_type": str(task_type or "课程检索"),
            "query": query_text,
            "knowledge_ids": valid_knowledge_ids,
            "evidences": evidence_rows,
            "coverage": coverage,
            "source_snapshot": {
                "download_snapshot_date": self.law_manifest.get("download_snapshot_date"),
                "criminal_law_version": self.law_manifest["documents"]["xingfa"]["version_as_of"],
                "manifest_sha256": _sha256(LAW_MANIFEST_PATH),
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "warnings": [
                "retrieval relevance and coverage are candidates, not semantic entailment judgments",
                "recheck legal validity before each real classroom term",
                f"retrieval method: {retrieval_method}",
            ],
            "usage_policy": {
                "hierarchy": ["law", "administrative_regulation", "judicial_interpretation", "judicial_normative_document", "guiding_case", "typical_case", "textbook_explanation", "learning_resource"],
                "normative_rule": ["law", "administrative_regulation"],
                "judicial_application": ["judicial_interpretation", "judicial_normative_document"],
                "case_reference": ["guiding_case", "typical_case"],
                "teaching_explanation": ["textbook_explanation"],
                "learning_resource": ["learning_resource"],
                "rule": "教材、案例和题目不得覆盖法律、行政法规或司法解释；unresolved来源必须显示效力尚未完全核实。",
            },
            "knowledge_context": knowledge_context,
        }

    def audit_citations(self, citations: list[dict[str, Any]]) -> dict[str, Any]:
        rows = []
        counts = {"valid": 0, "invalid_title": 0, "invalid_article": 0, "source_not_found": 0}
        for index, citation in enumerate(citations):
            title = str(citation.get("title") or "").strip()
            article_ref = str(citation.get("article_ref") or "").strip()
            requested_type = str(citation.get("source_type") or "").strip()
            hybrid_matches = (
                self.hybrid_retriever.resolve_source(
                    title=title,
                    article_ref=article_ref,
                    source_type=requested_type,
                    top_k=3,
                )
                if self.hybrid_retriever is not None
                else []
            )
            if hybrid_matches and not (
                self._canonical_formal_title(title) and article_ref
            ):
                candidate = hybrid_matches[0]
                evidence = self._evidence_from_hybrid(candidate)
                expected_quote = str(citation.get("quote") or "").strip()
                quote_status = "not_requested"
                risk_flags = []
                if expected_quote:
                    quote_status = (
                        "exact_fragment"
                        if _normalize(expected_quote) in _normalize(evidence.get("quote"))
                        else "quote_mismatch"
                    )
                    if quote_status == "quote_mismatch":
                        risk_flags.append("quote_mismatch")
                claim = str(citation.get("claim") or "").strip()
                overlap = _lexical_overlap(claim, str(evidence.get("quote") or "")) if claim else None
                usage = list(evidence.get("allowed_usage") or [])
                if claim and not set(usage) & {"normative_rule", "judicial_application"}:
                    risk_flags.append("source_cannot_prove_normative_conclusion")
                if evidence.get("effective_status") == "unresolved":
                    risk_flags.append("effect_not_fully_verified")
                counts["valid"] += 1
                rows.append(
                    {
                        "index": index,
                        "status": "valid",
                        "title": evidence.get("source_title") or title,
                        "article_ref": evidence.get("article_ref") or article_ref,
                        "quote_status": quote_status,
                        "claim_support_status": (
                            "candidate_requires_semantic_audit" if claim else "not_requested"
                        ),
                        "lexical_overlap": overlap,
                        "evidence": evidence,
                        "risk_flags": list(dict.fromkeys(risk_flags)),
                    }
                )
                continue
            result = law_corpus.verify_citation(title, article_ref)
            status = result["status"]
            risk_flags: list[str] = []
            evidence = None
            quote_status = "not_requested"
            claim_status = "not_requested"
            overlap = None
            if status == "valid":
                article = law_corpus.resolve_article(title, article_ref) or {}
                evidence = self._evidence_from_hit({**article, "score": 1.0})
                expected_quote = str(citation.get("quote") or "").strip()
                if expected_quote:
                    quote_status = (
                        "exact_fragment"
                        if _normalize(expected_quote) in _normalize(article.get("content"))
                        else "quote_mismatch"
                    )
                    if quote_status == "quote_mismatch":
                        risk_flags.append("quote_mismatch")
                claim = str(citation.get("claim") or "").strip()
                if claim:
                    overlap = _lexical_overlap(claim, str(article.get("content") or ""))
                    claim_status = (
                        "lexical_candidate_requires_semantic_audit"
                        if overlap >= 0.08
                        else "insufficient_lexical_overlap_requires_review"
                    )
                    risk_flags.append("semantic_entailment_not_evaluated")
            else:
                if hybrid_matches:
                    evidence = self._evidence_from_hybrid(hybrid_matches[0])
                    status = "valid"
                    quote = str(citation.get("quote") or "").strip()
                    quote_status = (
                        "exact_fragment"
                        if not quote or _normalize(quote) in _normalize(evidence.get("quote"))
                        else "quote_mismatch"
                    )
                    risk_flags.extend(evidence.get("risk_flags") or [])
                else:
                    risk_flags.append(status)
            counts[status] = counts.get(status, 0) + 1
            rows.append(
                {
                    "index": index,
                    "status": status,
                    "title": (evidence or {}).get("source_title") or result.get("title") or title,
                    "article_ref": (evidence or {}).get("article_ref") or article_ref,
                    "quote_status": quote_status,
                    "claim_support_status": claim_status,
                    "lexical_overlap": overlap,
                    "evidence": evidence,
                    "risk_flags": risk_flags,
                }
            )
        return {
            "schema_version": "citation-audit-result-v1",
            "items": rows,
            "summary": {**counts, "total": len(rows)},
            "semantic_boundary": (
                "exact existence and quote checks are deterministic; lexical overlap is not legal entailment"
            ),
        }


@lru_cache(maxsize=1)
def get_knowledge_service() -> KnowledgeService:
    return KnowledgeService()


__all__ = ["KnowledgeService", "get_knowledge_service"]
