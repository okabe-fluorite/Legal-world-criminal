"""BM25F + Dense -> RRF -> Reranker Hybrid RAG retrieval."""

from __future__ import annotations

import json
import re
from collections import OrderedDict, defaultdict
from pathlib import Path
from threading import Lock
from typing import Any, Sequence

import numpy as np

from .lexical_index import lexical_search
from .siliconflow import SiliconFlowClient


_ARTICLE_RE = re.compile(r"第[一二三四五六七八九十百千万零〇两\d]+条(?:之[一二三四五六七八九十百千零〇两\d]+)?")
_VERSION_SUFFIX_RE = re.compile(r"(?:\(|（)[^()（）]*(?:年|版|修订|修正)[^()（）]*(?:\)|）)")
_QUOTED_TITLE_RE = re.compile(r"《([^》]{2,100})》")


def _normalize(value: Any) -> str:
    return re.sub(r"[\s　《》“”。，；：、（）()]+", "", str(value or "")).lower()


def _title_aliases(value: Any) -> set[str]:
    raw = str(value or "")
    without_version = _VERSION_SUFFIX_RE.sub("", raw)
    aliases = {_normalize(raw), _normalize(without_version)}
    aliases.update(alias.replace("中华人民共和国", "") for alias in list(aliases))
    return {alias for alias in aliases if alias}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _rrf(rankings: Sequence[Sequence[int]], *, k: int = 60) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, document_index in enumerate(ranking, 1):
            scores[document_index] = scores.get(document_index, 0.0) + 1.0 / (k + rank)
    return scores


def rerank_instruction(collection: str) -> str:
    if collection == "textbook_explanation":
        return "优先返回与法学概念、教材章节和小节直接匹配的解释材料。"
    if collection == "question_public":
        return "优先返回考查知识点、事实结构和题型最相近的公开练习。"
    return "优先返回与法律问题直接相关、法名条号或裁判规则匹配的材料。"


