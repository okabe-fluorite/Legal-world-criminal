from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..teaching import law_corpus


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
        return row

    def search(
        self,
        *,
        query: str,
        task_type: str = "课程检索",
        top_k: int = 5,
        knowledge_ids: list[str] | None = None,
        key_judgments: list[str] | None = None,
    ) -> dict[str, Any]:
        query_text = str(query or "").strip()
        if not query_text:
            raise ValueError("query is required")
        top_k = max(1, min(int(top_k), 10))
        hits = law_corpus.search_law(query_text, top_k=top_k, title="中华人民共和国刑法")
        evidence_rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for hit in hits:
            row = self._evidence_from_hit(hit)
            seen.add(row["evidence_id"])
            evidence_rows.append(row)

        valid_knowledge_ids = []
        for knowledge_id in knowledge_ids or []:
            card = self.card_by_id.get(str(knowledge_id))
            if not card:
                continue
            valid_knowledge_ids.append(str(knowledge_id))
            for evidence_id in card.get("standard_evidence_ids") or []:
                if evidence_id in seen or evidence_id not in self.evidence_by_id:
                    continue
                row = dict(self.evidence_by_id[evidence_id])
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
            claim_hits = law_corpus.search_law(
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
            ],
        }

    def audit_citations(self, citations: list[dict[str, Any]]) -> dict[str, Any]:
        rows = []
        counts = {"valid": 0, "invalid_title": 0, "invalid_article": 0}
        for index, citation in enumerate(citations):
            title = str(citation.get("title") or "").strip()
            article_ref = str(citation.get("article_ref") or "").strip()
            result = law_corpus.verify_citation(title, article_ref)
            status = result["status"]
            counts[status] = counts.get(status, 0) + 1
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
                risk_flags.append(status)
            rows.append(
                {
                    "index": index,
                    "status": status,
                    "title": result.get("title") or title,
                    "article_ref": article_ref,
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
