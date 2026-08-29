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


def database_semantics(main_path: Path, adaptive_path: Path) -> dict[str, object]:
    with closing(sqlite3.connect(f"file:{main_path.as_posix()}?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        student = db.execute(
            "SELECT id FROM users WHERE email = ?", ("demo-student@example.com",)
        ).fetchone()
        teacher = db.execute(
            "SELECT id FROM users WHERE email = ?", ("demo-teacher@example.com",)
        ).fetchone()
        if student is None or teacher is None:
            return {"required_demo_accounts_present": False}
        student_id = str(student["id"])
        event_rows = db.execute(
            """
            SELECT event_type, stage, long_term_profile_eligible, adaptive_sync_status
            FROM learning_events
            WHERE user_id = ?
            ORDER BY created_at
            """,
            (student_id,),
        ).fetchall()
        decisions = db.execute(
            """
            SELECT review.decision
            FROM subjective_review_events AS review
            JOIN subjective_attempts AS attempt ON attempt.attempt_id = review.attempt_id
            WHERE attempt.user_id = ?
            ORDER BY review.created_at
            """,
            (student_id,),
        ).fetchall()
    with closing(
        sqlite3.connect(f"file:{adaptive_path.as_posix()}?mode=ro", uri=True)
    ) as adaptive:
        adaptive_student_events = int(
            adaptive.execute(
                "SELECT COUNT(*) FROM learning_events WHERE student_id = ?",
                (student_id,),
            ).fetchone()[0]
        )
    case_rows = [row for row in event_rows if row["event_type"] == "case_stage_assessment"]
    return {
        "required_demo_accounts_present": True,
        "student_event_count": len(event_rows),
        "eligible_event_count": sum(bool(row["long_term_profile_eligible"]) for row in event_rows),
        "adaptive_sent_count": sum(row["adaptive_sync_status"] == "sent" for row in event_rows),
        "case_stage_event_count": len(case_rows),
        "case_stages": sorted(str(row["stage"]) for row in case_rows),
        "subjective_decisions": sorted(str(row["decision"]) for row in decisions),
        "adaptive_student_event_count": adaptive_student_events,
        "student_id": student_id,
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
    semantics = database_semantics(main_db, adaptive_db)
    checks = {
        "main_db_integrity": integrity(main_db) == "ok",
        "adaptive_db_integrity": integrity(adaptive_db) == "ok",
        "synthetic_example_accounts_only": identities["synthetic_only"],
        "demo_user_count_two": identities["user_count"] == 2,
        "required_demo_accounts_present": semantics.get("required_demo_accounts_present") is True,
        "same_student_case_summary": case.get("user_id") == semantics.get("student_id"),
        "main_student_events_six": semantics.get("student_event_count") == 6,
        "main_eligible_events_five": semantics.get("eligible_event_count") == 5,
        "main_adaptive_sent_six": semantics.get("adaptive_sent_count") == 6,
        "case_stage_events_three": semantics.get("case_stage_event_count") == 3,
        "case_stages_lc_inv_pr": semantics.get("case_stages") == ["INV", "LC", "PR"],
        "subjective_revision_and_approval": semantics.get("subjective_decisions")
        == ["approve", "request_revision"],
        "adaptive_student_events_six": semantics.get("adaptive_student_event_count") == 6,
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
        "database_semantics": {
            key: value for key, value in semantics.items() if key != "student_id"
        },
        "checks": checks,
        "passed": all(checks.values()),
    }
    output = (args.output or runtime / "semantic-audit.json").resolve()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
