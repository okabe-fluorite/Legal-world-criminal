from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.database import Base, create_database_engine, create_session_factory, get_db_session
from src.core.models import LearnerProfileRecord, LearningEventRecord, User
from src.core.role_service import grant_user_role, resolve_user_role
from src.teacher.routes import create_teacher_router
from src.teacher.service import (
    TeacherConflictError,
    TeacherPermissionError,
    TeacherService,
)


class TeacherServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        database_path = (Path(self.temp.name) / "teacher-tests.db").as_posix()
        self.engine = create_database_engine(f"sqlite+pysqlite:///{database_path}")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)
        with get_db_session(self.factory) as session:
            self.teacher = User(id="teacher-1", email="teacher@example.com")
            self.other_teacher = User(id="teacher-2", email="other-teacher@example.com")
            self.student = User(id="student-1", email="student@example.com")
            session.add_all([self.teacher, self.other_teacher, self.student])
            session.flush()
            grant_user_role(
                session=session,
                user=self.teacher,
                role="teacher",
                granted_by="test",
            )
            grant_user_role(
                session=session,
                user=self.other_teacher,
                role="teacher",
                granted_by="test",
            )
        self.service = TeacherService(min_aggregate_size=1)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.temp.cleanup()

    def _users(self, session):
        return (
            session.get(User, "teacher-1"),
            session.get(User, "teacher-2"),
            session.get(User, "student-1"),
        )

    def _create_class_and_enroll(self) -> str:
        with get_db_session(self.factory) as session:
            teacher, _other, _student = self._users(session)
            created = self.service.create_class(
                session=session,
                teacher=teacher,
                course_id="undergraduate-criminal-law",
                name="刑法甲班",
                term="2026秋",
            )
            class_id = created["classroom"]["class_id"]
            enrolled = self.service.enroll_student(
                session=session,
                teacher=teacher,
                class_id=class_id,
                student_email="student@example.com",
            )
            duplicate = self.service.enroll_student(
                session=session,
                teacher=teacher,
                class_id=class_id,
                student_email="student@example.com",
            )
            self.assertEqual(enrolled["enrollment_status"], "inserted")
            self.assertEqual(duplicate["enrollment_status"], "duplicate")
            self.assertTrue(enrolled["student_ref"].startswith("student-"))
            self.assertNotIn("student@example.com", json.dumps(enrolled))
            return class_id

    def test_role_is_not_browser_self_declared_and_student_is_denied(self) -> None:
        with get_db_session(self.factory) as session:
            teacher, _other, student = self._users(session)
            self.assertEqual(resolve_user_role(session=session, user=teacher), "teacher")
            self.assertEqual(resolve_user_role(session=session, user=student), "student")
            with self.assertRaises(TeacherPermissionError):
                self.service.list_classes(session=session, teacher=student)

        previous = os.environ.get("SIMLAW_TEACHER_EMAILS")
        try:
            os.environ["SIMLAW_TEACHER_EMAILS"] = "allowlisted@example.com"
            with get_db_session(self.factory) as session:
                allowlisted = User(id="teacher-env", email="allowlisted@example.com")
                session.add(allowlisted)
                session.flush()
                self.assertEqual(
                    resolve_user_role(session=session, user=allowlisted), "teacher"
                )
        finally:
            if previous is None:
                os.environ.pop("SIMLAW_TEACHER_EMAILS", None)
            else:
                os.environ["SIMLAW_TEACHER_EMAILS"] = previous

    def test_class_analytics_are_owned_aggregated_and_hide_raw_notes(self) -> None:
        class_id = self._create_class_and_enroll()
        knowledge = self.service.knowledge.cards[0]
        with get_db_session(self.factory) as session:
            session.add_all(
                [
                    LearningEventRecord(
                        event_id="evt-attempt",
                        user_id="student-1",
                        schema_version="edubrain-learning-event-v2",
                        event_type="task_attempt_assessment",
                        case_id="",
                        stage="prestudy",
                        task_id="task-1",
                        source_response_sha256="a" * 64,
                        payload_sha256="b" * 64,
                        long_term_profile_eligible=True,
                        payload_json={},
                    ),
                    LearningEventRecord(
                        event_id="evt-confusion",
                        user_id="student-1",
                        schema_version="edubrain-learning-event-v2",
                        event_type="confusion_annotation",
                        case_id="",
                        stage="prestudy",
                        task_id="task-1",
                        source_response_sha256="c" * 64,
                        payload_sha256="d" * 64,
                        long_term_profile_eligible=False,
                        payload_json={"note": "raw private confusion note must not leak"},
                    ),
                    LearnerProfileRecord(
                        user_id="student-1",
                        schema_version="edubrain-learner-profile-v2",
                        source="adaptive_service",
                        profile_json={
                            "knowledge": {
                                knowledge["knowledge_id"]: {
                                    "knowledge_name": knowledge["canonical_name"],
                                    "latest": "missing",
                                    "evidence_status": "insufficient_evidence",
                                }
                            },
                            "confusions": {
                                knowledge["knowledge_id"]: {
                                    "knowledge_name": knowledge["canonical_name"],
                                    "count": 2,
                                    "latest": {"note": "raw private confusion note must not leak"},
                                }
                            },
                            "capabilities": {"subsumption": {"mean": 0.5}},
                            "error_tag_counts": {"要件遗漏": 1},
                        },
                    ),
                ]
            )

        with get_db_session(self.factory) as session:
            teacher, other, _student = self._users(session)
            analytics = self.service.class_analytics(
                session=session, teacher=teacher, class_id=class_id
            )
            self.assertEqual(analytics["summary"]["student_count"], 1)
            self.assertEqual(analytics["summary"]["learning_event_count"], 2)
            self.assertEqual(analytics["summary"]["task_attempt_count"], 1)
            self.assertEqual(analytics["summary"]["confusion_event_count"], 1)
            self.assertEqual(analytics["knowledge"][0]["confusion_count"], 2)
            self.assertFalse(analytics["privacy"]["student_emails_included"])
            self.assertFalse(analytics["privacy"]["raw_confusion_notes_included"])
            self.assertFalse(analytics["privacy"]["small_group_detail_suppressed"])
            serialized = json.dumps(analytics, ensure_ascii=False)
            self.assertNotIn("student@example.com", serialized)
            self.assertNotIn("raw private confusion note", serialized)
            with self.assertRaises(TeacherPermissionError):
                self.service.class_analytics(
                    session=session, teacher=other, class_id=class_id
                )

        with get_db_session(self.factory) as session:
            teacher, _other, _student = self._users(session)
            suppressed = TeacherService(min_aggregate_size=3).class_analytics(
                session=session, teacher=teacher, class_id=class_id
            )
            self.assertTrue(suppressed["privacy"]["small_group_detail_suppressed"])
            self.assertEqual(suppressed["privacy"]["minimum_aggregate_size"], 3)
            self.assertEqual(suppressed["knowledge"], [])
            self.assertEqual(suppressed["capabilities"], [])
            self.assertEqual(suppressed["top_error_tags"], [])

    def test_content_review_is_immutable_idempotent_and_answer_safe(self) -> None:
        with get_db_session(self.factory) as session:
            teacher, _other, _student = self._users(session)
            catalog = self.service.review_catalog(session=session, teacher=teacher)
            self.assertEqual(catalog["counts"]["case_bundles"], 3)
            self.assertEqual(catalog["counts"]["knowledge_cards"], 10)
            self.assertEqual(catalog["counts"]["task_items"], 30)
            serialized = json.dumps(catalog, ensure_ascii=False)
            self.assertNotIn("answer_private", serialized)
            self.assertNotIn("rationale_private", serialized)
            case_target = next(
                row for row in catalog["objects"] if row["object_type"] == "case_bundle"
            )
            teacher_case = self.service.teacher_case_bundle(
                session=session,
                teacher=teacher,
                case_id=case_target["object_id"],
            )
            self.assertIn("reference_private", teacher_case["case_bundle"])
            self.assertIn("guiding_points", teacher_case["case_bundle"]["reference_private"])
            target = next(
                row for row in catalog["objects"] if row["object_type"] == "task_item"
            )
            payload = dict(
                review_id="review-1",
                object_type=target["object_type"],
                object_id=target["object_id"],
                object_version=target["object_version"],
                decision="approve",
                note="法源与题干一致，同意本学期试用。",
            )
            first = self.service.submit_review(
                session=session, teacher=teacher, **payload
            )
            duplicate = self.service.submit_review(
                session=session, teacher=teacher, **payload
            )
            self.assertEqual(first["review_status"], "inserted")
            self.assertEqual(duplicate["review_status"], "duplicate")
            with self.assertRaises(TeacherConflictError):
                self.service.submit_review(
                    session=session,
                    teacher=teacher,
                    **{**payload, "note": "same id changed payload"},
                )

            with self.assertRaises(TeacherPermissionError):
                self.service.teacher_case_bundle(
                    session=session,
                    teacher=_student,
                    case_id=case_target["object_id"],
                )

        with get_db_session(self.factory) as session:
            teacher, _other, _student = self._users(session)
            audit = self.service.review_audit(session=session, teacher=teacher)
            self.assertEqual(len(audit["reviews"]), 1)

    def test_router_maps_student_role_to_403(self) -> None:
        def current_student():
            with get_db_session(self.factory) as session:
                return session.get(User, "student-1")

        def session_dependency():
            with get_db_session(self.factory) as session:
                yield session

        app = FastAPI()
        app.include_router(
            create_teacher_router(
                current_user_dependency=current_student,
                session_dependency=session_dependency,
                service=self.service,
            )
        )
        with TestClient(app) as client:
            response = client.get("/api/teacher/overview")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
