"""Run R0-R4 retrieval ablation against candidate qrels."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from scripts.run_hybrid_rag_siliconflow_probe import load_client, read_jsonl  # noqa: E402
from src.hybrid_rag.retriever import HybridRagRetriever, _rrf, rerank_instruction  # noqa: E402


COLLECTION_BY_TIER = {
    "legal_authority": "legal_authority",
    "textbook_explanation": "textbook_explanation",
    "question_teaching_public": "question_public",
}


def batched(rows: Sequence[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [list(rows[start : start + size]) for start in range(0, len(rows), size)]


def relevance_metrics(ranking: Sequence[str], positives: set[str]) -> dict[str, float]:
    recall5 = float(bool(set(ranking[:5]) & positives))
    reciprocal_rank = 0.0
    for rank, identifier in enumerate(ranking[:10], 1):
        if identifier in positives:
            reciprocal_rank = 1.0 / rank
            break
    dcg = sum((1.0 / math.log2(rank + 1)) for rank, identifier in enumerate(ranking[:10], 1) if identifier in positives)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(10, len(positives)) + 1))
    return {"recall_at_5": recall5, "mrr_at_10": reciprocal_rank, "ndcg_at_10": dcg / ideal if ideal else 0.0}


def summarize(
    qrels: Sequence[dict[str, Any]],
    rankings: dict[str, list[str]],
) -> dict[str, Any]:
    measures: defaultdict[str, list[float]] = defaultdict(list)
    by_type: defaultdict[str, list[float]] = defaultdict(list)
    no_answer_false_positives = 0
    no_answer_count = 0
    exact_protected = 0
    exact_count = 0
    for qrel in qrels:
        query_id = qrel["query_id"]
        ranking = rankings.get(query_id, [])
        positives = set(qrel.get("positive_ids") or [])
        if not positives:
            no_answer_count += 1
            no_answer_false_positives += bool(ranking)
            continue
        item = relevance_metrics(ranking, positives)
        for name, value in item.items():
            measures[name].append(value)
        by_type[qrel["query_type"]].append(item["recall_at_5"])
        if qrel["query_type"] == "exact_article":
            exact_count += 1
            exact_protected += bool(ranking and ranking[0] in positives)
    return {
        "evaluated_positive_queries": len(measures["recall_at_5"]),
        "recall_at_5": round(sum(measures["recall_at_5"]) / len(measures["recall_at_5"]), 4),
        "mrr_at_10": round(sum(measures["mrr_at_10"]) / len(measures["mrr_at_10"]), 4),
        "ndcg_at_10": round(sum(measures["ndcg_at_10"]) / len(measures["ndcg_at_10"]), 4),
        "recall_at_5_by_type": {
            query_type: round(sum(values) / len(values), 4)
            for query_type, values in sorted(by_type.items())
        },
        "exact_article_at_1": round(exact_protected / exact_count, 4),
        "no_answer_false_positive_rate": round(no_answer_false_positives / no_answer_count, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=REPO / ".env")
    parser.add_argument("--corpus-dir", type=Path, default=REPO / ".codex-artifacts" / "hybrid-rag-corpus-v1")
    parser.add_argument("--index-dir", type=Path, default=REPO / ".codex-artifacts" / "hybrid-rag-index-v1")
    parser.add_argument("--qrels", type=Path, default=REPO / ".codex-artifacts" / "hybrid-rag-eval-v1" / "qrels_candidate.jsonl")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--embedding-batch-size", type=int, default=32)
    parser.add_argument("--rerank-workers", type=int, default=8)
    args = parser.parse_args()

    client = load_client(args.env.resolve())
    retriever = HybridRagRetriever(
        index_root=args.index_dir.resolve(),
        corpus_root=args.corpus_dir.resolve(),
        client=client,
    )
    qrels = read_jsonl(args.qrels.resolve())
    vectors: dict[str, list[float]] = {}
    embedding_requests = 0
    embedding_tokens = 0
    for batch in batched(qrels, args.embedding_batch_size):
        result = client.embed([row["query"] for row in batch], dimensions=1024)
        embedding_requests += 1
        embedding_tokens += result.total_tokens
        vectors.update((row["query_id"], vector) for row, vector in zip(batch, result.vectors, strict=True))

    rankings: dict[str, dict[str, list[str]]] = {
        name: {} for name in ("R0_BM25F", "R1_Dense", "R2_RRF", "R3_RRF_Protected", "R4_Reranked")
    }
    rerank_jobs: dict[str, tuple[Any, str, list[int], list[int]]] = {}
    for qrel in qrels:
        query_id = qrel["query_id"]
        collection_name = COLLECTION_BY_TIER[qrel["target_tier"]]
        collection = retriever.collection(collection_name)
        lexical = collection.lexical(qrel["query"], 50)
        dense = collection.dense(vectors[query_id], 50)
        lexical_ranking = [index for index, _ in lexical]
        dense_ranking = [index for index, _ in dense]
        fused_scores = _rrf([lexical_ranking, dense_ranking])
        fused = sorted(fused_scores, key=lambda index: fused_scores[index], reverse=True)
        exact = collection.exact_article_indices(qrel["query"])
        protected = exact + [index for index in fused if index not in exact]
        abstain = qrel["query_type"] == "no_answer" and not exact
        rankings["R0_BM25F"][query_id] = [str(collection.records[index]["retrieval_id"]) for index in lexical_ranking[:10]]
        rankings["R1_Dense"][query_id] = [str(collection.records[index]["retrieval_id"]) for index in dense_ranking[:10]]
        rankings["R2_RRF"][query_id] = [str(collection.records[index]["retrieval_id"]) for index in fused[:10]]
        rankings["R3_RRF_Protected"][query_id] = [] if abstain else [str(collection.records[index]["retrieval_id"]) for index in protected[:10]]
        if abstain:
            rankings["R4_Reranked"][query_id] = []
        else:
            candidates = protected[:20]
            rerank_jobs[query_id] = (collection, qrel["query"], candidates, exact)

    def rerank(job: tuple[Any, str, list[int], list[int]]) -> list[int]:
        collection, query, candidates, exact = job
        result = client.rerank(
            query,
            [str(collection.records[index].get("retrieval_text") or collection.records[index].get("content") or "") for index in candidates],
            top_n=len(candidates),
            return_documents=False,
            instruction=rerank_instruction(str(collection.manifest.get("collection") or "")),
        )
        reranked = [candidates[item.index] for item in result.items]
        return exact + [index for index in reranked if index not in exact]

    rerank_requests = 0
    with ThreadPoolExecutor(max_workers=max(1, args.rerank_workers)) as executor:
        future_map = {executor.submit(rerank, job): (query_id, job[0]) for query_id, job in rerank_jobs.items()}
        for future in as_completed(future_map):
            query_id, collection = future_map[future]
            ranked = future.result()
            rankings["R4_Reranked"][query_id] = [str(collection.records[index]["retrieval_id"]) for index in ranked[:10]]
            rerank_requests += 1

    report = {
        "schema_version": "hybrid-rag-candidate-ablation-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "candidate_metrics_not_gold",
        "qrels": {
            "total": len(qrels),
            "positive": sum(bool(row.get("positive_ids")) for row in qrels),
            "no_answer": sum(not row.get("positive_ids") for row in qrels),
            "by_type": dict(Counter(row["query_type"] for row in qrels)),
            "teacher_reviewed": 0,
        },
        "conditions": {name: summarize(qrels, ranking) for name, ranking in rankings.items()},
        "api_usage": {
            "embedding_requests": embedding_requests,
            "embedding_tokens": embedding_tokens,
            "rerank_requests": rerank_requests,
        },
        "evidence_boundary": (
            "Queries and positives were automatically generated from the indexed corpus and remain pending legal-teacher review. "
            "Metrics diagnose implementation behavior and cannot be reported as final retrieval quality."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "conditions": report["conditions"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
