"""Small, strict SiliconFlow clients for Hybrid RAG embedding and reranking."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Sequence
from urllib.parse import urlsplit, urlunsplit

import requests


RETRYABLE_STATUS_CODES = {429, 503, 504}
OFFICIAL_API_HOSTS = ("api.siliconflow.cn", "api.siliconflow.com")


class SiliconFlowError(RuntimeError):
    """Safe API error which never includes credentials or response bodies."""

    def __init__(self, message: str, *, status_code: int | None = None, host: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.host = host


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    host: str
    latency_ms: float
    prompt_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class RerankItem:
    index: int
    relevance_score: float
    document: str | None


@dataclass(frozen=True)
class RerankResult:
    items: list[RerankItem]
    model: str
    host: str
    latency_ms: float
    input_tokens: int
    output_tokens: int


def normalize_endpoint(value: str, resource: str) -> str:
    """Accept an API root or a full resource URL and return one full endpoint."""

    resource_name = resource.strip("/")
    raw = str(value or "").strip().strip('"').strip("'").rstrip("/")
    if not raw:
        raise ValueError(f"missing {resource_name} endpoint")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError(f"invalid {resource_name} endpoint")
    path = parts.path.rstrip("/")
    for known in ("embeddings", "rerank"):
        if path.lower().endswith(f"/{known}"):
            path = path[: -(len(known) + 1)]
            break
    if not path:
        path = "/v1"
    elif not path.lower().endswith("/v1"):
        path = f"{path}/v1"
    path = f"{path}/{resource_name}"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def endpoint_candidates(configured: str, resource: str) -> list[str]:
    """Try the configured route first, then SiliconFlow's official public hosts."""

    result = [normalize_endpoint(configured, resource)]
    for host in OFFICIAL_API_HOSTS:
        candidate = f"https://{host}/v1/{resource.strip('/')}"
        if candidate not in result:
            result.append(candidate)
    return result


