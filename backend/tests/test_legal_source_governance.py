from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUTPUT = REPO / "data_governance"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LegalSourceGovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory = json.loads((OUTPUT / "corpus_inventory.json").read_text(encoding="utf-8"))
        cls.governed = json.loads((OUTPUT / "governed_source_manifest.json").read_text(encoding="utf-8"))
        cls.audit = json.loads((OUTPUT / "DATA_GOVERNANCE_AUDIT.json").read_text(encoding="utf-8"))
        cls.rejections = [
            json.loads(line)
            for line in (OUTPUT / "source_rejection_log.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        cls.links = [
            json.loads(line)
            for line in (OUTPUT / "knowledge_evidence_links.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]

    def test_inventory_matches_live_snapshot_contract_without_absolute_paths(self) -> None:
        self.assertEqual(self.inventory["counts"]["files"], 4173)
        self.assertEqual(self.inventory["counts"]["bytes"], 255164821)
        self.assertEqual(self.inventory["counts"]["extensions"]["doc"], 53)
        self.assertEqual(self.inventory["counts"]["extensions"]["docx"], 1458)
        self.assertEqual(
            self.inventory["counts"]["raw_subfolders"],
            {"司法解释": 553, "指导性案例": 530, "法律": 347, "行政法规": 610},
        )
        self.assertEqual(len(self.inventory["files"]), 4173)
        for row in self.inventory["files"]:
            self.assertRegex(row["sha256"], r"^[a-f0-9]{64}$")
            self.assertNotRegex(row["path"], r"^[A-Za-z]:")
            self.assertNotIn("\\", row["path"])

    def test_formal_corpus_remains_exactly_813_and_candidates_stay_provisional(self) -> None:
        formal = self.governed["formal_normative_layer"]
        self.assertEqual(formal["article_count"], 813)
        self.assertEqual(sum(row["articles"] for row in formal["outputs"]), 813)
        self.assertEqual(self.governed["course_layer"]["knowledge_cards"], 10)
        self.assertEqual(self.governed["course_layer"]["case_bundles"], 3)
        self.assertGreater(self.governed["candidate_layers"]["L2_judicial"]["count"], 0)
        self.assertGreater(self.governed["candidate_layers"]["L3_cases"]["count"], 0)
        self.assertEqual(
            self.governed["candidate_layers"]["L2_judicial"]["status"],
            "candidate_requires_legal_review",
        )

    def test_all_ten_knowledge_cards_have_formal_links_and_candidate_links_are_not_gold(self) -> None:
        knowledge_ids = {
            row["subject_id"]
            for row in self.links
            if row["subject_type"] == "knowledge_card"
            and row["review_status"] == "formal_course_evidence"
        }
        self.assertEqual(len(knowledge_ids), 10)
        candidate_links = [
            row
            for row in self.links
            if row["source_layer"] in {"L2_judicial_candidate", "L3_case_candidate"}
        ]
        self.assertTrue(candidate_links)
        self.assertTrue(
            all("candidate" in row["review_status"] for row in candidate_links)
        )
        self.assertTrue(all(row["evidence_id"] is None for row in candidate_links))

    def test_rejection_log_excludes_operational_archives_cache_and_duplicates(self) -> None:
        decisions = {row["decision"] for row in self.rejections}
        self.assertIn("rejected_from_content_pipeline", decisions)
        self.assertIn("isolated_outside_scope", decisions)
        self.assertTrue(
            any(row["reason"] == "archive_not_direct_content" for row in self.rejections)
        )
        self.assertTrue(
            any(row["reason"] == "cache_or_compiled_artifact" for row in self.rejections)
        )

    def test_audit_hashes_and_boundary_text_are_current(self) -> None:
        self.assertTrue(all(self.audit["gates"].values()))
        for row in self.audit["files"]:
            self.assertEqual(sha256(REPO / row["path"]), row["sha256"])
        card = (OUTPUT / "DATASET_CARD.md").read_text(encoding="utf-8")
        self.assertIn("53 `.doc` files", card)
        self.assertNotIn("530 DOC", card)
        self.assertIn("not a training set", card)
        flow = (OUTPUT / "DATA_GOVERNANCE_FLOW.svg").read_text(encoding="utf-8")
        for value in ("4,173", "813", "20 + 27", "87 LINKS", "MODEL CALLS = 0"):
            self.assertIn(value, flow)
        self.assertNotIn("D:\\", flow)
        serialized = json.dumps(
            [self.inventory, self.governed, self.audit], ensure_ascii=False
        )
        self.assertNotRegex(serialized, r"[A-Za-z]:\\")
        self.assertNotIn("26967", serialized)


if __name__ == "__main__":
    unittest.main()
