from __future__ import annotations

import json
import asyncio
import unittest
from pathlib import Path

from scripts.run_typical_question_evaluation import (
    REPO_ROOT,
    _citation_audit,
    _point_audit,
    _sources_for,
)
from src.case_bundle.service import CaseBundleService
from src.knowledge.service import KnowledgeService
from src.core.models import User
from ws_server import competition_typical_questions


class TypicalQuestionEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.suite = json.loads(
            (REPO_ROOT / "backend" / "evaluation" / "typical_questions.json").read_text(
                encoding="utf-8"
            )
        )
        cls.knowledge = KnowledgeService()
        cls.bundles = CaseBundleService()

    def test_all_three_cases_resolve_required_governed_sources(self) -> None:
        self.assertEqual(len(self.suite["cases"]), 3)
        for case in self.suite["cases"]:
            sources = _sources_for(case, self.knowledge, self.bundles)
            source_ids = {row["source_id"] for row in sources}
            self.assertTrue(set(case["required_source_ids"]).issubset(source_ids))
            self.assertTrue(all(row["quote"] for row in sources))

    def test_out_of_scope_or_non_exact_citation_fails(self) -> None:
        case = self.suite["cases"][0]
        sources = _sources_for(case, self.knowledge, self.bundles)
        audit = _citation_audit(
            {
                "citations": [
                    {"source_id": "EVID_OUTSIDE", "quote": "伪造引文"},
                    {
                        "source_id": case["required_source_ids"][0],
                        "quote": "并非法条逐字片段",
                    },
                ]
            },
            sources,
            case["required_source_ids"],
        )
        self.assertFalse(audit["passed"])
        self.assertEqual(audit["missing_required_source_ids"], case["required_source_ids"])

    def test_committed_live_baseline_passes_automated_gate_but_not_expert_review(self) -> None:
        report = json.loads(
            (REPO_ROOT / "docs" / "TYPICAL_QUESTION_EVALUATION.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report["case_count"], 3)
        self.assertEqual(report["automated_gate_pass_count"], 3)
        self.assertFalse(report["all_expert_reviews_complete"])
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn('"api_key":', serialized)
        for row in report["cases"]:
            self.assertTrue(row["automated_gate_pass"])
            self.assertEqual(row["expert_review_status"], "pending")
            self.assertFalse(row["verified_accurate"])
            self.assertTrue(all(point["passed"] for point in _point_audit(
                " ".join(
                    [
                        row["model_output"]["answer"],
                        " ".join(row["model_output"]["rule_steps"]),
                        row["model_output"]["conclusion"],
                    ]
                ),
                row,
            )))

    def test_authenticated_showcase_endpoint_returns_exact_three_cases(self) -> None:
        payload = asyncio.run(
            competition_typical_questions(
                current_user=User(id="showcase-user", email="showcase@example.com")
            )
        )
        self.assertEqual(payload["case_count"], 3)
        self.assertEqual(payload["automated_gate_pass_count"], 3)
        self.assertFalse(payload["all_expert_reviews_complete"])


if __name__ == "__main__":
    unittest.main()
