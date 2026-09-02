from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from src.hybrid_rag.official_verification import build_verification_records, summarize_records  # noqa: E402


class OfficialSourceVerificationTests(unittest.TestCase):
    def test_every_document_gets_record_and_agent_official_result_wins(self) -> None:
        content_hash = hashlib.sha256("条例正文".encode()).hexdigest()
        document = {
            "document_id": "RAGD_" + "A" * 24,
            "source_type": "regulation",
            "title": "测试条例",
            "document_content_sha256": content_hash,
            "source_snapshot_id": "official-test",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "laws" / "raw_data" / "行政法规"
            raw.mkdir(parents=True)
            (raw / "测试条例_20240102.txt").write_text(
                "测试条例\n2024年1月2日国务院令第99号公布\n自2024年2月1日起施行",
                encoding="utf-8",
            )
            rows = build_verification_records(
                [document],
                source_root=root,
                agent_rows=[
                    {
                        "document_id": document["document_id"],
                        "effective_status": "verified_current",
                        "verification_status": "verified",
                        "official_source_url": "https://www.gov.cn/test",
                        "verification_method": "official_primary_page_match",
                    }
                ],
                checked_at="2026-09-03",
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["evidence_source_type"], "administrative_regulation")
        self.assertEqual(rows[0]["allowed_usage"], ["normative_rule"])
        self.assertEqual(rows[0]["effective_status"], "verified_current")
        self.assertEqual(rows[0]["document_number"], "国务院令第99号")
        self.assertEqual(rows[0]["effective_date"], "2024-02-01")
        self.assertEqual(summarize_records(rows)["documents"], 1)

    def test_case_is_reference_not_normative_rule(self) -> None:
        document = {
            "document_id": "RAGD_" + "B" * 24,
            "source_type": "case",
            "title": "指导案例1号 测试案(FBM-CLI.C.1)",
            "case_id": "FBM-CLI.C.1",
            "document_content_sha256": "b" * 64,
            "source_snapshot_id": "official-test",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "laws" / "raw_data" / "指导性案例"
            raw.mkdir(parents=True)
            (raw / "指导案例1号 测试案(FBM-CLI.C.1).txt").write_text("指导案例1号", encoding="utf-8")
            row = build_verification_records([document], source_root=root, checked_at="2026-09-03")[0]
        self.assertEqual(row["allowed_usage"], ["case_reference"])
        self.assertEqual(row["effective_status"], "verified_historical")
        self.assertNotIn("normative_rule", row["allowed_usage"])


if __name__ == "__main__":
    unittest.main()
