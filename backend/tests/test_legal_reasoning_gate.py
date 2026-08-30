from __future__ import annotations

import json
import hashlib
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for entry in (ROOT, BACKEND):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from scripts.run_legal_reasoning_gate_audit import (  # noqa: E402
    DEFAULT_FIXTURES,
    apply_mutations,
    run_suite,
)
from src.legal_reasoning.gate import LegalReasoningGate, build_case_gate_context  # noqa: E402


class LegalReasoningGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.suite = json.loads(DEFAULT_FIXTURES.read_text(encoding="utf-8"))

    def test_base_fixture_matches_frozen_schema(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "legal-reasoning-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator(schema).validate(self.suite["base_reasoning"])

    def test_positive_fixture_passes_all_deterministic_checks(self) -> None:
        context_args = dict(self.suite["context"])
        context_args["case_id"] = context_args.pop("case_bundle_id")
        context = build_case_gate_context(**context_args)
        result = LegalReasoningGate().evaluate(self.suite["base_reasoning"], context)
        self.assertTrue(result["passed"], result["failed_checks"])
        self.assertFalse(result["failed_checks"])
        self.assertEqual(len(result["checks"]), 11)

    def test_all_negative_fixtures_are_blocked_as_expected(self) -> None:
        report = run_suite(self.suite)
        self.assertTrue(report["all_expectations_met"])
        self.assertEqual(report["counts"]["positive_passed"], 1)
        self.assertEqual(report["counts"]["negative_blocked"], 6)
        self.assertEqual(report["model_calls"], 0)
        self.assertEqual(report["network_calls"], 0)

    def test_mutations_do_not_modify_frozen_base(self) -> None:
        before = json.dumps(self.suite["base_reasoning"], ensure_ascii=False, sort_keys=True)
        mutated = apply_mutations(
            self.suite["base_reasoning"],
            [{"op": "set", "path": ["conclusion", "status"], "value": "abstain"}],
        )
        self.assertEqual(self.suite["base_reasoning"]["conclusion"]["status"], "supported_tentative")
        self.assertEqual(mutated["conclusion"]["status"], "abstain")
        self.assertEqual(
            before,
            json.dumps(self.suite["base_reasoning"], ensure_ascii=False, sort_keys=True),
        )

    def test_committed_audit_is_current_and_has_no_model_claim(self) -> None:
        report = json.loads(
            (ROOT / "docs" / "LEGAL_REASONING_GATE_AUDIT.json").read_text(
                encoding="utf-8"
            )
        )
        fixture_sha = hashlib.sha256(DEFAULT_FIXTURES.read_bytes()).hexdigest()
        schema_path = ROOT / "schemas" / "legal-reasoning-v1.schema.json"
        schema_sha = hashlib.sha256(schema_path.read_bytes()).hexdigest()
        self.assertEqual(report["fixture_suite_sha256"], fixture_sha)
        self.assertEqual(report["schema_sha256"], schema_sha)
        self.assertTrue(report["all_expectations_met"])
        self.assertEqual(report["counts"]["fixtures"], 7)
        self.assertEqual(report["model_calls"], 0)
        self.assertEqual(report["network_calls"], 0)


if __name__ == "__main__":
    unittest.main()