class SiliconFlowClient:
    def __init__(
        self,
        *,
        api_key: str,
        embedding_url: str,
        embedding_model: str,
        reranker_url: str,
        reranker_model: str,
        timeout_seconds: float = 90.0,
        max_attempts: int = 2,
        post: Callable[..., Any] = requests.post,
    ) -> None:
        if not str(api_key or "").strip():
            raise ValueError("SiliconFlow API key is not configured")
        self.api_key = api_key.strip().strip('"').strip("'")
        self.embedding_urls = endpoint_candidates(embedding_url, "embeddings")
        self.embedding_model = embedding_model.strip().strip('"').strip("'")
        self.reranker_urls = endpoint_candidates(reranker_url, "rerank")
        self.reranker_model = reranker_model.strip().strip('"').strip("'")
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, int(max_attempts))
        self.post = post

    def _post_json(self, urls: Sequence[str], payload: dict[str, Any]) -> tuple[dict[str, Any], str, float]:
        last_error: Exception | None = None
        for url in urls:
            host = urlsplit(url).netloc
            for attempt in range(1, self.max_attempts + 1):
                started = time.perf_counter()
                try:
                    response = self.post(
                        url,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                        timeout=self.timeout_seconds,
                    )
                except requests.RequestException as exc:
                    last_error = SiliconFlowError("SiliconFlow connection failed", host=host)
                    break
                latency_ms = (time.perf_counter() - started) * 1000.0
                status_code = int(getattr(response, "status_code", 0) or 0)
                if 200 <= status_code < 300:
                    try:
                        body = response.json()
                    except (TypeError, ValueError) as exc:
                        raise SiliconFlowError("SiliconFlow returned invalid JSON", status_code=status_code, host=host) from exc
                    if not isinstance(body, dict):
                        raise SiliconFlowError("SiliconFlow returned a non-object response", status_code=status_code, host=host)
                    return body, host, latency_ms
                last_error = SiliconFlowError(
                    f"SiliconFlow request failed with HTTP {status_code}",
                    status_code=status_code,
                    host=host,
                )
                if status_code == 404:
                    break
                if status_code in RETRYABLE_STATUS_CODES and attempt < self.max_attempts:
                    time.sleep(0.4 * attempt)
                    continue
                raise last_error
        if isinstance(last_error, Exception):
            raise last_error
        raise SiliconFlowError("SiliconFlow request failed before a response was received")

    def embed(self, texts: Sequence[str], *, dimensions: int = 1024) -> EmbeddingResult:
        cleaned = [str(text).strip() for text in texts]
        if not cleaned or any(not text for text in cleaned):
            raise ValueError("embedding inputs must be non-empty strings")
        payload, host, latency_ms = self._post_json(
            self.embedding_urls,
            {
                "model": self.embedding_model,
                "input": cleaned,
                "encoding_format": "float",
                "dimensions": int(dimensions),
            },
        )
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(cleaned):
            raise SiliconFlowError("embedding response count does not match input count", host=host)
        ordered: list[list[float] | None] = [None] * len(cleaned)
        for position, item in enumerate(data):
            if not isinstance(item, dict):
                raise SiliconFlowError("embedding response contains an invalid item", host=host)
            index = item.get("index", position)
            vector = item.get("embedding")
            if not isinstance(index, int) or not 0 <= index < len(cleaned) or ordered[index] is not None:
                raise SiliconFlowError("embedding response indices are invalid", host=host)
            if not isinstance(vector, list) or len(vector) != dimensions:
                raise SiliconFlowError("embedding vector dimension is invalid", host=host)
            converted = [float(value) for value in vector]
            if not all(math.isfinite(value) for value in converted):
                raise SiliconFlowError("embedding vector contains a non-finite value", host=host)
            ordered[index] = converted
        if any(vector is None for vector in ordered):
            raise SiliconFlowError("embedding response ordering is incomplete", host=host)
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        return EmbeddingResult(
            vectors=[vector for vector in ordered if vector is not None],
            model=str(payload.get("model") or self.embedding_model),
            host=host,
            latency_ms=latency_ms,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
        )

    def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int | None = None,
        return_documents: bool = False,
        instruction: str | None = None,
    ) -> RerankResult:
        query_text = str(query or "").strip()
        cleaned = [str(document).strip() for document in documents]
        if not query_text or not cleaned or any(not document for document in cleaned):
            raise ValueError("rerank query and documents must be non-empty")
        limit = min(len(cleaned), int(top_n or len(cleaned)))
        request_payload: dict[str, Any] = {
            "model": self.reranker_model,
            "query": query_text,
            "documents": cleaned,
            "top_n": limit,
            "return_documents": bool(return_documents),
        }
        if instruction and instruction.strip():
            request_payload["instruction"] = instruction.strip()
        payload, host, latency_ms = self._post_json(
            self.reranker_urls,
            request_payload,
        )
        raw_results = payload.get("results")
        if not isinstance(raw_results, list) or len(raw_results) > limit:
            raise SiliconFlowError("reranker response has an invalid result list", host=host)
        seen: set[int] = set()
        items: list[RerankItem] = []
        for item in raw_results:
            if not isinstance(item, dict):
                raise SiliconFlowError("reranker response contains an invalid item", host=host)
            index = item.get("index")
            score = item.get("relevance_score")
            if not isinstance(index, int) or not 0 <= index < len(cleaned) or index in seen:
                raise SiliconFlowError("reranker response index is invalid", host=host)
            score_value = float(score)
            if not math.isfinite(score_value):
                raise SiliconFlowError("reranker response score is non-finite", host=host)
            document_value = item.get("document")
            if isinstance(document_value, dict):
                document_value = document_value.get("text")
            seen.add(index)
            items.append(
                RerankItem(
                    index=index,
                    relevance_score=score_value,
                    document=str(document_value) if document_value is not None else None,
                )
            )
        items.sort(key=lambda item: item.relevance_score, reverse=True)
        tokens = payload.get("tokens") if isinstance(payload.get("tokens"), dict) else {}
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        if not tokens and isinstance(meta.get("tokens"), dict):
            tokens = meta["tokens"]
        return RerankResult(
            items=items,
            model=self.reranker_model,
            host=host,
            latency_ms=latency_ms,
            input_tokens=int(tokens.get("input_tokens") or 0),
            output_tokens=int(tokens.get("output_tokens") or 0),
        )


__all__ = [
    "EmbeddingResult",
    "RerankItem",
    "RerankResult",
    "SiliconFlowClient",
    "SiliconFlowError",
    "endpoint_candidates",
    "normalize_endpoint",
]
