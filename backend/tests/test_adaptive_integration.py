from __future__ import annotations

import os
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, select
from src.core.database import Base, create_database_engine, create_session_factory, get_db_session
from src.core.models import (
    LearnerProfileRecord,
    LearningEventRecord,
    RecommendationRecord,
    User,
)
from src.integration.adaptive_client import (
    build_adaptive_event,
    get_adaptive_catalog,
    publish_learning_event,
    request_recommendations,
    submit_confusion_annotation,
    submit_task_attempt,
)
from src.integration.event_delivery import deliver_learning_event, persist_adaptive_submission
from src.integration.event_store import persist_learning_event, update_adaptive_delivery
from ws_server import adaptive_evidence_timeline


class FakeResponse:
    content = b"{}"
    status_code = 200

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
            "SIMLAW_ADAPTIVE_ATTEMPTS_PATH",
            "SIMLAW_ADAPTIVE_CONFUSIONS_PATH",
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

    def test_student_evidence_timeline_is_owned_and_omits_response_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            engine = create_database_engine(
                f"sqlite+pysqlite:///{(Path(temp) / 'timeline.db').as_posix()}"
            )
            Base.metadata.create_all(engine)
            factory = create_session_factory(engine)
            with get_db_session(factory) as session:
                student = User(id="timeline-student", email="timeline@example.com")
                other = User(id="timeline-other", email="other-timeline@example.com")
                session.add_all([student, other])
            first = self.event("timeline-student")
            first["event_id"] = "timeline-event"
            first["error_tags"] = ["遗漏构成条件"]
            first["standard_evidence_ids"] = ["EVID_TIMELINE"]
            other_event = self.event("timeline-other")
            other_event["event_id"] = "other-timeline-event"
            persist_learning_event(first, session_factory=factory)
            persist_learning_event(other_event, session_factory=factory)
            with get_db_session(factory) as session:
                student = session.get(User, "timeline-student")
                result = asyncio.run(
                    adaptive_evidence_timeline(current_user=student, session=session)
                )
            engine.dispose()
        self.assertEqual([row["event_id"] for row in result["events"]], ["timeline-event"])
        self.assertEqual(result["events"][0]["error_tags"], ["遗漏构成条件"])
        serialized = str(result)
        self.assertNotIn("timeline-other", serialized)
        self.assertNotIn("source_response_sha256", serialized)

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
        self.assertIn("learning_events", Base.metadata.tables)
        self.assertIn("learner_profiles", Base.metadata.tables)
        self.assertIn("recommendations", Base.metadata.tables)

    def test_sqlite_engine_creates_missing_parent_for_local_first_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database_path = Path(temp) / "nested" / "runtime" / "local.db"
            engine = create_database_engine(
                f"sqlite+pysqlite:///{database_path.as_posix()}"
            )
            try:
                Base.metadata.create_all(engine)
            finally:
                engine.dispose()
            self.assertTrue(database_path.is_file())

    def test_authenticated_identity_overrides_browser_student_for_attempts_and_confusions(self) -> None:
        os.environ.update(
            {
                "SIMLAW_ADAPTIVE_API_BASE_URL": "https://adaptive.example/api/",
                "SIMLAW_ADAPTIVE_API_KEY": "adaptive-secret",
            }
        )
        calls = []

        def post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse({"learning_event": {"event_id": "evt-1"}})

        attempt = submit_task_attempt(
            "authenticated-student",
            {"attempt_id": "a1", "student_pseudonym": "forged-student"},
            post=post,
        )
        confusion = submit_confusion_annotation(
            "authenticated-student",
            {"annotation_id": "c1", "student_pseudonym": "forged-student"},
            post=post,
        )
        self.assertEqual(attempt["status"], "sent")
        self.assertEqual(confusion["status"], "sent")
        self.assertEqual(calls[0][0], "https://adaptive.example/api/attempts")
        self.assertEqual(calls[1][0], "https://adaptive.example/api/confusions")
        self.assertEqual(calls[0][1]["json"]["student_pseudonym"], "authenticated-student")
        self.assertEqual(calls[1][1]["json"]["student_pseudonym"], "authenticated-student")

    def test_adaptive_submission_persists_event_and_sanitized_snapshots(self) -> None:
        engine = create_database_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with get_db_session(factory) as session:
            session.add(User(id="student-1", email="student@example.com"))
        delivery = {
            "status": "sent",
            "error": "",
            "response": {
                "learning_event": {
                    "schema_version": "edubrain-learning-event-v2",
                    "event_id": "evt-attempt-1",
                    "event_type": "task_attempt_assessment",
                    "student_pseudonym": "student-1",
                    "task_id": "task-1",
                    "stage": "prestudy",
                    "source_response_sha256": "b" * 64,
                    "evidence_eligibility": {"long_term_profile": True},
                },
                "feedback": {
                    "correct_options": ["A"],
                    "rationale": "private grading rationale returned only to this response",
                },
                "profile": {
                    "schema_version": "edubrain-learner-profile-v2",
                    "student_pseudonym": "student-1",
                    "knowledge": {},
                },
                "recommendations": [{"task_id": "task-2"}],
                "policy_version": "policy-v1",
            },
        }
        first = persist_adaptive_submission(
            "student-1", delivery, session_factory=factory
        )
        duplicate = persist_adaptive_submission(
            "student-1", delivery, session_factory=factory
        )
        self.assertEqual(first["status"], "inserted")
        self.assertEqual(first["snapshot_status"], "stored")
        self.assertEqual(duplicate["status"], "duplicate")
        with get_db_session(factory) as session:
            event = session.get(LearningEventRecord, "evt-attempt-1")
            profile = session.get(LearnerProfileRecord, "student-1")
            recommendation = session.scalar(select(RecommendationRecord))
            self.assertEqual(event.user_id, "student-1")
            self.assertEqual(event.event_type, "task_attempt_assessment")
            self.assertNotIn("feedback", event.adaptive_response_json)
            self.assertIsNotNone(profile)
            self.assertEqual(
                recommendation.recommendation_json["recommendations"][0]["task_id"],
                "task-2",
            )

    def test_adaptive_submission_rejects_returned_identity_mismatch(self) -> None:
        result = persist_adaptive_submission(
            "student-1",
            {
                "status": "sent",
                "response": {
                    "learning_event": {
                        "event_id": "evt-forged",
                        "student_pseudonym": "student-2",
                    }
                },
            },
        )
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["reason"], "adaptive_student_identity_mismatch")

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
