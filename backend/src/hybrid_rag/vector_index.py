"""Resumable local float16 vector-index builder for Hybrid RAG corpora."""

from __future__ import annotations

import hashlib
import json
import os
import statistics
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

from .siliconflow import EmbeddingResult


@dataclass(frozen=True)
class IndexRecord:
    retrieval_id: str
    text: str
    metadata: dict[str, Any]


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _signature(records: Sequence[IndexRecord]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(record.retrieval_id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(record.text)).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _write_metadata(path: Path, records: Sequence[IndexRecord]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            payload = dict(record.metadata)
            payload["retrieval_id"] = record.retrieval_id
            payload["retrieval_text"] = record.text
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def build_vector_index(
    *,
    collection_name: str,
    records: Sequence[IndexRecord],
    output_dir: Path,
    embed_batch: Callable[[Sequence[str]], EmbeddingResult],
    model_name: str,
    vector_dim: int = 1024,
    batch_size: int = 32,
    workers: int = 8,
    checkpoint_every: int = 10,
) -> dict[str, Any]:
    if not records:
        raise ValueError(f"collection {collection_name} is empty")
    if len({record.retrieval_id for record in records}) != len(records):
        raise ValueError(f"collection {collection_name} contains duplicate retrieval IDs")
    if any(not record.text.strip() for record in records):
        raise ValueError(f"collection {collection_name} contains empty retrieval text")
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "build_state.json"
    partial_path = output_dir / "embeddings.float16.partial.npy"
    final_path = output_dir / "embeddings.float16.npy"
    metadata_path = output_dir / "metadata.jsonl"
    manifest_path = output_dir / "manifest.json"
    lexical_path = output_dir / "lexical.sqlite"
    source_signature = _signature(records)
    batch_ranges = [
        (index, start, min(len(records), start + batch_size))
        for index, start in enumerate(range(0, len(records), batch_size))
    ]
    if manifest_path.is_file() and final_path.is_file() and metadata_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            manifest.get("source_signature") == source_signature
            and manifest.get("record_count") == len(records)
            and manifest.get("vector_dim") == vector_dim
            and manifest.get("model") == model_name
        ):
            if not lexical_path.is_file():
                from .lexical_index import build_lexical_index

                build_lexical_index(records, lexical_path)
                manifest["lexical_file"] = lexical_path.name
                manifest["lexical_ranker"] = "SQLite FTS5 BM25F-style weighted fields"
                _atomic_json(manifest_path, manifest)
            return manifest
        raise ValueError(f"completed index {collection_name} does not match current inputs")

    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        expected = (source_signature, len(records), vector_dim, model_name, batch_size)
        actual = (
            state.get("source_signature"),
            state.get("record_count"),
            state.get("vector_dim"),
            state.get("model"),
            state.get("batch_size"),
        )
        if actual != expected:
            raise ValueError(f"partial index {collection_name} does not match current inputs")
    else:
        state = {
            "schema_version": "hybrid-rag-vector-build-state-v1",
            "collection": collection_name,
            "source_signature": source_signature,
            "record_count": len(records),
            "vector_dim": vector_dim,
            "model": model_name,
            "batch_size": batch_size,
            "completed_batches": [],
            "request_metrics": [],
            "prompt_tokens": 0,
            "total_tokens": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        np.lib.format.open_memmap(
            partial_path,
            mode="w+",
            dtype=np.float16,
            shape=(len(records), vector_dim),
        ).flush()
        _write_metadata(metadata_path, records)
        _atomic_json(state_path, state)

    if not partial_path.is_file():
        raise ValueError(f"partial vector file is missing for {collection_name}")
    completed = {int(value) for value in state.get("completed_batches", [])}
    matrix = np.lib.format.open_memmap(partial_path, mode="r+", dtype=np.float16)
    if matrix.shape != (len(records), vector_dim):
        raise ValueError(f"partial vector shape mismatch for {collection_name}: {matrix.shape}")
    pending = [(index, start, end) for index, start, end in batch_ranges if index not in completed]

    def run_batch(start: int, end: int) -> EmbeddingResult:
        return embed_batch([record.text for record in records[start:end]])

    failures: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map: dict[Future[EmbeddingResult], tuple[int, int, int]] = {
            executor.submit(run_batch, start, end): (index, start, end)
            for index, start, end in pending
        }
        newly_completed = 0
        for future in as_completed(future_map):
            batch_index, start, end = future_map[future]
            try:
                result = future.result()
                values = np.asarray(result.vectors, dtype=np.float32)
                if values.shape != (end - start, vector_dim) or not np.isfinite(values).all():
                    raise ValueError(f"invalid vector batch shape or values: batch={batch_index}")
                norms = np.linalg.norm(values, axis=1, keepdims=True)
                if np.any(norms <= 0.0):
                    raise ValueError(f"zero-norm vector in batch={batch_index}")
                values /= norms
                matrix[start:end] = values.astype(np.float16)
                matrix.flush()
                completed.add(batch_index)
                state["completed_batches"] = sorted(completed)
                state["request_metrics"].append(
                    {"batch": batch_index, "latency_ms": round(result.latency_ms, 3), "host": result.host}
                )
                state["prompt_tokens"] = int(state.get("prompt_tokens", 0)) + result.prompt_tokens
                state["total_tokens"] = int(state.get("total_tokens", 0)) + result.total_tokens
                newly_completed += 1
                if newly_completed % max(1, checkpoint_every) == 0:
                    _atomic_json(state_path, state)
            except Exception as exc:  # checkpoint remaining batches and report safely
                failures.append(
                    {
                        "batch": batch_index,
                        "type": type(exc).__name__,
                        "status_code": getattr(exc, "status_code", None),
                        "host": getattr(exc, "host", ""),
                        "message": str(exc),
                    }
                )
    _atomic_json(state_path, state)
    del matrix
    if failures:
        raise RuntimeError(
            f"collection {collection_name} has {len(failures)} failed batches; rerun to resume; first={failures[0]}"
        )
    if len(completed) != len(batch_ranges):
        raise RuntimeError(f"collection {collection_name} is incomplete after embedding")
    os.replace(partial_path, final_path)
    from .lexical_index import build_lexical_index

    build_lexical_index(records, lexical_path)
    metrics = state.get("request_metrics", [])
    latencies = [float(item["latency_ms"]) for item in metrics]
    host_counts = Counter(str(item["host"]) for item in metrics)
    manifest = {
        "schema_version": "hybrid-rag-vector-index-v1",
        "collection": collection_name,
        "status": "ready",
        "source_signature": source_signature,
        "record_count": len(records),
        "vector_dim": vector_dim,
        "dtype": "float16",
        "normalized": True,
        "model": model_name,
        "batch_size": batch_size,
        "request_count": len(metrics),
        "hosts": dict(host_counts),
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 3),
            "p50": round(_percentile(latencies, 0.50), 3),
            "p95": round(_percentile(latencies, 0.95), 3),
            "max": round(max(latencies), 3),
        },
        "usage": {
            "prompt_tokens": int(state.get("prompt_tokens", 0)),
            "total_tokens": int(state.get("total_tokens", 0)),
        },
        "vector_file": final_path.name,
        "metadata_file": metadata_path.name,
        "lexical_file": lexical_path.name,
        "lexical_ranker": "SQLite FTS5 BM25F-style weighted fields",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_json(manifest_path, manifest)
    state_path.unlink(missing_ok=True)
    return manifest


__all__ = ["IndexRecord", "build_vector_index"]
