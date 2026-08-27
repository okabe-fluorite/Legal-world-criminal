from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


class AdaptiveStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        # sqlite3.Connection's context manager commits/rolls back but does not
        # close the handle. Keep ownership explicit so Windows can release the
        # database file immediately after each operation.
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_events (
                    event_id TEXT PRIMARY KEY,
                    student_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_learning_events_student ON learning_events(student_id)"
            )

    def insert(self, payload: dict[str, Any]) -> str:
        event_id = str(payload.get("event_id") or "").strip()
        student_id = str(
            payload.get("student_pseudonym") or payload.get("student_id") or ""
        ).strip()
        if not event_id or not student_id:
            raise ValueError("event_id and student_pseudonym are required")
        digest = payload_hash(payload)
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock, closing(self._connect()) as connection, connection:
            existing = connection.execute(
                "SELECT payload_sha256 FROM learning_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if existing:
                return "duplicate" if existing["payload_sha256"] == digest else "conflict"
            connection.execute(
                """
                INSERT INTO learning_events
                    (event_id, student_id, event_type, payload_sha256, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    student_id,
                    str(payload.get("event_type") or "unknown"),
                    digest,
                    body,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return "inserted"

    def events(self, student_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT payload_json FROM learning_events WHERE student_id = ? ORDER BY created_at, event_id",
                (str(student_id),),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def profile(self, student_id: str) -> dict[str, Any]:
        events = self.events(student_id)
        capability_sum: dict[str, float] = defaultdict(float)
        capability_weight: dict[str, float] = defaultdict(float)
        capability_events: Counter[str] = Counter()
        knowledge_history: dict[str, list[dict[str, str]]] = defaultdict(list)
        errors: Counter[str] = Counter()
        excluded = 0

        for event in events:
            eligibility = event.get("evidence_eligibility") or {}
            if isinstance(eligibility, dict) and eligibility.get("long_term_profile") is False:
                excluded += 1
                continue
            for code, entry in (event.get("capability_scores") or {}).items():
                if not isinstance(entry, dict) or entry.get("score") is None:
                    continue
                score = float(entry["score"])
                weight = float(entry.get("weight") or 1.0)
                capability_sum[str(code)] += score * weight
                capability_weight[str(code)] += weight
                capability_events[str(code)] += 1
            for row in event.get("knowledge_evidence") or []:
                if not isinstance(row, dict):
                    continue
                knowledge_id = str(row.get("knowledge_id") or "").strip()
                if not knowledge_id or str(row.get("normalization_status")) != "canonical":
                    continue
                knowledge_history[knowledge_id].append(
                    {
                        "status": str(row.get("status") or "partial"),
                        "knowledge_name": str(row.get("knowledge_name") or ""),
                        "event_id": str(event.get("event_id") or ""),
                    }
                )
            for tag in event.get("error_tags") or []:
                value = str(tag or "").strip()
                if value:
                    errors[value.split("-")[0]] += 1

        capabilities = {
            code: {
                "mean": round(capability_sum[code] / capability_weight[code], 4),
                "event_count": capability_events[code],
                "evidence_status": "observed",
            }
            for code in sorted(capability_sum)
            if capability_weight[code] > 0
        }
        knowledge = {}
        for knowledge_id, history in knowledge_history.items():
            knowledge[knowledge_id] = {
                "knowledge_name": next(
                    (row["knowledge_name"] for row in reversed(history) if row["knowledge_name"]),
                    "",
                ),
                "latest": history[-1]["status"],
                "event_count": len({row["event_id"] for row in history}),
                "evidence_status": (
                    "provisional" if len({row["event_id"] for row in history}) >= 2 else "insufficient_evidence"
                ),
                "history": history,
            }

        return {
            "schema_version": "edubrain-learner-profile-v2",
            "student_pseudonym": str(student_id),
            "event_count": len(events),
            "eligible_event_count": len(events) - excluded,
            "excluded_event_count": excluded,
            "capabilities": capabilities,
            "knowledge": knowledge,
            "error_tag_counts": dict(errors.most_common()),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "warnings": [
                "case-stage evidence is formative and must not be interpreted as calibrated ORCDF mastery",
                "knowledge status remains insufficient until repeated independent evidence is collected",
            ],
        }
