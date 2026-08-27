from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .planner import INSTRUCTIONAL_ORDER
from .store import AdaptiveStore


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _event_id(kind: str, student_id: str, client_id: str) -> str:
    digest = _sha256(f"{kind}|{student_id}|{client_id}")[:24]
    return f"evt_{kind}_{digest}"


def _timestamp(value: Any) -> str:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("submitted_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("submitted_at must include a timezone offset")
    return parsed.isoformat()


class AdaptiveService:
    def __init__(self, *, data_dir: Path, store: AdaptiveStore) -> None:
        self.data_dir = Path(data_dir)
        self.store = store
        task_path = self.data_dir / "task_items.jsonl"
        card_path = self.data_dir / "knowledge_cards.jsonl"
        self.uses_governed_contracts = task_path.is_file() and card_path.is_file()
        self.approved = read_jsonl(
            task_path if self.uses_governed_contracts else self.data_dir / "approved_items.jsonl"
        )
        self.q_edges = read_jsonl(self.data_dir / "q_matrix.jsonl")
        self.nodes = read_jsonl(
            card_path if self.uses_governed_contracts else self.data_dir / "knowledge_nodes.jsonl"
        )
        self.item_records = {
            str(row.get("task_id") or row.get("candidate_id")): row
            for row in self.approved
        }
        self.item_to_knowledge = {
            str(row["item_id"]): str(row["knowledge_id"]) for row in self.q_edges
        }
        self.knowledge_by_id = {
            str(row["knowledge_id"]): row for row in self.nodes
        }
        self.items_by_knowledge: dict[str, list[str]] = defaultdict(list)
        for item_id, knowledge_id in self.item_to_knowledge.items():
            if item_id in self.item_records:
                self.items_by_knowledge[knowledge_id].append(item_id)

    def profile(self, student_id: str) -> dict[str, Any]:
        return self.store.profile(student_id)

    def recommendations(
        self,
        student_id: str,
        *,
        limit: int = 10,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        profile = self.profile(student_id)
        attempted = {
            str(value)
            for value in ((context or {}).get("attempted_item_ids") or [])
        }
        attempted.update(
            str(event.get("task_id") or "")
            for event in self.store.events(student_id)
            if str(event.get("event_type") or "") == "task_attempt_assessment"
        )
        attempted.discard("")
        confusions = profile.get("confusions") or {}
        selected = []
        candidates = set(self.item_records) - attempted
        selected_by_knowledge: defaultdict[str, int] = defaultdict(int)

        while candidates and len(selected) < max(1, min(int(limit), 30)):
            scored = []
            for item_id in candidates:
                knowledge_id = self.item_to_knowledge[item_id]
                node = self.knowledge_by_id[knowledge_id]
                name = str(node["canonical_name"])
                state = (profile.get("knowledge") or {}).get(knowledge_id) or {}
                latest = str(state.get("latest") or "")
                status = str(state.get("evidence_status") or "insufficient_evidence")
                if latest == "missing":
                    base, reason = 145.0, "case_evidence_indicates_weakness"
                elif latest == "partial":
                    base, reason = 120.0, "case_evidence_requires_reinforcement"
                elif latest == "mastered" and status == "provisional":
                    base, reason = 45.0, "provisional_mastery_spaced_review"
                elif state:
                    base, reason = 105.0, "insufficient_repeated_evidence"
                else:
                    base, reason = 100.0, "no_evidence_collect_diagnostic"
                if knowledge_id in confusions and base < 135.0:
                    base, reason = 135.0, "learner_reported_confusion"
                order = INSTRUCTIONAL_ORDER.get(name, 99)
                score = base - order * 2.5 - selected_by_knowledge[knowledge_id] * 35
                scored.append((score, -order, item_id, knowledge_id, reason))
            score, _order, item_id, knowledge_id, reason = max(scored)
            candidates.remove(item_id)
            selected_by_knowledge[knowledge_id] += 1
            record = self.item_records[item_id]
            item = record if self.uses_governed_contracts else record["item"]
            selected.append(
                {
                    "rank": len(selected) + 1,
                    "task_id": item_id,
                    "item_id": item_id,
                    "task_type": "diagnostic_item",
                    "knowledge_id": knowledge_id,
                    "knowledge_name": self.knowledge_by_id[knowledge_id]["canonical_name"],
                    "stem": item["stem"],
                    "options": item["options"],
                    "difficulty": item.get("difficulty", 2),
                    "cognitive_dimension": item.get("cognitive_dimension", ""),
                    "reason_code": reason,
                    "score": round(score, 4),
                    "answer_included": False,
                    "content_version": str(item.get("content_sha256") or ""),
                    "standard_evidence_ids": list(item.get("standard_evidence_ids") or []),
                }
            )
        return selected

    def submit_attempt(self, payload: dict[str, Any]) -> dict[str, Any]:
        student_id = str(payload.get("student_pseudonym") or "").strip()
        attempt_id = str(payload.get("attempt_id") or "").strip()
        task_id = str(payload.get("task_id") or "").strip()
        phase = str(payload.get("phase") or "").strip()
        if not student_id or not attempt_id:
            raise ValueError("student_pseudonym and attempt_id are required")
        task = self.item_records.get(task_id)
        if task is None:
            raise ValueError("unknown task_id")
        if phase not in set(task.get("phase_eligibility") or []):
            raise ValueError("task is not eligible for this phase")
        content_version = str(payload.get("content_version") or "").strip()
        if content_version != str(task.get("content_sha256") or ""):
            raise ValueError("task content_version is stale or invalid")

        valid_options = {str(value).upper() for value in (task.get("options") or {})}
        selected = sorted(
            {str(value).strip().upper() for value in payload.get("selected_options") or []}
        )
        if not selected or not set(selected).issubset(valid_options):
            raise ValueError("selected_options must contain only options from the task")
        expected = sorted({str(value).upper() for value in task["answer_private"]})
        correct = selected == expected
        overlap = bool(set(selected) & set(expected))
        knowledge_status = "mastered" if correct else ("partial" if overlap else "missing")
        score = float(task["scoring_rule"]["max_score"]) if correct else 0.0
        hint_count = int(payload.get("hint_count") or 0)
        answer_revealed = bool(payload.get("answer_revealed_before_submit"))
        difficulty_weight = {1: 0.8, 2: 1.0, 3: 1.2}.get(int(task.get("difficulty") or 2), 1.0)
        evidence_weight = 0.0 if answer_revealed else max(0.25, difficulty_weight * (1 - 0.15 * hint_count))
        submitted_at = _timestamp(payload.get("submitted_at"))

        triggered = []
        if not correct:
            for misconception in task.get("misconceptions_private") or []:
                triggers = {str(value).upper() for value in misconception.get("trigger_options") or []}
                if triggers & set(selected):
                    description = str(misconception.get("description") or "").strip()
                    if description:
                        triggered.append(description)

        response_hash = _sha256(
            json.dumps(selected, ensure_ascii=False, separators=(",", ":"))
        )
        event = {
            "schema_version": "edubrain-learning-event-v2",
            "event_id": _event_id("attempt", student_id, attempt_id),
            "event_type": "task_attempt_assessment",
            "student_pseudonym": student_id,
            "course_id": str(payload.get("course_id") or "undergraduate-criminal-law"),
            "attempt_id": attempt_id,
            "task_id": task_id,
            "phase": phase,
            "stage": phase,
            "task_version": content_version,
            "source_response_sha256": response_hash,
            "response": {
                "selected_options": selected,
                "response_time_ms": int(payload.get("response_time_ms") or 0),
                "confidence": payload.get("confidence"),
            },
            "grading": {
                "rule": "exact_option_set",
                "score": score,
                "max_score": float(task["scoring_rule"]["max_score"]),
                "correct": correct,
                "knowledge_status": knowledge_status,
            },
            "capability_scores": {
                str(code): {
                    "score": score,
                    "weight": round(evidence_weight, 4),
                    "source": "deterministic_task_attempt",
                    "unverified": False,
                }
                for code in task.get("target_abilities") or []
            },
            "knowledge_evidence": [
                {
                    "knowledge_id": str(knowledge_id),
                    "knowledge_name": str(task.get("knowledge_name") or ""),
                    "normalization_status": "canonical",
                    "status": knowledge_status,
                    "evidence_weight": round(evidence_weight, 4),
                    "reason": "deterministic exact-option-set grading",
                }
                for knowledge_id in task.get("knowledge_ids") or []
            ],
            "error_tags": [f"task_misconception-{value}" for value in triggered],
            "assist": {
                "hint_count": hint_count,
                "answer_revealed_before_submit": answer_revealed,
            },
            "evidence_eligibility": {
                "long_term_profile": not answer_revealed,
                "reason": (
                    "answer_revealed_before_submit"
                    if answer_revealed
                    else "independent_or_hint_adjusted_task_attempt"
                ),
            },
            "standard_evidence_ids": list(task.get("standard_evidence_ids") or []),
            "scored_at": submitted_at,
            "source_schema_version": "criminal-law-task-attempt-v1",
        }
        event_status = self.store.insert(event)
        if event_status == "conflict":
            return {
                "schema_version": "edubrain-task-attempt-response-v1",
                "attempt_status": "conflict",
                "attempt_id": attempt_id,
                "error_code": "attempt_id_payload_conflict",
            }
        profile = self.profile(student_id)
        recommendations = self.recommendations(student_id, limit=10)
        return {
            "schema_version": "edubrain-task-attempt-response-v1",
            "attempt_status": event_status,
            "attempt_id": attempt_id,
            "learning_event": event,
            "feedback": {
                "correct": correct,
                "score": score,
                "max_score": float(task["scoring_rule"]["max_score"]),
                "correct_options": expected,
                "rationale": str(task.get("rationale_private") or ""),
                "triggered_misconceptions": triggered,
                "knowledge_status": knowledge_status,
                "standard_evidence_ids": list(task.get("standard_evidence_ids") or []),
            },
            "profile": profile,
            "recommendations": recommendations,
            "policy_version": "hybrid-case-evidence-cold-start-v1",
        }

    def annotate_confusion(self, payload: dict[str, Any]) -> dict[str, Any]:
        student_id = str(payload.get("student_pseudonym") or "").strip()
        annotation_id = str(payload.get("annotation_id") or "").strip()
        task_id = str(payload.get("task_id") or "").strip()
        knowledge_id = str(payload.get("knowledge_id") or "").strip()
        if not student_id or not annotation_id:
            raise ValueError("student_pseudonym and annotation_id are required")
        task = self.item_records.get(task_id) if task_id else None
        if task_id and task is None:
            raise ValueError("unknown task_id")
        if task:
            task_knowledge = str((task.get("knowledge_ids") or [""])[0])
            if knowledge_id and knowledge_id != task_knowledge:
                raise ValueError("knowledge_id does not match task_id")
            knowledge_id = task_knowledge
        if knowledge_id not in self.knowledge_by_id:
            raise ValueError("a canonical knowledge_id or task_id is required")
        knowledge = self.knowledge_by_id[knowledge_id]
        submitted_at = _timestamp(payload.get("submitted_at"))
        note = str(payload.get("note") or "").strip()
        event = {
            "schema_version": "edubrain-learning-event-v2",
            "event_id": _event_id("confusion", student_id, annotation_id),
            "event_type": "confusion_annotation",
            "student_pseudonym": student_id,
            "course_id": str(payload.get("course_id") or "undergraduate-criminal-law"),
            "annotation_id": annotation_id,
            "task_id": task_id,
            "phase": str(payload.get("phase") or "prestudy"),
            "stage": str(payload.get("phase") or "prestudy"),
            "source_response_sha256": _sha256(note),
            "capability_scores": {},
            "knowledge_evidence": [],
            "confusion_annotations": [
                {
                    "knowledge_id": knowledge_id,
                    "knowledge_name": str(knowledge.get("canonical_name") or ""),
                    "confusion_type": str(payload.get("confusion_type") or "other"),
                    "note": note,
                    "request_help": bool(payload.get("request_help", True)),
                }
            ],
            "error_tags": [],
            "assist": {},
            "evidence_eligibility": {
                "long_term_profile": False,
                "reason": "self_report_not_mastery_evidence",
            },
            "scored_at": submitted_at,
            "source_schema_version": "criminal-law-confusion-annotation-v1",
        }
        event_status = self.store.insert(event)
        if event_status == "conflict":
            return {
                "schema_version": "edubrain-confusion-response-v1",
                "annotation_status": "conflict",
                "annotation_id": annotation_id,
                "error_code": "annotation_id_payload_conflict",
            }
        profile = self.profile(student_id)
        return {
            "schema_version": "edubrain-confusion-response-v1",
            "annotation_status": event_status,
            "annotation_id": annotation_id,
            "learning_event": event,
            "profile": profile,
            "recommendations": self.recommendations(student_id, limit=10),
            "policy_version": "hybrid-case-evidence-cold-start-v1",
        }

    def ingest(self, event: dict[str, Any]) -> dict[str, Any]:
        status = self.store.insert(event)
        student_id = str(
            event.get("student_pseudonym") or event.get("student_id") or ""
        ).strip()
        profile = self.profile(student_id)
        recommendations = self.recommendations(student_id, limit=10)
        return {
            "schema_version": "edubrain-adaptive-event-response-v1",
            "event_status": status,
            "profile": profile,
            "recommendations": recommendations,
            "policy_version": "hybrid-case-evidence-cold-start-v1",
        }