class HybridCollection:
    def __init__(
        self,
        index_dir: Path,
        *,
        case_parent_path: Path | None = None,
        verification_path: Path | None = None,
    ) -> None:
        self.index_dir = Path(index_dir)
        self.manifest = json.loads((self.index_dir / "manifest.json").read_text(encoding="utf-8"))
        self.records = _load_jsonl(self.index_dir / self.manifest["metadata_file"])
        self.vectors = np.load(self.index_dir / self.manifest["vector_file"], mmap_mode="r")
        self.lexical_path = self.index_dir / self.manifest["lexical_file"]
        if self.vectors.shape != (len(self.records), int(self.manifest["vector_dim"])):
            raise ValueError(f"index shape mismatch: {self.index_dir}")
        self.parents: dict[str, dict[str, Any]] = {}
        if case_parent_path and case_parent_path.is_file():
            self.parents = {str(row["parent_id"]): row for row in _load_jsonl(case_parent_path)}
        self.verification: dict[str, dict[str, Any]] = {}
        if verification_path and verification_path.is_file():
            self.verification = {
                str(row["document_id"]): row for row in _load_jsonl(verification_path)
            }
        self.indices_by_title: dict[str, list[int]] = defaultdict(list)
        for index, record in enumerate(self.records):
            for alias in _title_aliases(record.get("title") or record.get("subject") or ""):
                self.indices_by_title[alias].append(index)

    def lexical(self, query: str, limit: int) -> list[tuple[int, float]]:
        return lexical_search(self.lexical_path, query, limit=limit)

    def dense(self, query_vector: Sequence[float], limit: int) -> list[tuple[int, float]]:
        vector = np.asarray(query_vector, dtype=np.float32)
        if vector.shape != (self.vectors.shape[1],) or not np.isfinite(vector).all():
            raise ValueError("query vector does not match collection index")
        norm = float(np.linalg.norm(vector))
        if norm <= 0.0:
            raise ValueError("query vector has zero norm")
        scores = np.asarray(self.vectors @ (vector / norm), dtype=np.float32)
        count = min(max(1, int(limit)), scores.shape[0])
        if count == scores.shape[0]:
            indices = np.argsort(scores)[::-1]
        else:
            indices = np.argpartition(scores, -count)[-count:]
            indices = indices[np.argsort(scores[indices])[::-1]]
        return [(int(index), float(scores[index])) for index in indices]

    def exact_article_indices(self, query: str) -> list[int]:
        query_normalized = _normalize(query)
        article = _ARTICLE_RE.search(query_normalized)
        if not article:
            return []
        matches: list[int] = []
        for index, record in enumerate(self.records):
            article_ref = _normalize(record.get("article_ref"))
            titles = _title_aliases(record.get("title"))
            if article.group(0) != article_ref:
                continue
            if any(title in query_normalized for title in titles):
                matches.append(index)
        priority = {
            "formal_evidence": 0,
            "approved": 0,
            "pilot_teacher_approved": 1,
            "candidate_requires_legal_review": 2,
            "isolated_reference": 3,
            "isolated_outside_scope": 4,
        }
        matches.sort(
            key=lambda index: (
                priority.get(str(self.records[index].get("governance_status") or ""), 5),
                str(self.records[index].get("effective_status") or "") in {"unknown_requires_review", "edition_unknown"},
                index,
            )
        )
        return matches

    def project(self, document_index: int, scores: dict[str, Any]) -> dict[str, Any]:
        record = self.records[document_index]
        parent = self.parents.get(str(record.get("parent_id") or ""))
        verification = self.verification.get(str(record.get("document_id") or ""), {})
        source_type = str(
            verification.get("evidence_source_type")
            or record.get("source_type")
            or ("learning_resource" if self.manifest.get("collection") == "question_public" else "")
        )
        if source_type == "textbook_explanation":
            allowed_usage = ["teaching_explanation"]
            source_use = "教材解释可用于课堂说明，不得覆盖法律、行政法规或司法解释。"
        elif source_type in {"question", "learning_resource"}:
            allowed_usage = ["learning_resource"]
            source_use = "仅用于相似题、练习推荐和诊断任务，不参与法律结论证明。"
        else:
            allowed_usage = list(verification.get("allowed_usage") or [])
            source_use = str(verification.get("source_use") or "效力尚未完全核实，使用时请结合来源和时效提示。")
        effective_status = str(
            verification.get("effective_status")
            or record.get("effective_status")
            or (
                "edition_unknown"
                if source_type == "textbook_explanation"
                else "not_applicable_learning_resource"
                if source_type in {"question", "learning_resource"}
                else "unresolved"
            )
        )
        obsolete_flags = {
            "candidate_not_formal_authority",
            "effective_status_requires_review",
            "case_personal_information_review_required",
            "third_party_case_redistribution_review_required",
            "source_terms_and_exact_item_provenance_require_review",
            "unreviewed_inventory",
            "isolated_reference",
            "isolated_outside_scope",
            "no_case_personal_data_indicated_by_collection",
        }
        risk_flags = [
            str(value)
            for value in record.get("risk_flags") or []
            if str(value) not in obsolete_flags
        ]
        if effective_status == "unresolved":
            risk_flags.append("effect_not_fully_verified")
        result = {
            "retrieval_id": record.get("retrieval_id"),
            "document_id": record.get("document_id") or record.get("retrieval_id"),
            "parent_id": record.get("parent_id") or "",
            "source_type": source_type,
            "authority_level": verification.get("authority_level") or record.get("authority_level") or "学习资源",
            "allowed_usage": allowed_usage,
            "title": record.get("title") or record.get("subject") or "",
            "source_title": record.get("title") or record.get("subject") or "",
            "document_number": verification.get("document_number") or "",
            "article_ref": record.get("article_ref") or "",
            "section_title": record.get("section_title") or "",
            "quote": record.get("content") or record.get("retrieval_text") or "",
            "issuing_authority": verification.get("issuing_authority") or record.get("issuing_authority") or "",
            "promulgated_date": verification.get("promulgated_date") or record.get("promulgated_date") or "",
            "effective_date": verification.get("effective_date") or record.get("effective_date") or "",
            "revision_date": verification.get("revision_date") or "",
            "expiry_date": verification.get("expiry_date") or "",
            "effective_status": effective_status,
            "version": verification.get("version") or record.get("source_snapshot_id") or "",
            "official_source_url": verification.get("official_source_url") or record.get("source_url") or "",
            "source_url": verification.get("official_source_url") or record.get("source_url") or "",
            "verification_method": verification.get("verification_method") or "local_index_metadata",
            "verification_status": verification.get("verification_status") or "unresolved",
            "source_use": source_use,
            "risk_flags": list(dict.fromkeys(risk_flags)),
            "source_snapshot_id": record.get("source_snapshot_id") or "",
            "content_sha256": record.get("content_sha256") or "",
            "scores": scores,
        }
        if parent:
            result["parent_context"] = {
                "title": parent.get("title") or "",
                "section_type": parent.get("section_type") or "",
                "section_title": parent.get("section_title") or "",
                "content": parent.get("content") or "",
            }
        return result


