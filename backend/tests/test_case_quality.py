from __future__ import annotations

import sys
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "backend" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from audit_case_dataset import audit_case, audit_dataset  # noqa: E402


class CaseQualityTests(unittest.TestCase):
    def test_released_dataset_passes_strict_gate(self) -> None:
        result = audit_dataset(REPO_ROOT / "dataset" / "released_case_dataset.json")
        self.assertEqual(result["counts"]["records"], 3)
        self.assertEqual(result["counts"]["releasable"], 3)
        self.assertEqual(result["counts"]["blocked"], 0)

    def test_optional_local_source_hash_gate_detects_tampering(self) -> None:
        record = json.loads(
            (REPO_ROOT / "dataset" / "released_case_dataset.json").read_text(
                encoding="utf-8"
            )
        )[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "case.txt"
            source.write_text("authoritative case source", encoding="utf-8")
            checked = copy.deepcopy(record)
            checked["provenance"]["local_source_path"] = "case.txt"
            checked["provenance"]["local_source_sha256"] = hashlib.sha256(
                source.read_bytes()
            ).hexdigest()
            self.assertTrue(audit_case(checked, source_root=root)["releasable"])
            checked["provenance"]["local_source_sha256"] = "0" * 64
            audit = audit_case(checked, source_root=root)
            self.assertFalse(audit["releasable"])
            self.assertIn(
                "local_source_hash_mismatch",
                {flag["code"] for flag in audit["flags"]},
            )

    def test_legacy_dataset_is_not_silently_released(self) -> None:
        result = audit_dataset(REPO_ROOT / "dataset" / "criminal_case_dataset.json")
        self.assertGreater(result["counts"]["blocked"], 0)
        first = result["cases"][0]
        codes = {flag["code"] for flag in first["flags"]}
        self.assertIn("defendant_finding_mismatch", codes)


if __name__ == "__main__":
    unittest.main()
