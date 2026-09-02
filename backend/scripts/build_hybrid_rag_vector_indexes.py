"""Build three local Hybrid RAG vector indexes with resumable concurrent calls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from scripts.run_hybrid_rag_siliconflow_probe import load_client, read_jsonl  # noqa: E402
from src.hybrid_rag.vector_index import IndexRecord, build_vector_index  # noqa: E402


def legal_records(corpus_dir: Path) -> list[IndexRecord]:
    return [
        IndexRecord(
            retrieval_id=str(row["chunk_id"]),
            text=str(row.get("embed_text") or row["content"]),
            metadata=row,
        )
        for row in read_jsonl(corpus_dir / "legal_chunks.jsonl")
    ]


def textbook_records(corpus_dir: Path) -> list[IndexRecord]:
    return [
        IndexRecord(
            retrieval_id=str(row["chunk_id"]),
            text=str(row.get("embed_text") or row["content"]),
            metadata=row,
        )
        for row in read_jsonl(corpus_dir / "textbook_chunks.jsonl")
    ]


def question_records(corpus_dir: Path) -> list[IndexRecord]:
    return [
        IndexRecord(
            retrieval_id=str(row["question_id"]),
            text=str(row.get("embed_text") or row["stem"]),
            metadata=row,
        )
        for row in read_jsonl(corpus_dir / "question_public.jsonl")
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=REPO / ".env")
    parser.add_argument("--corpus-dir", type=Path, default=REPO / ".codex-artifacts" / "hybrid-rag-corpus-v1")
    parser.add_argument("--output-dir", type=Path, default=REPO / ".codex-artifacts" / "hybrid-rag-index-v1")
    parser.add_argument("--collections", nargs="+", choices=["legal_authority", "textbook_explanation", "question_public"], default=["legal_authority", "textbook_explanation", "question_public"])
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    corpus_dir = args.corpus_dir.resolve()
    output_dir = args.output_dir.resolve()
    client = load_client(args.env.resolve())
    builders = {
        "legal_authority": legal_records,
        "textbook_explanation": textbook_records,
        "question_public": question_records,
    }
    reports: dict[str, Any] = {}
    for collection in args.collections:
        records = builders[collection](corpus_dir)
        print(json.dumps({"collection": collection, "status": "building", "records": len(records)}, ensure_ascii=False), flush=True)
        reports[collection] = build_vector_index(
            collection_name=collection,
            records=records,
            output_dir=output_dir / collection,
            embed_batch=lambda texts: client.embed(texts, dimensions=1024),
            model_name=client.embedding_model,
            vector_dim=1024,
            batch_size=args.batch_size,
            workers=args.workers,
        )
        print(json.dumps({"collection": collection, "status": "ready", "records": len(records)}, ensure_ascii=False), flush=True)
    manifest_path = output_dir / "index_set_manifest.json"
    existing_collections: dict[str, Any] = {}
    if manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(existing.get("collections"), dict):
            existing_collections.update(existing["collections"])
    existing_collections.update(reports)
    summary = {
        "schema_version": "hybrid-rag-vector-index-set-v1",
        "status": "ready",
        "collections": existing_collections,
        "private_question_index": "disabled_by_design",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "ready", "collections": list(reports)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
