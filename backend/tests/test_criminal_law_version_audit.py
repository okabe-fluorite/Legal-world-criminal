from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "backend" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from audit_criminal_law_2024_consolidation import (  # noqa: E402
    clean_reference_text,
    compare_articles,
)


class CriminalLawVersionAuditTests(unittest.TestCase):
    def test_cleanup_separates_display_heading_and_publisher_marker(self) -> None:
        value = "【罪名】规范正文。中国刑事辩护网提供"
        self.assertEqual(clean_reference_text(value), "规范正文。")

    def test_compare_reports_missing_and_content_difference(self) -> None:
        result = compare_articles(
            {"第一条": "规范甲。", "第二条": "规范乙。", "第三条": "（删去）"},
            {"第一条": "【目的】规范甲。", "第二条": "旧规范。"},
        )
        self.assertEqual(result["exact_after_heading_and_watermark_cleanup"], 1)
        self.assertEqual(result["missing_article_refs"], ["第三条"])
        self.assertEqual(result["remaining_difference_count"], 2)
        self.assertEqual(
            [row["category"] for row in result["differences"]],
            ["content_difference", "missing_article"],
        )

    def test_committed_audit_accepts_version_year_but_rejects_dirty_reference(self) -> None:
        report = json.loads(
            (
                ROOT
                / "data_governance"
                / "CRIMINAL_LAW_2024_VERSION_AUDIT.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(report["official_version_chain"]["result_version_as_of"], "2024-03-01")
        self.assertTrue(report["all_seven_amendment_12_articles_match"])
        self.assertEqual(report["comparison"]["official_article_count"], 505)
        self.assertEqual(report["comparison"]["reference_article_count"], 504)
        self.assertEqual(report["comparison"]["exact_after_heading_and_watermark_cleanup"], 493)
        self.assertEqual(report["comparison"]["remaining_difference_count"], 12)
        self.assertFalse(report["decision"]["formal_evidence_admitted"])
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("E:\\\\", serialized)
        self.assertNotIn("D:\\\\", serialized)


if __name__ == "__main__":
    unittest.main()
