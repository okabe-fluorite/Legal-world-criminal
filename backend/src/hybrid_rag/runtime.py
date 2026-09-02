"""Feature-flagged Hybrid RAG runtime factory with graceful local fallback."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from .retriever import HybridRagRetriever
from .siliconflow import SiliconFlowClient


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INDEX_ROOT = REPO_ROOT / ".codex-artifacts" / "hybrid-rag-index-v1"
DEFAULT_CORPUS_ROOT = REPO_ROOT / ".codex-artifacts" / "hybrid-rag-corpus-v1"
TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}


def hybrid_rag_enabled() -> bool:
    return str(os.environ.get("SIMLAW_HYBRID_RAG_ENABLED") or "").strip().lower() in TRUE_VALUES


@lru_cache(maxsize=1)
def get_hybrid_rag_retriever() -> HybridRagRetriever | None:
    if not hybrid_rag_enabled():
        return None
    index_root = Path(os.environ.get("SIMLAW_HYBRID_RAG_INDEX_DIR") or DEFAULT_INDEX_ROOT)
    corpus_root = Path(os.environ.get("SIMLAW_HYBRID_RAG_CORPUS_DIR") or DEFAULT_CORPUS_ROOT)
    required = [
        index_root / "legal_authority" / "manifest.json",
        index_root / "textbook_explanation" / "manifest.json",
        index_root / "question_public" / "manifest.json",
        corpus_root / "case_parents.jsonl",
    ]
    if not all(path.is_file() for path in required):
        return None
    key = os.environ.get("LAW_EMBEDDING_API_KEY") or os.environ.get("LAW_RERANKER_API_KEY") or ""
    embedding_url = os.environ.get("LAW_EMBEDDING_API_BASE_URL") or ""
    reranker_url = os.environ.get("LAW_RERANKER_API_BASE_URL") or ""
    embedding_model = os.environ.get("LAW_EMBEDDING_MODEL") or "Qwen/Qwen3-Embedding-8B"
    reranker_model = os.environ.get("LAW_RERANKER_MODEL") or "Qwen/Qwen3-Reranker-8B"
    if not key or not embedding_url or not reranker_url:
        return None
    client = SiliconFlowClient(
        api_key=key,
        embedding_url=embedding_url,
        embedding_model=embedding_model,
        reranker_url=reranker_url,
        reranker_model=reranker_model,
    )
    return HybridRagRetriever(index_root=index_root, corpus_root=corpus_root, client=client)


def clear_hybrid_rag_runtime_cache() -> None:
    get_hybrid_rag_retriever.cache_clear()


__all__ = [
    "clear_hybrid_rag_runtime_cache",
    "get_hybrid_rag_retriever",
    "hybrid_rag_enabled",
]
