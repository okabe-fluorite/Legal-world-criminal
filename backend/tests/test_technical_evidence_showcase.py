from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for entry in (ROOT, BACKEND):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from src.competition.technical_evidence import build_technical_evidence_snapshot  # noqa: E402
from src.core.models import User  # noqa: E402
from ws_server import competition_technical_evidence  # noqa: E402


class TechnicalEvidenceShowcaseTests(unittest.TestCase):
    def test_snapshot_projects_all_machine_evidence_without_private_payloads(self) -> None:
        snapshot = build_technical_evidence_snapshot(repo_root=ROOT)
        self.assertEqual(snapshot["summary"]["candidate_files"], 4173)
        self.assertEqual(snapshot["summary"]["formal_articles"], 813)
        self.assertEqual(snapshot["summary"]["canonical_official_documents"], 2024)
        self.assertEqual(snapshot["summary"]["reasoning_gate_checks"], 11)
        self.assertEqual(snapshot["summary"]["benchmark_items"], 100)
        self.assertEqual(snapshot["summary"]["tutor_states"], 4)
        self.assertEqual(snapshot["summary"]["hybrid_records"], 57051)
        self.assertEqual(snapshot["hybrid_rag"]["collections"]["legal_authority"], 54463)
        self.assertEqual(snapshot["hybrid_rag"]["teacher_reviewed_qrels"], 0)
        self.assertEqual(snapshot["hybrid_rag"]["no_answer_false_positive_rate"], 0.0)
        self.assertEqual(snapshot["data_governance"]["local_source_matched"], 2024)
        self.assertEqual(snapshot["data_governance"]["verified_current"], 1045)
        self.assertEqual(snapshot["data_governance"]["verified_historical"], 598)
        self.assertEqual(snapshot["data_governance"]["unresolved"], 363)
        self.assertTrue(snapshot["data_governance"]["unresolved_non_blocking"])
        self.assertEqual(snapshot["legal_edu_eval"]["by_split"], {"dev": 30, "test": 70})
        self.assertEqual(snapshot["legal_edu_eval"]["cross_split_family_overlap"], 0)
        self.assertTrue(snapshot["agent_ablation"]["c0"]["gate_pass"])
        self.assertTrue(snapshot["agent_ablation"]["c1"]["gate_pass"])
        serialized = json.dumps(snapshot, ensure_ascii=False).lower()
        for forbidden in (
            "teacher_reference_private",
            "reference_private",
            "typical_errors_private",
            "answer_private",
            "internal_label_mapping",
            '"api_key":',
            "authorization",
            "c:\\users\\",
            "d:\\code\\",
            "e:\\guabangjieshuai",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_authenticated_endpoint_returns_same_safe_snapshot(self) -> None:
        payload = asyncio.run(
            competition_technical_evidence(
                current_user=User(id="evidence-user", email="evidence@example.com")
            )
        )
        self.assertEqual(payload["schema_version"], "competition-technical-evidence-snapshot-v1")
        self.assertEqual(len(payload["provenance"]), 9)
        self.assertTrue(all(len(row["sha256"]) == 64 for row in payload["provenance"]))
        self.assertEqual(payload["pending"][0]["status"], "pending_model_delivery")


if __name__ == "__main__":
    unittest.main()
