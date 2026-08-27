from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from sqlalchemy import func, select
from src.core.database import Base, create_database_engine, create_session_factory, get_db_session
from src.core.models import LearnerProfileRecord, RecommendationRecord, User
from src.integration.adaptive_client import (
    build_adaptive_event,
    get_adaptive_catalog,
    publish_learning_event,
    request_recommendations,
)
from src.integration.event_delivery import deliver_learning_event
from src.integration.event_store import persist_learning_event, update_adaptive_delivery


class FakeResponse:
    content = b"{}"

    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class AdaptiveIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.keys = {
            "SIMLAW_ADAPTIVE_API_BASE_URL",
            "SIMLAW_ADAPTIVE_API_KEY",
            "SIMLAW_ADAPTIVE_EVENTS_PATH",
            "SIMLAW_ADAPTIVE_RECOMMEND_PATH",
            "SIMLAW_ADAPTIVE_TIMEOUT_SECONDS",
        }
        self.original = {key: os.environ.get(key) for key in self.keys}
        for key in self.keys:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key in self.keys:
            os.environ.pop(key, None)
        for key, value in self.original.items():
            if value is not None:
                os.environ[key] = value

    @staticmethod
    def event(user_id: str = "student-1") -> dict:
        return {
            "event_id": "evt-1",
            "schema_version": "learning-event-v2",
            "event_type": "case_stage_assessment",
            "student_id": user_id,
            "case_id": "case_1",
            "stage": "DS",
            "task_id": "case:case_1:DS",
            "source_response_sha256": "a" * 64,
            "capability_scores": {"subsumption": {"score": 0.6, "weight": 1.0}},
            "knowledge_verdicts": [
                {"kp": "正当防卫", "status": "partial", "reason": "遗漏时间条件"}
            ],
            "evidence_eligibility": {"long_term_profile": True},
        }

    def test_free_form_knowledge_is_marked_unmapped(self) -> None:
        payload = build_adaptive_event(self.event())
        evidence = payload["knowledge_evidence"][0]
        self.assertTrue(evidence["knowledge_id"].startswith("unmapped:"))
        self.assertEqual(evidence["normalization_status"], "unmapped")

    def test_event_and_recommendation_http_contracts(self) -> None:
        os.environ.update(
            {
                "SIMLAW_ADAPTIVE_API_BASE_URL": "https://adaptive.example/api/",
                "SIMLAW_ADAPTIVE_API_KEY": "adaptive-secret",
            }
        )
        calls = []

        def post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse({"recommendations": [{"task_id": "q1"}]})

        sent = publish_learning_event(self.event(), post=post)
        recommended = request_recommendations("student-1", post=post)
        self.assertEqual(sent["status"], "sent")
        self.assertEqual(recommended["status"], "sent")
        self.assertEqual(calls[0][0], "https://adaptive.example/api/events")
        self.assertEqual(calls[1][0], "https://adaptive.example/api/recommend")
        self.assertEqual(calls[0][1]["headers"]["Authorization"], "Bearer adaptive-secret")
        self.assertNotIn("adaptive-secret", repr(get_adaptive_catalog()))

    def test_learning_event_store_is_idempotent_and_immutable(self) -> None:
        engine = create_database_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with get_db_session(factory) as session:
            session.add(User(id="student-1", email="student@example.com"))

        event = self.event()
        inserted = persist_learning_event(event, session_factory=factory)
        duplicate = persist_learning_event(event, session_factory=factory)
        modified = dict(event)
        modified["stage"] = "CR"
        conflict = persist_learning_event(modified, session_factory=factory)
        self.assertEqual(inserted["status"], "inserted")
        self.assertEqual(duplicate["status"], "duplicate")
        self.assertEqual(conflict["status"], "conflict")
        self.assertEqual(len(Base.metadata.tables), 9)

    def test_adaptive_response_upserts_profile_and_one_recommendation_per_event(self) -> None:
        engine = create_database_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with get_db_session(factory) as session:
            session.add(User(id="student-1", email="student@example.com"))
        event = self.event()
        persist_learning_event(event, session_factory=factory)
        response = {
            "status": "sent",
            "error": "",
            "response": {
                "profile": {
                    "schema_version": "edubrain-learner-profile-v2",
                    "student_pseudonym": "student-1",
                    "knowledge": {},
                },
                "recommendations": [{"task_id": "q1"}],
                "policy_version": "policy-v1",
            },
        }
        update_adaptive_delivery("evt-1", response, session_factory=factory)
        response["response"]["recommendations"] = [{"task_id": "q2"}]
        update_adaptive_delivery("evt-1", response, session_factory=factory)
        with get_db_session(factory) as session:
            profile = session.get(LearnerProfileRecord, "student-1")
            recommendation = session.scalar(select(RecommendationRecord))
            recommendation_count = session.scalar(
                select(func.count()).select_from(RecommendationRecord)
            )
            self.assertIsNotNone(profile)
            self.assertEqual(profile.source, "edubrain_adaptive_service")
            self.assertEqual(recommendation_count, 1)
            self.assertEqual(
                recommendation.recommendation_json["recommendations"][0]["task_id"],
                "q2",
            )

    def test_conflicting_local_event_is_not_delivered(self) -> None:
        with patch(
            "src.integration.event_delivery.persist_learning_event",
            return_value={"status": "conflict"},
        ), patch("src.integration.event_delivery.publish_learning_event") as publish, patch(
            "src.integration.event_delivery.update_adaptive_delivery"
        ):
            result = deliver_learning_event(self.event())
        publish.assert_not_called()
        self.assertEqual(result["adaptive"]["status"], "not_sent")


if __name__ == "__main__":
    unittest.main()
