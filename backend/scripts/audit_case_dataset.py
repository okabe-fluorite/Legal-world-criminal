"""Audit criminal case records before they enter the product case picker."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = REPO_ROOT / "dataset" / "criminal_case_dataset.json"
BAD_NAMES = {"扣押", "情况", "参考", "公安", "营业", "同案", "因本案", "吉林"}
CASE_NUMBER_RE = re.compile(r"[（(]\d{4}[）)]?[^，。；;\s]{1,24}号")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _add(flags: list[dict[str, str]], severity: str, code: str, message: str) -> None:
    flags.append({"severity": severity, "code": code, "message": message})


def audit_case(
    record: dict[str, Any],
    *,
    source_root: Path | None = None,
) -> dict[str, Any]:
    info = record.get("extracted_info") or {}
    first = info.get("first_instance") or {}
    party = (info.get("party_info") or {}).get("defendant") or {}
    name = _text(party.get("name"))
    background = _text(info.get("case_background"))
    finding = _text(first.get("court_finding"))
    opinion = _text(first.get("court_opinion"))
    sentence = _text(first.get("main_sentence"))
    title = _text(info.get("source_title"))
    charge = _text(info.get("charge"))
    legal_basis = _text(first.get("legal_basis"))
    flags: list[dict[str, str]] = []

    if not name or name in BAD_NAMES or not 2 <= len(name) <= 12:
        _add(flags, "critical", "invalid_defendant_name", f"invalid defendant name: {name!r}")
    if len(background) < 120:
        _add(flags, "critical", "missing_case_background", "case background is missing or too short")
    if name and background and name not in background:
        _add(flags, "critical", "defendant_background_mismatch", "defendant is absent from case background")
    if len(finding) < 80:
        _add(flags, "critical", "missing_court_finding", "court finding is missing or too short")
    if name and finding and name not in finding:
        _add(flags, "critical", "defendant_finding_mismatch", "defendant is absent from court finding")
    if finding.count("经审理查明") > 1:
        _add(flags, "critical", "multiple_court_findings", "multiple cases may have been concatenated")
    if len(set(CASE_NUMBER_RE.findall(finding))) > 1:
        _add(flags, "critical", "multiple_case_numbers_in_finding", "court finding contains multiple case numbers")
    if not opinion:
        _add(flags, "high", "missing_court_opinion", "court opinion is empty")
    if not sentence:
        _add(flags, "high", "missing_judgment", "judgment result is empty")
    if not legal_basis:
        _add(flags, "high", "missing_legal_basis", "legal basis is empty")
    if not title or "案" not in title or len(title) > 100:
        _add(flags, "high", "invalid_source_title", "source title is not a plausible case title")
    if not charge or charge.endswith("2罪"):
        _add(flags, "high", "invalid_charge", f"charge is not normalized: {charge!r}")
    if not _text(info.get("guiding_points")):
        _add(flags, "high", "missing_guiding_points", "guiding points are empty")
    if not _text(info.get("defense_hint")):
        _add(flags, "medium", "missing_defense_hint", "defense hint is empty")
    combined = "\n".join((background, finding, opinion, sentence, legal_basis))
    for polluted in ("中国刑事辩护网提供", "百度文库", "下载APP"):
        if polluted in combined:
            _add(flags, "critical", "source_pollution", f"polluted phrase found: {polluted}")

    release = record.get("release") or {}
    provenance = record.get("provenance") or {}
    knowledge_points = info.get("knowledge_points") or []
    if not release:
        _add(
            flags,
            "high",
            "missing_release_review",
            "case has no explicit release status or review boundary",
        )
    else:
        if _text(release.get("release_status")) != "pilot_release_approved":
            _add(flags, "high", "release_not_approved", "release status is not pilot_release_approved")
        if (
            not _text(provenance.get("source_url"))
            or not _text(provenance.get("local_source_path"))
            or not _text(provenance.get("local_source_sha256"))
        ):
            _add(
                flags,
                "critical",
                "missing_provenance",
                "released case lacks source URL, local source path, or source hash",
            )
        if source_root is not None and _text(provenance.get("local_source_path")):
            root = source_root.resolve()
            candidate = (root / _text(provenance.get("local_source_path"))).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                _add(flags, "critical", "unsafe_source_path", "local source path leaves source root")
            else:
                if not candidate.is_file():
                    _add(flags, "critical", "missing_local_source", "local source file is missing")
                else:
                    actual_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
                    if actual_sha.lower() != _text(
                        provenance.get("local_source_sha256")
                    ).lower():
                        _add(
                            flags,
                            "critical",
                            "local_source_hash_mismatch",
                            "local source SHA-256 does not match provenance",
                        )
        if not knowledge_points or any(
            not _text(item.get("knowledge_id")) for item in knowledge_points if isinstance(item, dict)
        ):
            _add(flags, "critical", "missing_canonical_knowledge", "released case lacks canonical knowledge IDs")

    severity_counts = Counter(item["severity"] for item in flags)
    releasable = severity_counts["critical"] == 0 and severity_counts["high"] == 0
    return {
        "original_id": record.get("original_id"),
        "source_title": title,
        "defendant": name,
        "charge": charge,
        "releasable": releasable,
        "severity_counts": dict(severity_counts),
        "flags": flags,
    }


def audit_dataset(path: Path, *, source_root: Path | None = None) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("case dataset root must be a list")
    rows = [
        audit_case(record, source_root=source_root)
        for record in data
        if isinstance(record, dict)
    ]
    return {
        "schema_version": "criminal-case-quality-audit-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(path.resolve()),
        "dataset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_root": str(source_root.resolve()) if source_root is not None else None,
        "counts": {
            "records": len(rows),
            "releasable": sum(row["releasable"] for row in rows),
            "blocked": sum(not row["releasable"] for row in rows),
            "critical_flags": sum(row["severity_counts"].get("critical", 0) for row in rows),
            "high_flags": sum(row["severity_counts"].get("high", 0) for row in rows),
        },
        "cases": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--source-root",
        type=Path,
        help="Optional read-only laws root used to verify each local source path and SHA-256",
    )
    parser.add_argument("--require-all-releasable", action="store_true")
    args = parser.parse_args()
    result = audit_dataset(args.dataset, source_root=args.source_root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result["counts"], ensure_ascii=False, indent=2))
    if args.require_all_releasable and result["counts"]["blocked"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
