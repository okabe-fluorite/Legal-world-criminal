from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import func, select

from src.core.database import Base, create_database_engine, create_session_factory, get_db_session
from src.core.models import LearnerProfileRecord, LearningEventRecord, LearningSupportSessionRecord, User
from src.learning_support.service import (
    LearningSupportConflictError,
    LearningSupportPermissionError,
    LearningSupportService,
)


class LearningSupportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        database_path = (Path(self.temp.name) / "learning-support.db").as_posix()
        self.engine = create_database_engine(f"sqlite+pysqlite:///{database_path}")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)
        with get_db_session(self.factory) as session:
            session.add_all(
                [
                    User(id="student-1", email="student1@example.com"),
                    User(id="student-2", email="student2@example.com"),
                ]
            )

    def tearDown(self) -> None:
        self.engine.dispose()
        self.temp.cleanup()

    @staticmethod
    def create_payload(service: LearningSupportService) -> dict:
        card = service.knowledge.cards[0]
        task = next(
            row
            for row in service.knowledge.tasks
            if card["knowledge_id"] in row["knowledge_ids"]
        )
        return {
            "session_id": "support-1",
            "knowledge_id": card["knowledge_id"],
            "task_id": task["task_id"],
            "phase": "prestudy",
            "confusion_type": "fact_application",
            "confusion_note": "我不知道题目事实对应规则中的哪个条件。",
        }

    def test_two_step_session_is_idempotent_owned_and_not_mastery_evidence(self) -> None:
        service = LearningSupportService(generator=lambda _prompt: "{}")
        payload = self.create_payload(service)
        with get_db_session(self.factory) as session:
            student = session.get(User, "student-1")
            first = service.create_session(session=session, user=student, **payload)
            duplicate = service.create_session(session=session, user=student, **payload)
            self.assertEqual(first["session_status"], "inserted")
            self.assertEqual(duplicate["session_status"], "duplicate")
            self.assertEqual(first["session"]["status"], "awaiting_response")
            self.assertIn("关键事实", first["session"]["diagnostic_question"])
            self.assertFalse(
                first["session"]["evidence_eligibility"]["long_term_profile"]
            )
            with self.assertRaises(LearningSupportConflictError):
                service.create_session(
                    session=session,
                    user=student,
                    **{**payload, "confusion_note": "same id changed note"},
                )
            other = session.get(User, "student-2")
            with self.assertRaises(LearningSupportPermissionError):
                service.get_session(
                    session=session, user=other, session_id=payload["session_id"]
                )

        with get_db_session(self.factory) as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(LearningEventRecord)),
                0,
            )
            self.assertEqual(
                session.scalar(select(func.count()).select_from(LearnerProfileRecord)),
                0,
            )

    def test_governed_llm_result_requires_exact_standard_evidence(self) -> None:
        probe = LearningSupportService()
        card = probe.knowledge.cards[0]
        evidence = probe.knowledge.evidence_by_id[card["standard_evidence_ids"][0]]
        generated = {
            "diagnosis": {"category": "fact_rule_mapping", "summary": "学生尚未连接事实与规范条件。"},
            "layers": {
                "norm": {
                    "content": "先定位法条条件。",
                    "citations": [
                        {
                            "title": "刑法",
                            "article_ref": evidence["article_ref"],
                            "quote": evidence["quote"][:80],
                        }
                    ],
                },
                "plain": {"content": "用自己的话拆分规则条件。"},
                "application": {"content": "把题目事实逐项对应条件。"},
                "dispute": {"content": "课程基础口径之外的争议需要教师判断。"},
            },
            "next_action": {"type": "retry_task", "instruction": "重新作答当前任务。"},
            "confidence": 0.88,
            "teacher_review_required": False,
        }
        service = LearningSupportService(
            generator=lambda _prompt: (
                json.dumps(generated, ensure_ascii=False),
                {"task": "learning_support", "provider": "fake", "api_key_configured": True},
            )
        )
        payload = self.create_payload(service)
        with get_db_session(self.factory) as session:
            student = session.get(User, "student-1")
            service.create_session(session=session, user=student, **payload)
            first = service.respond(
                session=session,
                user=student,
                session_id=payload["session_id"],
                student_response="题目中最关键的事实应当与法条条件逐项对应。",
            )
            duplicate = service.respond(
                session=session,
                user=student,
                session_id=payload["session_id"],
                student_response="题目中最关键的事实应当与法条条件逐项对应。",
            )
            self.assertEqual(first["response_status"], "inserted")
            self.assertEqual(duplicate["response_status"], "duplicate")
            result = first["session"]["result"]
            self.assertEqual(first["session"]["result_source"], "llm_governed_evidence")
            self.assertEqual(first["session"]["status"], "completed")
            self.assertEqual(result["citation_audit"]["summary"]["valid"], 1)
            self.assertIn("semantic entailment was not evaluated", " ".join(result["warnings"]))
            serialized = json.dumps(first, ensure_ascii=False)
            self.assertNotIn('"api_key":', serialized)
            self.assertNotIn("primary-secret", serialized)
            with self.assertRaises(LearningSupportConflictError):
                service.respond(
                    session=session,
                    user=student,
                    session_id=payload["session_id"],
                    student_response="same session changed response",
                )

    def test_bad_model_citation_falls_back_to_governed_card(self) -> None:
        bad = {
            "diagnosis": {"category": "bad", "summary": "bad"},
            "layers": {
                "norm": {
                    "content": "bad",
                    "citations": [
                        {"title": "刑法", "article_ref": "第九千条", "quote": "不存在"}
                    ],
                },
                "plain": {"content": "bad"},
                "application": {"content": "bad"},
                "dispute": {"content": "bad"},
            },
            "next_action": {"type": "retry_task", "instruction": "bad"},
            "confidence": 0.99,
            "teacher_review_required": False,
        }
        service = LearningSupportService(
            generator=lambda _prompt: json.dumps(bad, ensure_ascii=False)
        )
        payload = self.create_payload(service)
        with get_db_session(self.factory) as session:
            student = session.get(User, "student-1")
            service.create_session(session=session, user=student, **payload)
            response = service.respond(
                session=session,
                user=student,
                session_id=payload["session_id"],
                student_response="我的解释",
            )
            result = response["session"]["result"]
            self.assertEqual(response["session"]["result_source"], "deterministic_fallback")
            self.assertEqual(response["session"]["status"], "needs_teacher_review")
            self.assertTrue(result["teacher_review_required"])
            self.assertTrue(result["layers"]["norm"]["citations"])
            self.assertNotIn("第九千条", json.dumps(result, ensure_ascii=False))

    def test_session_table_payload_is_student_scoped(self) -> None:
        service = LearningSupportService(generator=lambda _prompt: "{}")
        payload = self.create_payload(service)
        with get_db_session(self.factory) as session:
            student = session.get(User, "student-1")
            service.create_session(session=session, user=student, **payload)
        with get_db_session(self.factory) as session:
            record = session.get(LearningSupportSessionRecord, payload["session_id"])
            self.assertEqual(record.user_id, "student-1")
            self.assertEqual(record.status, "awaiting_response")


if __name__ == "__main__":
    unittest.main()
