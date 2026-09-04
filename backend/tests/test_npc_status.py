from __future__ import annotations

import unittest

from src.hybrid_rag.npc_status import iter_rechecked_laws, npc_document_id, project_npc_status, recheck_laws


class NpcStatusTests(unittest.TestCase):
    def source(self, identifier: str = "LAW_1") -> dict:
        return {
            "document_id": identifier,
            "source_type": "law",
            "title": "中华人民共和国测试法",
            "official_source_url": "https://flk.npc.gov.cn/detail.html?id=official-id",
        }

    def test_official_status_codes_map_to_public_verification_states(self) -> None:
        expected = {1: "repealed", 2: "superseded", 3: "verified_current", 4: "unresolved"}
        for code, status in expected.items():
            with self.subTest(code=code):
                row = project_npc_status(
                    self.source(),
                    {
                        "sxx": code,
                        "title": "中华人民共和国测试法",
                        "zdjgName": "全国人民代表大会常务委员会",
                        "gbrq": "2026-01-01",
                        "sxrq": "2026-02-01",
                        "flxz": "法律",
                    },
                    checked_at="2026-09-04",
                )
                self.assertEqual(row["effective_status"], status)
                self.assertTrue(row["official_title_matches"])
                self.assertEqual(row["official_status_code"], code)

    def test_title_mismatch_is_unresolved_even_if_status_code_is_current(self) -> None:
        row = project_npc_status(
            self.source(),
            {"sxx": 3, "title": "另一部法律", "flxz": "法律"},
        )
        self.assertEqual(row["effective_status"], "unresolved")
        self.assertEqual(row["verification_status"], "unresolved")

    def test_batch_recheck_is_parallel_safe_and_keeps_only_laws(self) -> None:
        rows = recheck_laws(
            [self.source("LAW_2"), self.source("LAW_1"), {**self.source("REG_1"), "source_type": "regulation"}],
            workers=4,
            fetcher=lambda _identifier: {
                "sxx": 3,
                "title": "中华人民共和国测试法",
                "flxz": "法律",
            },
        )
        self.assertEqual([row["document_id"] for row in rows], ["LAW_1", "LAW_2"])
        self.assertTrue(all(row["effective_status"] == "verified_current" for row in rows))

    def test_incremental_iterator_yields_before_batch_sorting(self) -> None:
        rows = list(
            iter_rechecked_laws(
                [self.source("LAW_1"), self.source("LAW_2")],
                workers=2,
                fetcher=lambda _identifier: {
                    "sxx": 3,
                    "title": "中华人民共和国测试法",
                    "flxz": "法律",
                },
            )
        )
        self.assertEqual({row["document_id"] for row in rows}, {"LAW_1", "LAW_2"})

    def test_only_official_npc_detail_urls_yield_ids(self) -> None:
        self.assertEqual(
            npc_document_id("https://flk.npc.gov.cn/detail.html?id=abc123"),
            "abc123",
        )
        self.assertEqual(npc_document_id("https://example.com/detail.html?id=abc123"), "")


if __name__ == "__main__":
    unittest.main()
