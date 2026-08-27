from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from src.teaching import learner
from src.teaching.report import build_report
from src.teaching.skill_card import _weak_capabilities
from src.teaching.scorer import TeachingScorer


def sample_event(event_id: str = "evt-1") -> dict:
    return {
        "event_id": event_id,
        "case_id": "case_1",
        "stage": "DS",
        "scored_at": "2026-08-26T12:00:00",
        "capability_scores": {
            "subsumption": {"score": 0.6, "weight": 1.0},
            "claim_construction": {"score": None, "weight": 0.5},
        },
        "knowledge_verdicts": [
            {"kp": "正当防卫", "status": "missing", "reason": "遗漏条件"}
        ],
        "knowledge_gaps": ["正当防卫"],
        "error_tags": ["遗漏时间条件"],
    }


class LearnerEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.old_profiles = os.environ.get("SIMLAW_TEACHING_PROFILES_DIR")
        self.old_cards = os.environ.get("SIMLAW_TEACHING_SKILL_CARDS_DIR")
        os.environ["SIMLAW_TEACHING_PROFILES_DIR"] = str(root / "profiles")
        os.environ["SIMLAW_TEACHING_SKILL_CARDS_DIR"] = str(root / "cards")

    def tearDown(self) -> None:
        if self.old_profiles is None:
            os.environ.pop("SIMLAW_TEACHING_PROFILES_DIR", None)
        else:
            os.environ["SIMLAW_TEACHING_PROFILES_DIR"] = self.old_profiles
        if self.old_cards is None:
            os.environ.pop("SIMLAW_TEACHING_SKILL_CARDS_DIR", None)
        else:
            os.environ["SIMLAW_TEACHING_SKILL_CARDS_DIR"] = self.old_cards
        self.temp.cleanup()

    def test_same_event_is_idempotent_and_gap_counts_once(self) -> None:
        first = learner.update_profile("student", sample_event())
        second = learner.update_profile("student", sample_event())
        self.assertEqual(first["knowledge_state"]["正当防卫"]["exposed"], 1)
        self.assertEqual(second["knowledge_state"]["正当防卫"]["exposed"], 1)
        self.assertEqual(len(second["growth_curve"]), 1)
        self.assertEqual(second["processed_event_ids"], ["evt-1"])

    def test_ai_drafted_event_is_feedback_only(self) -> None:
        event = sample_event("evt-draft")
        event["evidence_eligibility"] = {
            "formative_feedback": True,
            "long_term_profile": False,
            "reason": "ai_drafted_response_excluded_from_mastery",
        }
        profile = learner.update_profile("student", event)
        self.assertEqual(profile["capability_means"], {})
        self.assertEqual(profile["knowledge_state"], {})
        self.assertIn("evt-draft", profile["excluded_events"])

    def test_canonical_knowledge_id_absorbs_name_gap(self) -> None:
        event = sample_event("evt-canonical")
        event["knowledge_verdicts"] = [
            {
                "knowledge_id": "CRIM_KP_2DD5C021746121C3",
                "knowledge_name": "故意、过失与意外事件",
                "status": "partial",
            }
        ]
        event["knowledge_gaps"] = ["故意、过失与意外事件"]
        profile = learner.update_profile("student", event)
        state = profile["knowledge_state"]
        self.assertEqual(list(state), ["CRIM_KP_2DD5C021746121C3"])
        self.assertEqual(state["CRIM_KP_2DD5C021746121C3"]["exposed"], 1)

    def test_unobserved_capabilities_are_not_zero(self) -> None:
        report = build_report("new-student")
        self.assertEqual(len(report["capability_radar"]), 8)
        self.assertTrue(all(row["score"] is None for row in report["capability_radar"]))
        self.assertTrue(
            all(
                row["evidence_status"] == "insufficient_evidence"
                for row in report["capability_radar"]
            )
        )

    def test_abstained_capability_is_not_rendered_as_weak(self) -> None:
        weak = _weak_capabilities(sample_event())
        self.assertEqual([row["code"] for row in weak], ["subsumption"])

    def test_learning_event_id_is_deterministic_and_records_assistance(self) -> None:
        kwargs = {
            "case_id": "case_1",
            "stage": "DS",
            "charge": "抢劫罪",
            "student_id": "student",
            "payload": {"capability_scores": {}},
            "law_citations": [],
            "gold_incomplete": False,
            "utterance_texts": ["模型起草文本"],
            "utterances": [
                {
                    "request_id": "req-1",
                    "text": "模型起草文本",
                    "final_text": "模型起草文本",
                    "assist_mode": "draft",
                    "hint_ids": ["h1"],
                    "skill_card_ids": ["card-1"],
                    "timestamp": "2026-08-26T12:00:00",
                }
            ],
        }
        first = TeachingScorer()._build_learning_event(**kwargs)
        second = TeachingScorer()._build_learning_event(**kwargs)
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertEqual(first["schema_version"], "learning-event-v2")
        self.assertTrue(first["assist"]["ai_drafted"])
        self.assertEqual(first["assist"]["hint_count"], 1)
        self.assertEqual(first["assist"]["skill_card_ids"], ["card-1"])
        self.assertFalse(first["evidence_eligibility"]["long_term_profile"])


if __name__ == "__main__":
    unittest.main()
