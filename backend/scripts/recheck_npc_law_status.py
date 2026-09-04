"""Deterministically recheck canonical law status against the official NPC API."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from src.hybrid_rag.npc_status import iter_rechecked_laws  # noqa: E402
from src.hybrid_rag.official_verification import read_jsonl, write_jsonl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=REPO / ".codex-artifacts" / "official-verification-v1" / "laws_luna_resolved.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO / ".codex-artifacts" / "official-verification-v1" / "laws_npc_rechecked.jsonl",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPO / ".codex-artifacts" / "official-verification-v1" / "laws_npc_rechecked_summary.json",
    )
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()

    sources = read_jsonl(args.input.resolve())
    cached = {
        str(row.get("document_id") or ""): row
        for row in (read_jsonl(args.output.resolve()) if args.output.is_file() and not args.refresh else [])
    }
    pending = [] if args.cache_only else [
        row
        for row in sources
        if str(row.get("document_id") or "") not in cached
        or not int(cached[str(row.get("document_id") or "")].get("official_status_code") or 0)
    ]
    completed_since_checkpoint = 0
    for row in iter_rechecked_laws(pending, workers=args.workers):
        cached[str(row["document_id"])] = row
        completed_since_checkpoint += 1
        if completed_since_checkpoint >= 20:
            write_jsonl(args.output.resolve(), sorted(cached.values(), key=lambda item: str(item["document_id"])))
            completed_since_checkpoint = 0
    rows = sorted(cached.values(), key=lambda row: str(row["document_id"]))
    write_jsonl(args.output.resolve(), rows)
    status_counts = Counter(str(row.get("effective_status") or "unresolved") for row in rows)
    official_code_counts = Counter(str(row.get("official_status_code") or "unknown") for row in rows)
    source_by_id = {str(row.get("document_id") or ""): row for row in sources}
    conflicts = [
        {
            "document_id": str(row.get("document_id") or ""),
            "official_status": str(row.get("effective_status") or ""),
            "previous_status": str(source_by_id[str(row.get("document_id") or "")].get("effective_status") or ""),
        }
        for row in rows
        if int(row.get("official_status_code") or 0) > 0
        and str(source_by_id[str(row.get("document_id") or "")].get("effective_status") or "")
        != str(row.get("effective_status") or "")
    ]
    summary = {
        "schema_version": "npc-law-status-recheck-v1",
        "input_records": len(sources),
        "output_records": len(rows),
        "official_title_matches": sum(bool(row.get("official_title_matches")) for row in rows),
        "by_effective_status": dict(status_counts),
        "by_official_status_code": dict(official_code_counts),
        "unresolved": sum(str(row.get("effective_status")) == "unresolved" for row in rows),
        "official_api_success": sum(int(row.get("official_status_code") or 0) > 0 for row in rows),
        "official_api_unavailable": sum(int(row.get("official_status_code") or 0) == 0 for row in rows),
        "status_conflicts_with_previous": len(conflicts),
        "status_conflicts": conflicts,
        "workers": max(1, min(args.workers, 64)),
        "reused_cache": len(sources) - len(pending),
        "network_requests": len(pending),
        "cache_only": bool(args.cache_only),
        "official_endpoint": "https://flk.npc.gov.cn/law-search/search/flfgDetails",
        "status_mapping": {"1": "repealed", "2": "superseded", "3": "verified_current", "4": "unresolved_not_yet_effective"},
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if len(rows) == len(sources) else 1


if __name__ == "__main__":
    raise SystemExit(main())
