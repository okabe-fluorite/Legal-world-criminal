"""BM25F + Dense -> RRF -> Reranker Hybrid RAG retrieval."""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Any, Sequence

import numpy as np

from .lexical_index import lexical_search
from .siliconflow import SiliconFlowClient


_ARTICLE_RE = re.compile(r"第[一二三四五六七八九十百千万零〇两\d]+条(?:之[一二三四五六七八九十百千零〇两\d]+)?")
_VERSION_SUFFIX_RE = re.compile(r"(?:\(|（)[^()（）]*(?:年|版|修订|修正)[^()（）]*(?:\)|）)")


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


class HybridCollection:
    def __init__(self, index_dir: Path, *, case_parent_path: Path | None = None) -> None:
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
        governance = str(record.get("governance_status") or "")
        if governance in {"pilot_teacher_approved", "approved", "formal_evidence"}:
            source_use = "可作为已审核来源使用"
        elif governance == "candidate_requires_legal_review":
            source_use = "候选来源，使用前需法学教师复核"
        else:
            source_use = "参考资料，不能单独作为正式结论依据"
        result = {
            "retrieval_id": record.get("retrieval_id"),
            "source_type": record.get("source_type") or ("question" if self.manifest.get("collection") == "question_public" else ""),
            "authority_level": record.get("authority_level"),
            "title": record.get("title") or record.get("subject") or "",
            "article_ref": record.get("article_ref") or "",
            "section_title": record.get("section_title") or "",
            "quote": record.get("content") or record.get("retrieval_text") or "",
            "effective_date": record.get("effective_date") or "",
            "effective_status": record.get("effective_status") or "",
            "source_url": record.get("source_url") or "",
            "source_use": source_use,
            "governance_status": governance,
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
        cache_size: int = 128,
    ) -> None:
        self.index_root = Path(index_root)
        self.corpus_root = Path(corpus_root)
        self.client = client
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
                    instruction="优先返回与法律问题直接相关、法名条号或裁判规则匹配的材料。",
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
            "results": results,
            "errors": errors,
            "notice": "检索结果用于提供候选资料；正式法律结论仍需核对来源、时效和适用关系。",
        }


__all__ = ["HybridCollection", "HybridRagRetriever"]
