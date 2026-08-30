from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for entry in (ROOT, BACKEND):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from scripts.run_agent_ablation_v1 import (  # noqa: E402
    DEFAULT_PROTOCOL,
    extract_json,
    normalize_orchestrated_ids,
    build_blind_review_packet,
    pending_report,
    source_payload,
)


class AgentAblationV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = json.loads(DEFAULT_PROTOCOL.read_text(encoding="utf-8"))

    def test_protocol_freezes_case_stage_inputs_and_pending_teacher_review(self) -> None:
        self.assertEqual(self.protocol["case_bundle_id"], "CRIM_CASE_BCE041E195C8247BC179")
        self.assertEqual(self.protocol["stage"], "CR")
        self.assertEqual(len(self.protocol["required_element_ids"]), 4)
        self.assertEqual(self.protocol["teacher_blind_review"], "pending")

    def test_source_payload_contains_only_public_fact_catalog_and_allowed_evidence(self) -> None:
        context, shared = source_payload(self.protocol)
        serialized = json.dumps(shared, ensure_ascii=False)
        self.assertNotIn("teacher_reference_private", serialized)
        self.assertNotIn("reference_private", serialized)
        self.assertEqual(set(context["allowed_evidence"]), {"EVID_9CB6894B3E55465B19C6"})
        self.assertTrue(shared["student_visible_fact_catalog"])
        self.assertTrue(
            all(
                re.fullmatch(r"FACT_[A-Z0-9_]{2,64}", row["fact_id"])
                for row in shared["student_visible_fact_catalog"]
            )
        )

    def test_json_extraction_and_pending_report_are_honest(self) -> None:
        self.assertEqual(extract_json("```json\n{\"ok\": true}\n```"), {"ok": True})
        report = pending_report(self.protocol)
        self.assertEqual(report["run_status"], "pending_live_model_run")
        self.assertEqual(report["conditions"], {"C0": "pending", "C1": "pending"})
        self.assertEqual(report["teacher_blind_review"], "pending")

    def test_orchestrator_normalizes_only_counterargument_ids(self) -> None:
        raw = {
            "issue": {"statement": "x"},
            "counterarguments": [
                {"argument_id": "COUNTER_1", "position": "p"},
                {"argument_id": "COUNTER_VALID", "position": "q"},
            ],
        }
        normalized, changes = normalize_orchestrated_ids(raw)
        self.assertEqual(raw["counterarguments"][0]["argument_id"], "COUNTER_1")
        self.assertEqual(normalized["counterarguments"][0]["argument_id"], "COUNTER_C01")
        self.assertEqual(normalized["counterarguments"][1]["argument_id"], "COUNTER_VALID")
        self.assertEqual(normalized["issue"], raw["issue"])
        self.assertEqual(len(changes), 1)

    def test_blind_packet_does_not_expose_condition_labels(self) -> None:
        report = {
            "protocol_sha256": "0f" * 32,
            "conditions": {
                "C0": {"reasoning": {"reasoning_id": "x", "case_context": {}, "issue": {"statement": "甲"}}},
                "C1": {"reasoning": {"reasoning_id": "y", "case_context": {}, "issue": {"statement": "乙"}}},
            },
        }
        packet, mapping = build_blind_review_packet(report, self.protocol)
        serialized = json.dumps(packet, ensure_ascii=False)
        self.assertNotIn('"C0"', serialized)
        self.assertNotIn('"C1"', serialized)
        self.assertEqual(set(mapping), {"C0", "C1"})
        self.assertEqual(packet["status"], "pending_two_independent_law_reviewers")


if __name__ == "__main__":
    unittest.main()
