from __future__ import annotations

import json
import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path

from jsonschema import Draft202012Validator

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from src.hybrid_rag.eval_templates import build_nli_pairs, build_qrels  # noqa: E402


def legal_row(index: int, source_type: str) -> dict:
    return {
        "chunk_id": f"C{index:04d}",
        "document_id": f"D{index:04d}",
        "source_type": source_type,
        "title": f"测试{source_type}{index}",
        "article_ref": f"第{index}条" if source_type != "judicial_interpretation" else "",
        "content": f"测试内容第{index}项明确规定应当依法处理相关事项并说明适用条件。",
        "parent_id": "",
    }


class HybridRagEvalTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.legal = []
        index = 0
        for source_type, count in (("law", 60), ("regulation", 40), ("judicial_interpretation", 40)):
            for _ in range(count):
                index += 1
                self.legal.append(legal_row(index, source_type))
        self.parents = []
        for case_index in range(20):
            parent_id = f"P{case_index:03d}"
            document_id = f"CASE{case_index:03d}"
            self.parents.append(
                {
                    "parent_id": parent_id,
                    "document_id": document_id,
                    "section_type": "summary",
                    "title": f"指导案例{case_index}号测试案",
                    "content": f"本案围绕测试争议{case_index}形成裁判规则。",
                }
            )
            self.legal.append(
                {
                    "chunk_id": f"CASECHILD{case_index:03d}",
                    "document_id": document_id,
                    "source_type": "case",
                    "title": f"指导案例{case_index}号测试案",
                    "article_ref": "",
                    "content": f"案例子块{case_index}",
                    "parent_id": parent_id,
                }
            )
        self.books = [
            {
                "chunk_id": f"T{index:03d}",
                "source_path": f"book/{index}.txt",
                "subject": "刑法" if index % 2 == 0 else "刑事诉讼法",
                "section_title": f"教材小节{index}",
            }
            for index in range(30)
        ]
        self.questions = [
            {"question_id": f"Q{index:03d}", "stem": f"测试相似题目{index}应如何处理？"}
            for index in range(30)
        ]

    def test_exact_quotas_pending_labels_and_parent_links(self) -> None:
        qrels = build_qrels(
            legal_chunks=self.legal,
            case_parents=self.parents,
            textbook_chunks=self.books,
            question_public=self.questions,
        )
        self.assertEqual(len(qrels), 120)
        self.assertEqual(
            Counter(row["query_type"] for row in qrels),
            {
                "exact_article": 24,
                "judicial_rule": 16,
                "case_rule": 20,
                "textbook_explanation": 20,
                "similar_question": 20,
                "no_answer": 20,
            },
        )
        self.assertTrue(all(not row["is_gold"] for row in qrels))
        children_by_parent = defaultdict(set)
        for row in self.legal:
            if row.get("parent_id"):
                children_by_parent[row["parent_id"]].add(row["chunk_id"])
        for row in [item for item in qrels if item["query_type"] == "case_rule"]:
            self.assertEqual(set(row["positive_ids"]), children_by_parent[row["positive_parent_ids"][0]])

    def test_nli_candidates_are_balanced_pending_and_schema_valid(self) -> None:
        pairs = build_nli_pairs(self.legal)
        self.assertEqual(len(pairs), 180)
        self.assertEqual(Counter(row["candidate_label"] for row in pairs), {"entailment": 60, "contradiction": 60, "neutral": 60})
        self.assertTrue(all(row["gold_label"] is None for row in pairs))
        self.assertTrue(all(row["review_status"] == "candidate_requires_teacher_review" for row in pairs))
        schema = json.loads((REPO / "schemas" / "hybrid-rag-nli-label-v1.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        self.assertFalse([error for row in pairs for error in validator.iter_errors(row)])


if __name__ == "__main__":
    unittest.main()
