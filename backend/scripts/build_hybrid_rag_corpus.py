"""Build canonical law/textbook/question corpora without model or network calls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from src.hybrid_rag import BuildConfig, build_corpus  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--laws-root", type=Path, required=True)
    parser.add_argument("--textbook-root", type=Path, required=True)
    parser.add_argument("--jecqa-single", type=Path, required=True)
    parser.add_argument("--jecqa-multiple", type=Path, required=True)
    parser.add_argument("--task-items", type=Path, default=REPO / "adaptive_service" / "data" / "task_items.jsonl")
    parser.add_argument(
        "--subjective-tasks",
        type=Path,
        default=REPO / "adaptive_service" / "data" / "subjective_tasks.jsonl",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--snapshot-date", required=True)
    parser.add_argument(
        "--inventory",
        type=Path,
        default=REPO / "data_governance" / "corpus_inventory.json",
        help="governed inventory used for source, validity, privacy, and redistribution metadata",
    )
    parser.add_argument("--public-audit-json", type=Path)
    parser.add_argument("--public-audit-md", type=Path)
    parser.add_argument("--target-chars", type=int, default=1000)
    parser.add_argument("--max-chars", type=int, default=1400)
    parser.add_argument("--overlap-chars", type=int, default=120)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also fail on non-blocking quality warnings; default only fails required correctness/security checks",
    )
    args = parser.parse_args()
    manifest, audit = build_corpus(
        BuildConfig(
            laws_root=args.laws_root.resolve(),
            textbook_root=args.textbook_root.resolve(),
            task_items_path=args.task_items.resolve(),
            subjective_tasks_path=args.subjective_tasks.resolve(),
            jecqa_single_path=args.jecqa_single.resolve(),
            jecqa_multiple_path=args.jecqa_multiple.resolve(),
            output_dir=args.output_dir.resolve(),
            snapshot_date=args.snapshot_date,
            inventory_path=args.inventory.resolve() if args.inventory else None,
            public_audit_json=args.public_audit_json.resolve() if args.public_audit_json else None,
            public_audit_md=args.public_audit_md.resolve() if args.public_audit_md else None,
            target_chunk_chars=args.target_chars,
            max_chunk_chars=args.max_chars,
            overlap_chars=args.overlap_chars,
        )
    )
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "counts": manifest["counts"],
                "audit_all_passed": audit["all_passed"],
                "required_checks_passed": audit["required_checks_passed"],
                "quality_warnings": audit["quality_warnings"],
                "embedding_calls": audit["execution"]["embedding_calls"],
                "reranker_calls": audit["execution"]["reranker_calls"],
            },
            ensure_ascii=False,
        )
    )
    success = audit["strict_all_passed"] if args.strict else audit["required_checks_passed"]
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
