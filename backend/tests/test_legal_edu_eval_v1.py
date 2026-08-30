from __future__ import annotations

import hashlib
import json
import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for entry in (ROOT, BACKEND):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from scripts.build_legal_edu_eval_v1 import TYPE_TARGETS, canonical  # noqa: E402
from scripts.run_legal_edu_eval_v1 import run_evaluation, score_response  # noqa: E402


DATASET = BACKEND / "evaluation" / "legal_edu_eval_v1.jsonl"
MANIFEST = BACKEND / "evaluation" / "legal_edu_eval_v1_manifest.json"
SCHEMA = ROOT / "schemas" / "legal-edu-eval-item-v1.schema.json"


class LegalEduEvalV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.items = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line]
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_exact_distribution_schema_and_content_hashes(self) -> None:
        self.assertEqual(len(self.items), 100)
        self.assertEqual(Counter(row["task_type"] for row in self.items), Counter(TYPE_TARGETS))
        validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
        for row in self.items:
            validator.validate(row)
            body = {key: value for key, value in row.items() if key != "content_sha256"}
            expected = hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()
            self.assertEqual(row["content_sha256"], expected)
            self.assertEqual(row["review"]["status"], "candidate_requires_legal_review")
            self.assertEqual(row["review"]["gold_status"], "not_gold")

    def test_source_families_do_not_cross_dev_and_test(self) -> None:
        families: dict[str, set[str]] = defaultdict(set)
        for row in self.items:
            families[row["split"]].add(row["source_family_id"])
        self.assertFalse(families["dev"] & families["test"])
        self.assertEqual(Counter(row["split"] for row in self.items), Counter({"dev": 30, "test": 70}))
        self.assertEqual(self.manifest["counts"]["cross_split_family_overlap"], 0)

    def test_runner_keeps_all_missing_candidates_pending(self) -> None:
        report = run_evaluation(dataset_path=DATASET, manifest_path=MANIFEST, response_paths={})
        self.assertEqual(report["candidates"]["E0_base_model"]["status"], "pending")
        self.assertEqual(report["candidates"]["E3_rag_finetuned_model"]["status"], "pending_model_delivery")
        for row in report["candidates"].values():
            self.assertIsNone(row["metrics"]["automatic_gate_rate"])
            self.assertEqual(row["metrics"]["human_score"], "pending")

    def test_runner_scores_exact_evidence_and_required_points(self) -> None:
        item = self.items[0]
        answer = " ".join(keyword for point in item["required_points"] for keyword in point["keyword_groups"][0])
        evidence = item["standard_evidence"][0]
        result = score_response(
            item,
            {
                "task_id": item["task_id"],
                "output": {
                    "answer": answer,
                    "citations": [{"evidence_id": evidence["evidence_id"], "quote": evidence["quote"][:20]}],
                    "abstained": False,
                },
                "latency_ms": 12,
                "input_tokens": 20,
                "output_tokens": 30,
            },
        )
        self.assertTrue(result["schema_success"])
        self.assertEqual(result["point_coverage"], 1.0)
        self.assertTrue(result["evidence_scope_pass"])
        self.assertTrue(result["exact_quote_pass"])


if __name__ == "__main__":
    unittest.main()
