"""Run a secret-safe SiliconFlow Embedding/Reranker probe over Hybrid RAG data."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from src.hybrid_rag.siliconflow import SiliconFlowClient, SiliconFlowError  # noqa: E402


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def percentile(values: Sequence[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile_value
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def spread(rows: Sequence[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if len(rows) < count:
        raise ValueError(f"probe stratum is too small: need={count} have={len(rows)}")
    if count == 1:
        return [rows[0]]
    return [rows[round(index * (len(rows) - 1) / (count - 1))] for index in range(count)]


def text_of(row: dict[str, Any]) -> str:
    return str(row.get("content") or row.get("stem") or row.get("title") or "").strip()


def build_strata(corpus_dir: Path) -> dict[str, list[dict[str, Any]]]:
    legal = read_jsonl(corpus_dir / "legal_chunks.jsonl")
    textbooks = read_jsonl(corpus_dir / "textbook_chunks.jsonl")
    questions = read_jsonl(corpus_dir / "question_public.jsonl")
    return {
        "law": [row for row in legal if row.get("source_type") == "law"],
        "regulation": [row for row in legal if row.get("source_type") == "regulation"],
        "judicial_interpretation": [row for row in legal if row.get("source_type") == "judicial_interpretation"],
        "case_child": [row for row in legal if row.get("source_type") == "case" and row.get("parent_id")],
        "textbook": textbooks,
        "question_public": questions,
    }


def batched(values: Sequence[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield list(values[start : start + size])


def load_client(env_path: Path) -> SiliconFlowClient:
    env = read_env(env_path)
    embedding_key = env.get("LAW_EMBEDDING_API_KEY", "")
    reranker_key = env.get("LAW_RERANKER_API_KEY", "")
    if embedding_key and reranker_key and embedding_key != reranker_key:
        raise ValueError("probe currently requires the same SiliconFlow key for both APIs")
    return SiliconFlowClient(
        api_key=embedding_key or reranker_key,
        embedding_url=env.get("LAW_EMBEDDING_API_BASE_URL", ""),
        embedding_model=env.get("LAW_EMBEDDING_MODEL", ""),
        reranker_url=env.get("LAW_RERANKER_API_BASE_URL", ""),
        reranker_model=env.get("LAW_RERANKER_MODEL", ""),
    )


def run_embedding_probe(
    client: SiliconFlowClient,
    samples: list[tuple[str, str]],
    *,
    batch_size: int,
) -> dict[str, Any]:
    latencies: list[float] = []
    prompt_tokens = 0
    total_tokens = 0
    models: Counter[str] = Counter()
    hosts: Counter[str] = Counter()
    dimensions: Counter[int] = Counter()
    texts = [text for _, text in samples]
    for batch in batched(texts, batch_size):
        result = client.embed(batch, dimensions=1024)
        latencies.append(result.latency_ms)
        prompt_tokens += result.prompt_tokens
        total_tokens += result.total_tokens
        models[result.model] += 1
        hosts[result.host] += 1
        dimensions.update(len(vector) for vector in result.vectors)
    return {
        "status": "succeeded",
        "input_count": len(texts),
        "request_count": len(latencies),
        "strata": dict(Counter(stratum for stratum, _ in samples)),
        "models": dict(models),
        "hosts": dict(hosts),
        "dimensions": dict(dimensions),
        "all_vectors_finite": True,
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 3),
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "max": round(max(latencies), 3),
        },
        "usage": {"prompt_tokens": prompt_tokens, "total_tokens": total_tokens},
    }


def candidate_documents(corpus_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    by_id: dict[str, str] = {}
    tier_by_id: dict[str, str] = {}
    for filename, tier, id_field in (
        ("legal_chunks.jsonl", "legal_authority", "chunk_id"),
        ("textbook_chunks.jsonl", "textbook_explanation", "chunk_id"),
        ("question_public.jsonl", "question_teaching_public", "question_id"),
    ):
        for row in read_jsonl(corpus_dir / filename):
            identifier = str(row[id_field])
            by_id[identifier] = text_of(row)
            tier_by_id[identifier] = tier
    return by_id, tier_by_id


def run_reranker_probe(
    client: SiliconFlowClient,
    corpus_dir: Path,
    qrels_path: Path,
    *,
    query_count: int,
) -> dict[str, Any]:
    qrels = [row for row in read_jsonl(qrels_path) if row.get("positive_ids")]
    selected = spread(qrels, query_count)
    text_by_id, tier_by_id = candidate_documents(corpus_dir)
    ids_by_tier: dict[str, list[str]] = defaultdict(list)
    for identifier, tier in tier_by_id.items():
        ids_by_tier[tier].append(identifier)
    latencies: list[float] = []
    input_tokens = 0
    output_tokens = 0
    hosts: Counter[str] = Counter()
    candidate_hit_at_1 = 0
    candidate_hit_at_5 = 0
    valid_queries = 0
    for query_index, qrel in enumerate(selected):
        positives = [identifier for identifier in qrel["positive_ids"] if identifier in text_by_id]
        if not positives:
            continue
        positive_id = positives[0]
        tier = qrel["target_tier"]
        negative_pool = [identifier for identifier in ids_by_tier[tier] if identifier not in positives]
        if len(negative_pool) < 7:
            continue
        start = (query_index * 17) % len(negative_pool)
        negatives = (negative_pool[start:] + negative_pool[:start])[:7]
        candidate_ids = negatives[:3] + [positive_id] + negatives[3:]
        documents = [text_by_id[identifier] for identifier in candidate_ids]
        result = client.rerank(
            qrel["query"],
            documents,
            top_n=5,
            return_documents=False,
            instruction="优先返回与法律问题直接相关、法名条号或裁判规则匹配的材料。",
        )
        latencies.append(result.latency_ms)
        input_tokens += result.input_tokens
        output_tokens += result.output_tokens
        hosts[result.host] += 1
        ranked_ids = [candidate_ids[item.index] for item in result.items]
        candidate_hit_at_1 += bool(ranked_ids and ranked_ids[0] in positives)
        candidate_hit_at_5 += bool(set(ranked_ids[:5]) & set(positives))
        valid_queries += 1
    if valid_queries != query_count:
        raise ValueError(f"reranker probe coverage incomplete: expected={query_count} actual={valid_queries}")
    return {
        "status": "succeeded",
        "query_count": valid_queries,
        "request_count": len(latencies),
        "documents_per_query": 8,
        "top_n": 5,
        "hosts": dict(hosts),
        "candidate_positive_at_1": round(candidate_hit_at_1 / valid_queries, 4),
        "candidate_positive_at_5": round(candidate_hit_at_5 / valid_queries, 4),
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 3),
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "max": round(max(latencies), 3),
        },
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=REPO / ".env")
    parser.add_argument("--corpus-dir", type=Path, default=REPO / ".codex-artifacts" / "hybrid-rag-corpus-v1")
    parser.add_argument("--qrels", type=Path, default=REPO / ".codex-artifacts" / "hybrid-rag-eval-v1" / "qrels_candidate.jsonl")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=300)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--rerank-queries", type=int, default=30)
    args = parser.parse_args()
    if args.sample_size < 6 or args.sample_size > 500 or args.sample_size % 6:
        raise ValueError("sample-size must be a multiple of 6 between 6 and 500")
    client = load_client(args.env.resolve())
    strata = build_strata(args.corpus_dir.resolve())
    per_stratum = args.sample_size // 6
    samples = [
        (name, text_of(row))
        for name, rows in strata.items()
        for row in spread(rows, per_stratum)
    ]
    started_at = datetime.now(timezone.utc)
    report: dict[str, Any] = {
        "schema_version": "hybrid-rag-siliconflow-probe-v1",
        "started_at": started_at.isoformat(),
        "status": "running",
        "sample_scope": "deterministic_stratified_probe",
        "embedding": None,
        "reranker": None,
        "errors": [],
        "evidence_boundary": (
            "This probe validates API compatibility and candidate-template behavior only. "
            "Candidate relevance labels still require legal-teacher review."
        ),
    }
    try:
        report["embedding"] = run_embedding_probe(client, samples, batch_size=args.batch_size)
        report["reranker"] = run_reranker_probe(
            client,
            args.corpus_dir.resolve(),
            args.qrels.resolve(),
            query_count=args.rerank_queries,
        )
        report["status"] = "succeeded"
    except (SiliconFlowError, ValueError) as exc:
        report["status"] = "failed"
        report["errors"].append(
            {
                "type": type(exc).__name__,
                "status_code": getattr(exc, "status_code", None),
                "host": getattr(exc, "host", ""),
                "message": str(exc),
            }
        )
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_report(args.output.resolve(), report)
    print(json.dumps({"status": report["status"], "output": args.output.name}, ensure_ascii=False))
    return 0 if report["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
