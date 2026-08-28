from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import func, select

from src.core.database import Base, create_database_engine, create_session_factory, get_db_session
from src.core.models import (
    ClassEnrollmentRecord,
    CourseClassRecord,
    LearnerProfileRecord,
    LearningEventRecord,
    SubjectiveAttemptRecord,
    SubjectiveReviewRecord,
    User,
)
from src.core.role_service import grant_user_role
from src.subjective.service import (
    SubjectiveConflictError,
    SubjectivePermissionError,
    SubjectiveTaskService,
)


class SubjectiveTaskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = (Path(self.temp.name) / "subjective.db").as_posix()
        self.previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{self.database_path}"
        self.engine = create_database_engine(os.environ["DATABASE_URL"])
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)
        with get_db_session(self.factory) as session:
            teacher = User(id="teacher-1", email="teacher@example.com")
            other_teacher = User(id="teacher-2", email="other@example.com")
            student = User(id="student-1", email="student@example.com")
            session.add_all([teacher, other_teacher, student])
            session.flush()
            grant_user_role(session=session, user=teacher, role="teacher", granted_by="test")
            grant_user_role(session=session, user=other_teacher, role="teacher", granted_by="test")
            classroom = CourseClassRecord(
                id="class-1",
                teacher_user_id=teacher.id,
                course_id="undergraduate-criminal-law",
                name="刑法甲班",
                term="2026秋",
                status="active",
            )
            session.add(classroom)
            session.flush()
            session.add(
                ClassEnrollmentRecord(
                    id="enrollment-1",
                    class_id=classroom.id,
                    student_user_id=student.id,
                    status="active",
                )
            )

    def tearDown(self) -> None:
        self.engine.dispose()
        if self.previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.previous_database_url
        self.temp.cleanup()

    @staticmethod
    def model_payload(task: dict, *, confidence: float = 0.9) -> dict:
        return {
            "rubric_scores": {
                dimension["code"]: 0.8
                for dimension in task["rubric_private"]["dimensions"]
            },
            "strengths": ["能够区分事实与规范条件。"],
            "corrections": ["需要进一步说明边界事实。"],
            "suggested_revision": "补充反例并写清法条与事实的连接。",
            "evidence_ids_used": [task["standard_evidence_ids"][0]],
            "confidence": confidence,
            "abstain": False,
            "abstain_reason": "",
        }

    def service(self, *, confidence: float = 0.9) -> SubjectiveTaskService:
        probe = SubjectiveTaskService(generator=lambda _prompt: "")
        first = probe.tasks[0]
        payload = self.model_payload(first, confidence=confidence)
        return SubjectiveTaskService(
            generator=lambda _prompt: (
                json.dumps(payload, ensure_ascii=False),
                {"task": "subjective_scoring", "provider": "fake"},
            )
        )

    @staticmethod
    def valid_response(service: SubjectiveTaskService, task: dict) -> str:
        evidence = service.evidence_by_id[task["standard_evidence_ids"][0]]
        return (
            f"我先依据《刑法》{evidence['article_ref']}确定核心规则，再把题目中的关键事实逐项对应。"
            "成立情形必须满足规范列出的全部条件；反例中只要缺少关键条件，就不能直接得出同一结论。"
            "最后还要说明事实争议与规范解释争议的区别，避免只凭结果严重倒推主观要件。"
        )

    def test_catalog_contains_10_short_and_3_role_tasks_without_private_fields(self) -> None:
        service = self.service()
        catalog = service.catalog()
        self.assertEqual(catalog["counts"], {"tasks": 13, "short_answer": 10, "role_reversal": 3})
        serialized = json.dumps(catalog, ensure_ascii=False)
        self.assertNotIn("rubric_private", serialized)
        self.assertNotIn("expected_points_private", serialized)
        self.assertTrue(all(row["content_sha256"] for row in catalog["tasks"]))

    def test_high_confidence_ai_feedback_remains_ineligible_until_teacher_review(self) -> None:
        service = self.service(confidence=0.9)
        task = service.tasks[0]
        with get_db_session(self.factory) as session:
            student = session.get(User, "student-1")
            first = service.submit_attempt(
                session=session,
                user=student,
                attempt_id="subjective-1",
                task_id=task["task_id"],
                task_version=task["content_sha256"],
                phase="prestudy",
                response_text=self.valid_response(service, task),
                confidence=4,
            )
            duplicate = service.submit_attempt(
                session=session,
                user=student,
                attempt_id="subjective-1",
                task_id=task["task_id"],
                task_version=task["content_sha256"],
                phase="prestudy",
                response_text=self.valid_response(service, task),
                confidence=4,
            )
            self.assertEqual(first["attempt_status"], "inserted")
            self.assertEqual(duplicate["attempt_status"], "duplicate")
            attempt = first["attempt"]
            self.assertFalse(attempt["ai_abstained"])
            self.assertEqual(attempt["ai_score"], 0.8)
            self.assertEqual(attempt["status"], "needs_teacher_review")
            self.assertFalse(attempt["evidence_eligibility"]["long_term_profile"])
        with get_db_session(self.factory) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(LearningEventRecord)), 0)
            self.assertEqual(session.scalar(select(func.count()).select_from(LearnerProfileRecord)), 0)

    def test_low_confidence_or_bad_student_citation_abstains(self) -> None:
        low = self.service(confidence=0.5)
        task = low.tasks[0]
        with get_db_session(self.factory) as session:
            student = session.get(User, "student-1")
            result = low.submit_attempt(
                session=session,
                user=student,
                attempt_id="subjective-low",
                task_id=task["task_id"],
                task_version=task["content_sha256"],
                phase="prestudy",
                response_text=self.valid_response(low, task),
                confidence=3,
            )
            self.assertTrue(result["attempt"]["ai_abstained"])
            self.assertIsNone(result["attempt"]["ai_score"])

            high = self.service(confidence=0.95)
            bad_text = (
                "我引用《刑法》第九千条作为依据，但这实际上是一个不存在的条文。"
                "回答仍然补足到足够长度，并讨论事实与规范之间的关系以及正反两类边界。"
                "我还尝试把关键事实逐项对应构成条件，但由于所引条文不存在，这个论证不能作为可靠法源依据，需要重新检索并修订。"
            )
            bad = high.submit_attempt(
                session=session,
                user=student,
                attempt_id="subjective-bad-citation",
                task_id=task["task_id"],
                task_version=task["content_sha256"],
                phase="prestudy",
                response_text=bad_text,
                confidence=4,
            )
            self.assertTrue(bad["attempt"]["ai_abstained"])
            self.assertIsNone(bad["attempt"]["ai_score"])
            self.assertFalse(bad["attempt"]["citation_audit"]["passed"])

    def test_teacher_queue_is_class_scoped_and_approval_creates_eligible_event(self) -> None:
        service = self.service(confidence=0.9)
        task = service.tasks[0]
        with get_db_session(self.factory) as session:
            student = session.get(User, "student-1")
            service.submit_attempt(
                session=session,
                user=student,
                attempt_id="subjective-review",
                task_id=task["task_id"],
                task_version=task["content_sha256"],
                phase="review",
                response_text=self.valid_response(service, task),
                confidence=4,
            )
        with get_db_session(self.factory) as session:
            teacher = session.get(User, "teacher-1")
            other = session.get(User, "teacher-2")
            queue = service.teacher_queue(session=session, teacher=teacher)
            other_queue = service.teacher_queue(session=session, teacher=other)
            self.assertEqual(len(queue["attempts"]), 1)
            self.assertEqual(other_queue["attempts"], [])
            serialized = json.dumps(queue, ensure_ascii=False)
            self.assertNotIn("student@example.com", serialized)
            self.assertNotIn("student-1", serialized)
            with self.assertRaises(SubjectivePermissionError):
                service.review_attempt(
                    session=session,
                    teacher=other,
                    review_id="review-other",
                    attempt_id="subjective-review",
                    decision="approve",
                    teacher_score=0.8,
                    knowledge_status="partial",
                    feedback="无权限",
                    error_tags=[],
                )

        with get_db_session(self.factory) as session:
            teacher = session.get(User, "teacher-1")
            result = service.review_attempt(
                session=session,
                teacher=teacher,
                review_id="subjective-teacher-review",
                attempt_id="subjective-review",
                decision="approve",
                teacher_score=0.82,
                knowledge_status="partial",
                feedback="规则基本准确，但边界事实仍需展开。",
                error_tags=["边界论证不足"],
            )
            self.assertEqual(result["review_status"], "inserted")
            self.assertTrue(result["learning_event"]["evidence_eligibility"]["long_term_profile"])
            self.assertEqual(result["learning_event"]["event_type"], "teacher_reviewed_subjective_assessment")
        with get_db_session(self.factory) as session:
            attempt = session.get(SubjectiveAttemptRecord, "subjective-review")
            review = session.get(SubjectiveReviewRecord, "subjective-teacher-review")
            event = session.get(LearningEventRecord, review.learning_event_id)
            self.assertEqual(attempt.status, "teacher_approved")
            self.assertIsNotNone(event)
            self.assertTrue(event.long_term_profile_eligible)
            self.assertEqual(event.payload_json["task_version"], task["content_sha256"])
            student = session.get(User, "student-1")
            history = service.list_attempts(session=session, user=student, phase="review")
            self.assertEqual(len(history["attempts"]), 1)
            visible = history["attempts"][0]
            self.assertTrue(visible["evidence_eligibility"]["long_term_profile"])
            self.assertEqual(visible["teacher_review"]["decision"], "approve")
            self.assertEqual(visible["teacher_review"]["teacher_score"], 0.82)
            serialized = json.dumps(history, ensure_ascii=False)
            self.assertNotIn("teacher-1", serialized)
            self.assertNotIn("teacher@example.com", serialized)

    def test_one_attempt_accepts_only_one_teacher_decision_and_event(self) -> None:
        service = self.service(confidence=0.9)
        task = service.tasks[0]
        with get_db_session(self.factory) as session:
            student = session.get(User, "student-1")
            service.submit_attempt(
                session=session,
                user=student,
                attempt_id="subjective-single-review",
                task_id=task["task_id"],
                task_version=task["content_sha256"],
                phase="prestudy",
                response_text=self.valid_response(service, task),
                confidence=4,
            )
        payload = {
            "attempt_id": "subjective-single-review",
            "decision": "approve",
            "teacher_score": 0.8,
            "knowledge_status": "partial",
            "feedback": "第一次且唯一的教师决定。",
            "error_tags": ["边界待补"],
        }
        with get_db_session(self.factory) as session:
            teacher = session.get(User, "teacher-1")
            inserted = service.review_attempt(
                session=session,
                teacher=teacher,
                review_id="single-review-id",
                **payload,
            )
            duplicate = service.review_attempt(
                session=session,
                teacher=teacher,
                review_id="single-review-id",
                **payload,
            )
            self.assertEqual(inserted["review_status"], "inserted")
            self.assertEqual(duplicate["review_status"], "duplicate")
        with get_db_session(self.factory) as session:
            teacher = session.get(User, "teacher-1")
            with self.assertRaises(SubjectiveConflictError):
                service.review_attempt(
                    session=session,
                    teacher=teacher,
                    review_id="second-review-id",
                    **payload,
                )
        with get_db_session(self.factory) as session:
            review_count = int(
                session.scalar(select(func.count()).select_from(SubjectiveReviewRecord))
                or 0
            )
            event_count = int(
                session.scalar(
                    select(func.count())
                    .select_from(LearningEventRecord)
                    .where(
                        LearningEventRecord.event_type
                        == "teacher_reviewed_subjective_assessment"
                    )
                )
                or 0
            )
            self.assertEqual(review_count, 1)
            self.assertEqual(event_count, 1)

    def test_student_history_returns_deidentified_revision_feedback(self) -> None:
        service = self.service(confidence=0.9)
        task = service.tasks[0]
        original = self.valid_response(service, task)
        with get_db_session(self.factory) as session:
            student = session.get(User, "student-1")
            service.submit_attempt(
                session=session,
                user=student,
                attempt_id="subjective-revision-original",
                task_id=task["task_id"],
                task_version=task["content_sha256"],
                phase="review",
                response_text=original,
                confidence=3,
            )
        with get_db_session(self.factory) as session:
            teacher = session.get(User, "teacher-1")
            service.review_attempt(
                session=session,
                teacher=teacher,
                review_id="subjective-revision-request",
                attempt_id="subjective-revision-original",
                decision="request_revision",
                teacher_score=None,
                knowledge_status="",
                feedback="请补充行为时法与裁判时法的比较步骤。",
                error_tags=["时间效力比较不足"],
            )
        with get_db_session(self.factory) as session:
            student = session.get(User, "student-1")
            history = service.list_attempts(session=session, user=student, phase="review")
            self.assertEqual(history["attempts"][0]["status"], "revision_requested")
            self.assertEqual(
                history["attempts"][0]["teacher_review"]["decision"],
                "request_revision",
            )
            self.assertFalse(
                history["attempts"][0]["evidence_eligibility"]["long_term_profile"]
            )
            serialized = json.dumps(history, ensure_ascii=False)
            self.assertNotIn("teacher-1", serialized)
            self.assertNotIn("teacher@example.com", serialized)
            service.submit_attempt(
                session=session,
                user=student,
                attempt_id="subjective-revision-new",
                task_id=task["task_id"],
                task_version=task["content_sha256"],
                phase="review",
                response_text=original + "修订稿进一步比较行为时法与裁判时法。",
                confidence=4,
            )
        with get_db_session(self.factory) as session:
            student = session.get(User, "student-1")
            history = service.list_attempts(session=session, user=student, phase="review")
            self.assertEqual(len(history["attempts"]), 2)
            self.assertEqual(history["attempts"][0]["status"], "needs_teacher_review")
        with get_db_session(self.factory) as session:
            teacher = session.get(User, "teacher-1")
            service.review_attempt(
                session=session,
                teacher=teacher,
                review_id="subjective-revision-reject",
                attempt_id="subjective-revision-new",
                decision="reject",
                teacher_score=None,
                knowledge_status="",
                feedback="本次修订仍未回应核心争点。",
                error_tags=["核心争点遗漏"],
            )
        with get_db_session(self.factory) as session:
            student = session.get(User, "student-1")
            history = service.list_attempts(session=session, user=student, phase="review")
            self.assertEqual(history["attempts"][0]["status"], "teacher_rejected")
            self.assertEqual(
                history["attempts"][0]["teacher_review"]["decision"],
                "reject",
            )
            event_count = int(
                session.scalar(select(func.count()).select_from(LearningEventRecord))
                or 0
            )
            self.assertEqual(event_count, 0)


if __name__ == "__main__":
    unittest.main()
