from __future__ import annotations

import unittest
from collections import OrderedDict

from scripts.build_law_corpus_from_official_docx import (
    apply_amendment_twelve,
    parse_articles_from_paragraphs,
)


class OfficialLawCorpusBuilderTests(unittest.TestCase):
    def test_parser_ignores_structure_headings_and_stops_before_appendix(self) -> None:
        rows = parse_articles_from_paragraphs(
            [
                "目录",
                "第一条　第一条正文。",
                "第一章　章名",
                "第二条　第二条第一款。",
                "第二条第二款。",
                "附件一",
                "第一条　附件中的重复条号。",
            ],
            expected_last_ref="第二条",
            stop_heading="附件一",
        )
        self.assertEqual(list(rows), ["第一条", "第二条"])
        self.assertEqual(rows["第一条"], "第一条正文。")
        self.assertEqual(rows["第二条"], "第二条第一款。\n第二条第二款。")

    def test_amendment_twelve_replaces_full_or_first_paragraph_only(self) -> None:
        base = OrderedDict(
            (
                ref,
                f"{ref}旧第一款。\n{ref}旧第二款。",
            )
            for ref in [
                "第一百六十五条",
                "第一百六十六条",
                "第一百六十九条",
                "第三百八十七条",
                "第三百九十条",
                "第三百九十一条",
                "第三百九十三条",
            ]
        )
        paragraphs = [
            "一、将刑法第一百六十五条修改为：“165新全文。”",
            "二、将刑法第一百六十六条修改为：“166新全文。”",
            "三、将刑法第一百六十九条修改为：“169新全文。”",
            "四、将刑法第三百八十七条第一款修改为：“387新第一款。”",
            "五、将刑法第三百九十条修改为：“390新全文。”",
            "六、将刑法第三百九十一条第一款修改为：“391新第一款。”",
            "七、将刑法第三百九十三条修改为：“393新全文。”",
            "八、本修正案自2024年3月1日起施行。",
        ]
        updated, changed = apply_amendment_twelve(base, paragraphs)
        self.assertEqual(len(changed), 7)
        self.assertEqual(updated["第一百六十五条"], "165新全文。")
        self.assertEqual(
            updated["第三百八十七条"],
            "387新第一款。\n第三百八十七条旧第二款。",
        )
        self.assertEqual(updated["第三百九十条"], "390新全文。")


if __name__ == "__main__":
    unittest.main()
