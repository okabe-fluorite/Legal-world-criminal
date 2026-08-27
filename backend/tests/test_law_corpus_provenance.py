from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


CORPUS_DIR = Path(__file__).resolve().parents[1] / "legal_corpus" / "processed"
MODIFIED_BY_XII = {
    "第一百六十五条",
    "第一百六十六条",
    "第一百六十九条",
    "第三百八十七条",
    "第三百九十条",
    "第三百九十一条",
    "第三百九十三条",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class LawCorpusProvenanceTests(unittest.TestCase):
    def test_governed_outputs_match_manifest_and_have_no_publisher_pollution(self) -> None:
        manifest = json.loads(
            (CORPUS_DIR / "law_corpus_manifest.json").read_text(encoding="utf-8")
        )
        criminal = load_jsonl(CORPUS_DIR / "xingfa.jsonl")
        procedure = load_jsonl(CORPUS_DIR / "xingsufa.jsonl")
        self.assertEqual(len(criminal), 505)
        self.assertEqual(len(procedure), 308)
        self.assertEqual(len({row["article_ref"] for row in criminal}), 505)
        self.assertEqual(len({row["article_ref"] for row in procedure}), 308)
        for filename, expected in manifest["outputs"].items():
            self.assertEqual(sha256(CORPUS_DIR / filename), expected)
        combined = criminal + procedure
        self.assertTrue(all(row["source_url"] == "https://flk.npc.gov.cn/" for row in combined))
        self.assertTrue(all(row["schema_version"] == "simlaw-law-article-v2" for row in combined))
        self.assertFalse(
            any(
                phrase in row["content"]
                for row in combined
                for phrase in ("中国刑事辩护网", "华律网", "找法网")
            )
        )

    def test_article_200_and_amendment_twelve_are_present(self) -> None:
        criminal = {
            row["article_ref"]: row for row in load_jsonl(CORPUS_DIR / "xingfa.jsonl")
        }
        self.assertIn("第二百条", criminal)
        self.assertIn(
            "单位犯本节第一百九十四条、第一百九十五条规定之罪",
            criminal["第二百条"]["content"],
        )
        modified = {
            ref for ref, row in criminal.items() if row.get("article_modified_by")
        }
        self.assertEqual(modified, MODIFIED_BY_XII)
        self.assertIn("前款所列单位，在经济往来中", criminal["第三百八十七条"]["content"])
        self.assertIn("单位犯前款罪的", criminal["第三百九十一条"]["content"])


if __name__ == "__main__":
    unittest.main()
