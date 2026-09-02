"""Build candidate retrieval qrels and NLI annotation templates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from src.hybrid_rag.eval_templates import build_eval_templates  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--qrels-output", type=Path, required=True)
    parser.add_argument("--nli-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    args = parser.parse_args()
    qrels, nli = build_eval_templates(args.corpus_dir.resolve())
    write_jsonl(args.qrels_output, qrels)
    write_jsonl(args.nli_output, nli)
    manifest = {
        "schema_version": "hybrid-rag-eval-template-manifest-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "candidate_requires_teacher_review",
        "is_gold": False,
        "counts": {
            "qrels": len(qrels),
            "qrels_by_type": dict(Counter(row["query_type"] for row in qrels)),
            "nli_pairs": len(nli),
            "nli_by_candidate_label": dict(Counter(row["candidate_label"] for row in nli)),
            "gold_labels": sum(row["gold_label"] is not None for row in nli),
        },
        "outputs": {
            "qrels": {"file": args.qrels_output.name, "sha256": sha256(args.qrels_output)},
            "nli": {"file": args.nli_output.name, "sha256": sha256(args.nli_output)},
        },
        "execution": {"model_calls": 0, "network_calls": 0},
        "evidence_boundary": "Automatically constructed candidates are annotation templates, not retrieval Gold or expert NLI labels.",
    }
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
