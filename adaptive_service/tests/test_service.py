from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from edubrain_adaptive.service import AdaptiveService
from edubrain_adaptive.store import AdaptiveStore


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"


class AdaptiveServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.service = AdaptiveService(
            data_dir=DATA_DIR,
            store=AdaptiveStore(Path(self.temp.name) / "adaptive.db"),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def attempt(self, **overrides) -> dict:
        task = self.service.approved[0]
        payload = {
            "schema_version": "criminal-law-task-attempt-v1",
            "attempt_id": "attempt-1",
            "student_pseudonym": "student-attempt",
            "course_id": "undergraduate-criminal-law",
            "task_id": task["task_id"],
            "content_version": task["content_sha256"],
            "phase": "prestudy",
            "selected_options": list(task["answer_private"]),
            "submitted_at": datetime(2026, 8, 27, 8, 0, tzinfo=timezone.utc).isoformat(),
            "response_time_ms": 12000,
            "confidence": 4,
            "hint_count": 0,
            "answer_revealed_before_submit": False,
        }
        payload.update(overrides)
        return payload

    @staticmethod
    def event(status: str = "missing") -> dict:
        return {
            "schema_version": "edubrain-learning-event-v2",
            "event_id": "evt-1",
            "event_type": "case_stage_assessment",
            "student_pseudonym": "student-1",
            "case_id": "case_1",
            "stage": "DS",
            "capability_scores": {
                "subsumption": {"score": 0.55, "weight": 1.0, "source": "judge"}
            },
            "knowledge_evidence": [
                {
                    "knowledge_id": "CRIM_KP_2DD5C021746121C3",
                    "knowledge_name": "故意、过失与意外事件",
                    "normalization_status": "canonical",
                    "status": status,
                }
            ],
            "error_tags": ["遗漏主观要件"],
            "evidence_eligibility": {"long_term_profile": True},
        }

    def test_cold_start_covers_all_ten_knowledge_points_without_answers(self) -> None:
        rows = self.service.recommendations("new-student", limit=10)
        self.assertEqual(len(rows), 10)
        self.assertEqual(len({row["knowledge_id"] for row in rows}), 10)
        self.assertTrue(all(row["answer_included"] is False for row in rows))
        self.assertTrue(all("answer" not in row for row in rows))

    def test_event_is_idempotent_and_unmet_prerequisite_is_prioritized(self) -> None:
        first = self.service.ingest(self.event())
        second = self.service.ingest(self.event())
        self.assertEqual(first["event_status"], "inserted")
        self.assertEqual(second["event_status"], "duplicate")
        profile = second["profile"]
        self.assertEqual(profile["event_count"], 1)
        self.assertEqual(profile["knowledge"]["CRIM_KP_2DD5C021746121C3"]["latest"], "missing")
        recommendation = second["recommendations"][0]
        self.assertEqual(recommendation["knowledge_id"], "CRIM_KP_467B1D9FCFABDA50")
        self.assertEqual(recommendation["reason_code"], "prerequisite_for_observed_gap")
        self.assertEqual(recommendation["path_action"], "diagnose_or_reinforce_prerequisite")
        self.assertIn(
            "CRIM_KP_2DD5C021746121C3",
            recommendation["supports_target_knowledge_ids"],
        )
        self.assertEqual(
            recommendation["prerequisite_path_names"][0],
            ["罪刑法定原则", "犯罪概念与但书", "故意、过失与意外事件"],
        )

    def test_prerequisite_frontier_advances_after_three_events_across_two_tasks(self) -> None:
        self.service.ingest(self.event())
        root_id = "CRIM_KP_467B1D9FCFABDA50"
        root_tasks = [task for task in self.service.approved if task["knowledge_ids"] == [root_id]]
        self.assertGreaterEqual(len(root_tasks), 2)
        for index, task in enumerate((root_tasks[0], root_tasks[1], root_tasks[0]), start=1):
            self.service.submit_attempt(
                self.attempt(
                    attempt_id=f"root-ready-{index}",
                    student_pseudonym="student-1",
                    task_id=task["task_id"],
                    content_version=task["content_sha256"],
                    selected_options=task["answer_private"],
                )
            )
        root_state = self.service.profile("student-1")["knowledge"][root_id]
        self.assertEqual(root_state["latest"], "mastered")
        self.assertEqual(root_state["evidence_status"], "provisional")
        recommendation = self.service.recommendations("student-1", limit=1)[0]
        self.assertEqual(recommendation["knowledge_id"], "CRIM_KP_BC82753EB8088C13")
        self.assertEqual(
            recommendation["prerequisite_path_names"][0],
            ["犯罪概念与但书", "故意、过失与意外事件"],
        )

    def test_ai_drafted_event_is_excluded_from_profile(self) -> None:
        event = self.event()
        event["event_id"] = "evt-draft"
        event["evidence_eligibility"] = {"long_term_profile": False}
        result = self.service.ingest(event)
        self.assertEqual(result["profile"]["eligible_event_count"], 0)
        self.assertEqual(result["profile"]["excluded_event_count"], 1)
        self.assertEqual(result["profile"]["capabilities"], {})
        self.assertEqual(result["profile"]["knowledge"], {})

    def test_same_event_id_with_changed_payload_conflicts(self) -> None:
        self.assertEqual(self.service.store.insert(self.event()), "inserted")
        changed = self.event(status="mastered")
        self.assertEqual(self.service.store.insert(changed), "conflict")

    def test_task_attempt_is_privately_graded_idempotent_and_excludes_attempted_task(self) -> None:
        payload = self.attempt()
        schema = json.loads((SCHEMA_DIR / "task-attempt-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(payload)
        first = self.service.submit_attempt(payload)
        duplicate = self.service.submit_attempt(payload)
        self.assertEqual(first["attempt_status"], "inserted")
        self.assertEqual(duplicate["attempt_status"], "duplicate")
        self.assertTrue(first["feedback"]["correct"])
        self.assertEqual(first["learning_event"]["grading"]["score"], 1.0)
        self.assertNotIn(payload["task_id"], {row["task_id"] for row in first["recommendations"]})
        knowledge_id = self.service.approved[0]["knowledge_ids"][0]
        knowledge = first["profile"]["knowledge"][knowledge_id]
        self.assertEqual(knowledge["latest"], "mastered")
        self.assertEqual(knowledge["task_count"], 1)
        self.assertEqual(knowledge["evidence_status"], "insufficient_evidence")

        def keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key
                    yield from keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from keys(child)

        self.assertTrue(
            {"answer_private", "rationale_private", "misconceptions_private"}.isdisjoint(
                set(keys(first))
            )
        )

        wrong = next(
            option
            for option in self.service.approved[0]["options"]
            if option not in self.service.approved[0]["answer_private"]
        )
        conflict = self.service.submit_attempt(
            self.attempt(selected_options=[wrong])
        )
        self.assertEqual(conflict["attempt_status"], "conflict")
        self.assertEqual(self.service.profile("student-attempt")["event_count"], 1)

    def test_answer_revealed_attempt_is_feedback_only(self) -> None:
        result = self.service.submit_attempt(
            self.attempt(
                attempt_id="attempt-revealed",
                student_pseudonym="student-revealed",
                answer_revealed_before_submit=True,
            )
        )
        self.assertEqual(result["profile"]["eligible_event_count"], 0)
        self.assertEqual(result["profile"]["excluded_event_count"], 1)
        self.assertEqual(result["profile"]["knowledge"], {})

    def test_selecting_correct_and_wrong_options_is_missing_not_partial(self) -> None:
        task = self.service.approved[0]
        selected = list(task["answer_private"])
        selected.append(next(value for value in task["options"] if value not in selected))
        result = self.service.submit_attempt(
            self.attempt(
                attempt_id="attempt-overselect",
                student_pseudonym="student-overselect",
                selected_options=selected,
            )
        )
        self.assertFalse(result["feedback"]["correct"])
        self.assertEqual(result["feedback"]["knowledge_status"], "missing")
        knowledge_id = task["knowledge_ids"][0]
        self.assertEqual(result["profile"]["knowledge"][knowledge_id]["latest"], "missing")

    def test_provisional_knowledge_requires_three_events_and_two_distinct_tasks(self) -> None:
        knowledge_id = self.service.approved[0]["knowledge_ids"][0]
        tasks = [
            task for task in self.service.approved if task["knowledge_ids"] == [knowledge_id]
        ]
        self.assertEqual(len(tasks), 3)
        first_task = tasks[0]
        first = self.service.submit_attempt(
            self.attempt(
                attempt_id="evidence-1",
                student_pseudonym="student-threshold",
                task_id=first_task["task_id"],
                content_version=first_task["content_sha256"],
                selected_options=first_task["answer_private"],
            )
        )
        self.assertEqual(
            first["profile"]["knowledge"][knowledge_id]["evidence_status"],
            "insufficient_evidence",
        )
        second_task = tasks[1]
        second = self.service.submit_attempt(
            self.attempt(
                attempt_id="evidence-2",
                student_pseudonym="student-threshold",
                task_id=second_task["task_id"],
                content_version=second_task["content_sha256"],
                selected_options=second_task["answer_private"],
            )
        )
        self.assertEqual(
            second["profile"]["knowledge"][knowledge_id]["evidence_status"],
            "insufficient_evidence",
        )
        third_task = tasks[0]
        third = self.service.submit_attempt(
            self.attempt(
                attempt_id="evidence-3",
                student_pseudonym="student-threshold",
                task_id=third_task["task_id"],
                content_version=third_task["content_sha256"],
                selected_options=third_task["answer_private"],
            )
        )
        state = third["profile"]["knowledge"][knowledge_id]
        self.assertEqual(state["event_count"], 3)
        self.assertEqual(state["task_count"], 2)
        self.assertEqual(state["evidence_status"], "provisional")

    def test_confusion_is_a_self_report_not_negative_mastery_evidence(self) -> None:
        task = self.service.approved[0]
        payload = {
            "schema_version": "criminal-law-confusion-annotation-v1",
            "annotation_id": "confusion-1",
            "student_pseudonym": "student-confused",
            "course_id": "undergraduate-criminal-law",
            "phase": "prestudy",
            "task_id": task["task_id"],
            "knowledge_id": task["knowledge_ids"][0],
            "confusion_type": "fact_application",
            "note": "我不能区分当场胁迫与事后要挟。",
            "request_help": True,
            "submitted_at": datetime(2026, 8, 27, 8, 5, tzinfo=timezone.utc).isoformat(),
        }
        schema = json.loads(
            (SCHEMA_DIR / "confusion-annotation-v1.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator(schema).validate(payload)
        first = self.service.annotate_confusion(payload)
        duplicate = self.service.annotate_confusion(payload)
        self.assertEqual(first["annotation_status"], "inserted")
        self.assertEqual(duplicate["annotation_status"], "duplicate")
        profile = first["profile"]
        self.assertEqual(profile["self_report_event_count"], 1)
        self.assertEqual(profile["knowledge"], {})
        self.assertEqual(profile["confusions"][task["knowledge_ids"][0]]["count"], 1)
        self.assertEqual(first["recommendations"][0]["knowledge_id"], task["knowledge_ids"][0])
        self.assertEqual(first["recommendations"][0]["reason_code"], "learner_reported_confusion")
        changed = dict(payload)
        changed["note"] = "同一个ID但内容发生变化。"
        self.assertEqual(
            self.service.annotate_confusion(changed)["annotation_status"],
            "conflict",
        )


class AdaptiveApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        from edubrain_adaptive import api

        self.api = api
        self.previous_db_path = api.DB_PATH
        self.previous_data_dir = api.DATA_DIR
        api.DB_PATH = Path(self.temp.name) / "adaptive-api.db"
        api.DATA_DIR = DATA_DIR
        api.get_service.cache_clear()
        self.key_patch = patch.dict(
            os.environ, {"SIMLAW_ADAPTIVE_API_KEY": "test-adaptive-key"}
        )
        self.key_patch.start()
        self.client = TestClient(api.app)

    def tearDown(self) -> None:
        self.client.close()
        self.api.get_service.cache_clear()
        self.api.DB_PATH = self.previous_db_path
        self.api.DATA_DIR = self.previous_data_dir
        self.key_patch.stop()
        self.temp.cleanup()

    @staticmethod
    def event() -> dict:
        return AdaptiveServiceTests.event()

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": "Bearer test-adaptive-key"}

    def test_health_and_authentication_contract(self) -> None:
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["items"], 30)
        self.assertEqual(health.json()["knowledge_points"], 10)
        self.assertTrue(health.json()["governed_contracts"])
        self.assertEqual(self.client.post("/events", json=self.event()).status_code, 401)

    def test_event_and_recommendation_http_contract(self) -> None:
        first = self.client.post("/events", json=self.event(), headers=self.auth)
        duplicate = self.client.post("/events", json=self.event(), headers=self.auth)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["event_status"], "inserted")
        self.assertEqual(duplicate.json()["event_status"], "duplicate")
        response = self.client.post(
            "/recommend",
            headers=self.auth,
            json={"student_pseudonym": "student-1", "limit": 3},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["recommendations"]), 3)
        self.assertEqual(body["recommendations"][0]["reason_code"], "prerequisite_for_observed_gap")
        self.assertEqual(body["recommendations"][0]["path_action"], "diagnose_or_reinforce_prerequisite")
        self.assertTrue(all(row["answer_included"] is False for row in body["recommendations"]))
        self.assertTrue(all(row["standard_evidence_ids"] for row in body["recommendations"]))
        def keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key
                    yield from keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from keys(child)

        self.assertTrue(
            {"answer", "answer_private", "rationale_private"}.isdisjoint(set(keys(body)))
        )

    def test_attempt_and_confusion_http_contracts(self) -> None:
        task = self.api.get_service().approved[0]
        attempt = {
            "attempt_id": "api-attempt-1",
            "student_pseudonym": "api-student",
            "task_id": task["task_id"],
            "content_version": task["content_sha256"],
            "phase": "review",
            "selected_options": task["answer_private"],
            "submitted_at": "2026-08-27T08:00:00+00:00",
        }
        first = self.client.post("/attempts", json=attempt, headers=self.auth)
        duplicate = self.client.post("/attempts", json=attempt, headers=self.auth)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["attempt_status"], "inserted")
        self.assertEqual(duplicate.json()["attempt_status"], "duplicate")
        wrong = next(value for value in task["options"] if value not in task["answer_private"])
        changed = {**attempt, "selected_options": [wrong]}
        self.assertEqual(
            self.client.post("/attempts", json=changed, headers=self.auth).status_code,
            409,
        )

        confusion = {
            "annotation_id": "api-confusion-1",
            "student_pseudonym": "api-student",
            "phase": "review",
            "task_id": task["task_id"],
            "confusion_type": "rule_understanding",
            "note": "我不确定规范条件如何适用。",
            "submitted_at": "2026-08-27T08:05:00+00:00",
        }
        response = self.client.post("/confusions", json=confusion, headers=self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["annotation_status"], "inserted")
        self.assertEqual(response.json()["profile"]["self_report_event_count"], 1)


if __name__ == "__main__":
    unittest.main()
