"""Create a public, secret-free summary of a private frozen demo backup."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--restore-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    backup = args.backup.resolve()
    manifest_path = backup / "manifest.json"
    source_audit_path = backup / "evidence" / "semantic-audit.json"
    teacher_path = backup / "evidence" / "teacher-smoke-result.json"
    case_path = backup / "evidence" / "case3-e2e-summary.json"
    for required in (
        manifest_path,
        source_audit_path,
        teacher_path,
        case_path,
        args.restore_audit,
    ):
        if not required.is_file():
            raise SystemExit(f"missing frozen-demo evidence: {required}")

    manifest = read_json(manifest_path)
    source_audit = read_json(source_audit_path)
    restore_audit = read_json(args.restore_audit)
    teacher = read_json(teacher_path)
    case = read_json(case_path)
    files = manifest.get("files") or []

    summary = {
        "schema": "competition-frozen-demo-public-audit-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_git_commit": manifest.get("git_commit"),
        "backup_manifest_sha256": sha256(manifest_path),
        "backup_file_count": len(files),
        "backup_payload_bytes": sum(int(row.get("bytes") or 0) for row in files),
        "private_backup_policy": {
            "contains_password_hashes": bool(manifest.get("contains_password_hashes")),
            "access_policy": manifest.get("access_policy"),
            "published_in_git": False,
        },
        "identity_boundary": source_audit.get("identities"),
        "database_semantics": source_audit.get("database_semantics"),
        "teacher_journey": {
            "class_metrics_before": teacher.get("metrics"),
            "class_metrics_after": teacher.get("metrics_after_subjective_approval"),
            "revision_feedback_visible": teacher.get("revision_feedback_visible"),
            "revision_prefilled_original": teacher.get("revision_prefilled_original"),
            "student_approval_visible": teacher.get("student_approval_visible"),
            "queues": {
                "before": teacher.get("subjective_queue_before"),
                "after_revision": teacher.get("subjective_queue_after_revision_request"),
                "before_approval": teacher.get("subjective_queue_before_approval"),
                "after_approval": teacher.get("subjective_queue_after"),
            },
            "browser_errors": {
                key: len(teacher.get(key) or [])
                for key in ("console_errors", "page_errors", "http_errors", "request_failures")
            },
        },
        "case3_e2e": {
            "case_id": case.get("case_id"),
            "closed": case.get("closed"),
            "timed_out": case.get("timed_out"),
            "elapsed_seconds": case.get("elapsed_seconds"),
            "fixed_response_count": case.get("submitted_response_count"),
            "stages_seen": case.get("stages_seen"),
            "scenario_start_count": (case.get("event_counts") or {}).get("scenario_start"),
            "scenario_end_count": (case.get("event_counts") or {}).get("scenario_end"),
            "agent_despawn_count": case.get("post_close_agent_despawns"),
            "runtime_issue_count": len(case.get("runtime_issues") or []),
            "evidence_boundary": case.get("evidence_boundary"),
        },
        "semantic_audit": {
            "source_passed": source_audit.get("passed"),
            "source_check_count": len(source_audit.get("checks") or {}),
            "restore_passed": restore_audit.get("passed"),
            "restore_check_count": len(restore_audit.get("checks") or {}),
        },
        "evidence_boundary": (
            "synthetic example.com demo accounts and deterministic student inputs; "
            "proves reproducible software behavior, not target-user approval, learning gain, "
            "expert legal validity, or formal grading validity"
        ),
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