class HybridRagRetriever:
    def __init__(
        self,
        *,
        index_root: Path,
        corpus_root: Path,
        client: SiliconFlowClient,
        verification_path: Path | None = None,
        cache_size: int = 128,
    ) -> None:
        self.index_root = Path(index_root)
        self.corpus_root = Path(corpus_root)
        self.client = client
        self.verification_path = Path(verification_path) if verification_path else None
        self.cache_size = max(1, cache_size)
        self._collections: dict[str, HybridCollection] = {}
        self._embedding_cache: OrderedDict[str, list[float]] = OrderedDict()
        self._cache_lock = Lock()

    def collection(self, name: str) -> HybridCollection:
        if name not in {"legal_authority", "textbook_explanation", "question_public"}:
            raise ValueError(f"unsupported Hybrid RAG collection: {name}")
        if name not in self._collections:
            self._collections[name] = HybridCollection(
                self.index_root / name,
                case_parent_path=(self.corpus_root / "case_parents.jsonl") if name == "legal_authority" else None,
                verification_path=self.verification_path if name == "legal_authority" else None,
            )
        return self._collections[name]

    def _embed_query(self, query: str) -> list[float]:
        with self._cache_lock:
            cached = self._embedding_cache.get(query)
            if cached is not None:
                self._embedding_cache.move_to_end(query)
                return list(cached)
        result = self.client.embed([query], dimensions=1024)
        vector = result.vectors[0]
        with self._cache_lock:
            self._embedding_cache[query] = list(vector)
            self._embedding_cache.move_to_end(query)
            while len(self._embedding_cache) > self.cache_size:
                self._embedding_cache.popitem(last=False)
        return vector

    def resolve_source(
        self,
        *,
        title: str,
        article_ref: str = "",
        source_type: str = "",
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Deterministically resolve a cited source without model/API calls."""

        title_aliases = _title_aliases(title)
        normalized_article = _normalize(article_ref)
        if not title_aliases:
            return []
        if source_type in {"textbook_explanation"}:
            collections = ["textbook_explanation"]
        elif source_type in {"learning_resource", "question"}:
            collections = ["question_public"]
        else:
            collections = ["legal_authority", "textbook_explanation", "question_public"]
        matches: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for collection_name in collections:
            collection = self.collection(collection_name)
            candidate_indices = sorted(
                {
                    index
                    for alias in title_aliases
                    for index in collection.indices_by_title.get(alias, [])
                }
            )
            for index in candidate_indices:
                record = collection.records[index]
                record_title = record.get("title") or record.get("subject") or ""
                aliases = _title_aliases(record_title)
                if not (title_aliases & aliases):
                    continue
                if normalized_article and _normalize(record.get("article_ref")) != normalized_article:
                    continue
                projected = collection.project(
                    index,
                    {
                        "bm25f": 0.0,
                        "dense_cosine": 0.0,
                        "rrf": 0.0,
                        "reranker": None,
                        "exact_article_protected": bool(normalized_article),
                    },
                )
                if source_type:
                    requested = source_type.lower()
                    actual = str(projected.get("source_type") or "").lower()
                    aliases_by_type = {
                        "司法解释": {"judicial_interpretation", "judicial_normative_document"},
                        "案例": {"guiding_case", "typical_case"},
                        "教材": {"textbook_explanation"},
                        "题目": {"learning_resource", "question"},
                    }
                    allowed = aliases_by_type.get(source_type, {requested})
                    if actual not in allowed:
                        continue
                key = (str(projected.get("document_id") or ""), str(projected.get("parent_id") or normalized_article))
                if key in seen:
                    continue
                seen.add(key)
                matches.append(projected)
                if len(matches) >= max(1, int(top_k)):
                    return matches
        return matches

    def search(
        self,
        query: str,
        *,
        collection: str = "legal_authority",
        top_k: int = 5,
        lexical_k: int = 50,
        dense_k: int = 50,
        rerank_k: int = 20,
    ) -> dict[str, Any]:
        query_text = str(query or "").strip()
        if not query_text:
            raise ValueError("query is required")
        top_k = min(20, max(1, int(top_k)))
        index = self.collection(collection)
        lexical_hits = index.lexical(query_text, lexical_k)
        stages = {"bm25f": "succeeded", "dense": "succeeded", "reranker": "succeeded"}
        errors: list[dict[str, str]] = []
        dense_hits: list[tuple[int, float]] = []
        try:
            dense_hits = index.dense(self._embed_query(query_text), dense_k)
        except Exception as exc:
            stages["dense"] = "fallback_to_bm25f"
            stages["reranker"] = "skipped"
            errors.append({"stage": "dense", "type": type(exc).__name__, "message": str(exc)})
        rrf_scores = _rrf(
            [
                [document_index for document_index, _ in lexical_hits],
                [document_index for document_index, _ in dense_hits],
            ]
        )
        exact_indices = index.exact_article_indices(query_text)
        explicit_missing_article = bool(
            collection == "legal_authority"
            and _ARTICLE_RE.search(_normalize(query_text))
            and _QUOTED_TITLE_RE.search(query_text)
            and not exact_indices
        )
        if explicit_missing_article:
            return {
                "schema_version": "hybrid-rag-search-result-v1",
                "query": query_text,
                "collection": collection,
                "stages": {**stages, "reranker": "skipped_by_exact_reference_check"},
                "fallback_used": False,
                "abstained": True,
                "abstention_reason": "explicit_title_article_not_found",
                "results": [],
                "errors": errors,
                "notice": "未找到与指定法名和条号同时匹配的资料，请核对名称、条号或版本。",
            }
        for position, document_index in enumerate(exact_indices):
            rrf_scores[document_index] = rrf_scores.get(document_index, 0.0) + 1.0 - position * 0.0001
        fused = sorted(rrf_scores, key=lambda document_index: rrf_scores[document_index], reverse=True)
        candidates = fused[: max(top_k, rerank_k)]
        rerank_scores: dict[int, float] = {}
        if dense_hits and candidates:
            try:
                reranked = self.client.rerank(
                    query_text,
                    [str(index.records[item].get("retrieval_text") or index.records[item].get("content") or "") for item in candidates],
                    top_n=len(candidates),
                    return_documents=False,
                    instruction=rerank_instruction(collection),
                )
                rerank_scores = {candidates[item.index]: item.relevance_score for item in reranked.items}
                candidates = [candidates[item.index] for item in reranked.items]
            except Exception as exc:
                stages["reranker"] = "fallback_to_rrf"
                errors.append({"stage": "reranker", "type": type(exc).__name__, "message": str(exc)})
        exact_present = [item for item in exact_indices if item in rrf_scores]
        candidates = exact_present + [item for item in candidates if item not in exact_present]
        lexical_scores = dict(lexical_hits)
        dense_scores = dict(dense_hits)
        results = [
            index.project(
                document_index,
                {
                    "bm25f": round(lexical_scores.get(document_index, 0.0), 6),
                    "dense_cosine": round(dense_scores.get(document_index, 0.0), 6),
                    "rrf": round(rrf_scores.get(document_index, 0.0), 6),
                    "reranker": round(rerank_scores.get(document_index, 0.0), 6) if rerank_scores else None,
                    "exact_article_protected": document_index in exact_indices,
                },
            )
            for document_index in candidates[:top_k]
        ]
        return {
            "schema_version": "hybrid-rag-search-result-v1",
            "query": query_text,
            "collection": collection,
            "stages": stages,
            "fallback_used": any(value.startswith("fallback") for value in stages.values()),
            "abstained": False,
            "results": results,
            "errors": errors,
            "notice": "检索结果用于提供候选资料；正式法律结论仍需核对来源、时效和适用关系。",
        }


def public_search_result(value: dict[str, Any]) -> dict[str, Any]:
    """Remove internal identifiers, raw ranks and machine status codes for product UI."""

    stages = value.get("stages") if isinstance(value.get("stages"), dict) else {}
    fallback = bool(value.get("fallback_used"))
    if stages.get("dense") == "fallback_to_bm25f":
        method = "词法检索（语义服务暂不可用）"
    elif stages.get("reranker") == "fallback_to_rrf":
        method = "词法与语义融合（重排服务暂不可用）"
    else:
        method = "词法与语义融合检索"
    rows = []
    for result in value.get("results") or []:
        rows.append(
            {
                "source_type": result.get("source_type") or "资料",
                "authority_level": result.get("authority_level") or "层级待复核",
                "allowed_usage": result.get("allowed_usage") or [],
                "title": result.get("title") or "",
                "document_number": result.get("document_number") or "",
                "article_ref": result.get("article_ref") or "",
                "section_title": result.get("section_title") or "",
                "quote": result.get("quote") or "",
                "parent_context": result.get("parent_context"),
                "issuing_authority": result.get("issuing_authority") or "",
                "promulgated_date": result.get("promulgated_date") or "",
                "effective_date": result.get("effective_date") or "",
                "expiry_date": result.get("expiry_date") or "",
                "effective_status": result.get("effective_status") or "",
                "version": result.get("version") or "",
                "official_source_url": result.get("official_source_url") or "",
                "source_url": result.get("official_source_url") or result.get("source_url") or "",
                "verification_method": result.get("verification_method") or "",
                "verification_status": result.get("verification_status") or "",
                "source_use": result.get("source_use") or "使用前请复核",
                "risk_flags": result.get("risk_flags") or [],
            }
        )
    return {
        "schema_version": "hybrid-rag-public-search-v1",
        "query": value.get("query") or "",
        "collection": value.get("collection") or "",
        "retrieval_method": method,
        "fallback_used": fallback,
        "abstained": bool(value.get("abstained")),
        "results": rows,
        "notice": value.get("notice") or "检索结果用于提供候选资料。",
    }


__all__ = [
    "HybridCollection",
    "HybridRagRetriever",
    "public_search_result",
    "rerank_instruction",
]
