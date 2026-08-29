"""Audit a frozen competition-demo runtime without exposing credentials."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def integrity(path: Path) -> str:
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as db:
        return str(db.execute("PRAGMA integrity_check").fetchone()[0])


def identity_audit(path: Path) -> dict[str, object]:
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as db:
        emails = [str(row[0]) for row in db.execute("SELECT email FROM users")]
    domains = Counter(email.rsplit("@", 1)[-1].lower() for email in emails)
    return {
        "user_count": len(emails),
        "domains": dict(domains),
        "synthetic_only": set(domains) <= {"example.com"},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    runtime = args.runtime.resolve()

    main_db = runtime / "legalworld-local.db"
    adaptive_db = runtime / "adaptive.db"
    teacher_path = runtime / "teacher-smoke-result.json"
    case_path = runtime / "case3-e2e-summary.json"
    for required in (main_db, adaptive_db, teacher_path, case_path):
        if not required.is_file():
            raise SystemExit(f"missing demo evidence: {required}")

    teacher = read_json(teacher_path)
    case = read_json(case_path)
    identities = identity_audit(main_db)
    checks = {
        "main_db_integrity": integrity(main_db) == "ok",
        "adaptive_db_integrity": integrity(adaptive_db) == "ok",
        "synthetic_example_accounts_only": identities["synthetic_only"],
        "teacher_revision_queue_cleared": teacher.get("subjective_queue_after_revision_request") == 0,
        "teacher_revised_draft_seen": teacher.get("subjective_queue_before_approval") == 1,
        "teacher_approval_queue_cleared": teacher.get("subjective_queue_after") == 0,
        "student_approval_visible": teacher.get("student_approval_visible") is True,
        "teacher_event_recorded": teacher.get("subjective_review_event_recorded") is True,
        "teacher_browser_errors_zero": not any(
            teacher.get(key)
            for key in ("console_errors", "page_errors", "http_errors", "request_failures")
        ),
        "case3_closed": case.get("case_id") == "case_3" and case.get("closed") is True,
        "case3_not_timed_out": case.get("timed_out") is False,
        "case3_runtime_issues_zero": not case.get("runtime_issues"),
        "case3_agents_despawned": case.get("post_close_agent_despawns") == 3,
        "case3_fixed_inputs_disclosed": "deterministic synthetic student inputs"
        in str(case.get("evidence_boundary") or ""),
    }
    report = {
        "schema": "competition-demo-semantic-audit-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime": str(runtime),
        "identities": identities,
        "checks": checks,
        "passed": all(checks.values()),
    }
    output = (args.output or runtime / "semantic-audit.json").resolve()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
