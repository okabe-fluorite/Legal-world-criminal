from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from edubrain_adaptive.service import AdaptiveService
from edubrain_adaptive.store import AdaptiveStore


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class AdaptiveServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.service = AdaptiveService(
            data_dir=DATA_DIR,
            store=AdaptiveStore(Path(self.temp.name) / "adaptive.db"),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

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

    def test_event_is_idempotent_and_weakness_is_prioritized(self) -> None:
        first = self.service.ingest(self.event())
        second = self.service.ingest(self.event())
        self.assertEqual(first["event_status"], "inserted")
        self.assertEqual(second["event_status"], "duplicate")
        profile = second["profile"]
        self.assertEqual(profile["event_count"], 1)
        self.assertEqual(profile["knowledge"]["CRIM_KP_2DD5C021746121C3"]["latest"], "missing")
        self.assertEqual(
            second["recommendations"][0]["knowledge_id"],
            "CRIM_KP_2DD5C021746121C3",
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
        self.assertEqual(body["recommendations"][0]["reason_code"], "case_evidence_indicates_weakness")
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


if __name__ == "__main__":
    unittest.main()
