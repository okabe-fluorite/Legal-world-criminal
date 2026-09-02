from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from src.hybrid_rag.corpus_builder import BuildConfig, PRIVATE_FIELD_NAMES, build_corpus  # noqa: E402


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class HybridRagCorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.laws = self.root / "laws"
        for name in ("output_laws", "output_regulations", "output_judicial", "output_cases"):
            (self.laws / name).mkdir(parents=True)
        law = "《测试法》第一条规定，为了测试制定本法。\n《测试法》第二条规定，第二条正文。"
        (self.laws / "output_laws" / "测试法.txt").write_text(law, encoding="utf-8")
        (self.laws / "output_laws" / "测试法副本.txt").write_text(law, encoding="utf-8")
        (self.laws / "output_regulations" / "测试条例.txt").write_text(
            "《测试条例》第一条规定，条例正文。", encoding="utf-8"
        )
        (self.laws / "output_judicial" / "测试批复.txt").write_text(
            "这是没有条号结构的司法批复，仍应进入长度降级分块。", encoding="utf-8"
        )
        (self.laws / "output_cases" / "指导案例1号 测试案(FBM-CLI.C.1).txt").write_text(
            "【案例摘要】\n摘要内容。\n\n【基本案情精要】\n" + "案件事实。" * 180 + "\n\n【裁判要点与理由】\n裁判规则。",
            encoding="utf-8",
        )
        self.books = self.root / "reference_book"
        (self.books / "刑法").mkdir(parents=True)
        (self.books / "刑法" / "第一章 刑法概说.txt").write_text(
            json.dumps(["第一章刑法概说", "【本章主要内容提示】", "刑法基础解释。", "第一节刑法概念", "概念解释。"], ensure_ascii=False),
            encoding="utf-8",
        )
        self.tasks = self.root / "task_items.jsonl"
        self.subjective = self.root / "subjective_tasks.jsonl"
        write_jsonl(
            self.tasks,
            [
                {
                    "task_id": "OBJ_1",
                    "domain": "刑法",
                    "status": "pilot_teacher_approved",
                    "task_type": "diagnostic_item",
                    "phase_eligibility": ["prestudy", "review"],
                    "knowledge_ids": ["KP_1"],
                    "target_abilities": ["subsumption"],
                    "difficulty": 1,
                    "stem": "测试题干？",
                    "options": {"A": "正确候选", "B": "错误候选"},
                    "answer_private": ["A"],
                    "rationale_private": "私有解析",
                    "misconceptions_private": [{"description": "私有错因"}],
                    "scoring_rule": {"type": "exact"},
                }
            ],
        )
        write_jsonl(
            self.subjective,
            [
                {
                    "task_id": "SUBJ_1",
                    "domain": "刑法",
                    "status": "pilot_teacher_approved",
                    "task_type": "short_answer",
                    "phase_eligibility": ["review"],
                    "knowledge_ids": ["KP_1"],
                    "target_abilities": ["claim_construction"],
                    "difficulty": 2,
                    "prompt": "请分析测试规则。",
                    "context_public": {"summary": "公开课程摘要"},
                    "rubric_private": {"version": "v1"},
                    "expected_points_private": ["私有要点"],
                }
            ],
        )
        self.single = self.root / "0_train.json"
        self.multiple = self.root / "1_train.json"
        write_jsonl(
            self.single,
            [
                {"id": "0_1", "subject": "刑法", "type": "0", "statement": "刑法单选？", "option_list": {"A": "甲", "B": "乙"}, "answer": ["A"]},
                {"id": "0_2", "subject": "民法", "type": "0", "statement": "民法题？", "option_list": {"A": "甲"}, "answer": ["A"]},
            ],
        )
        write_jsonl(
            self.multiple,
            [{"id": "1_1", "subject": "刑法", "type": "1", "statement": "刑法多选？", "option_list": {"A": "甲", "B": "乙"}, "answer": ["A", "B"]}],
        )
        self.output = self.root / "output"
        self.config = BuildConfig(
            laws_root=self.laws,
            textbook_root=self.books,
            task_items_path=self.tasks,
            subjective_tasks_path=self.subjective,
            jecqa_single_path=self.single,
            jecqa_multiple_path=self.multiple,
            output_dir=self.output,
            snapshot_date="2026-09-02",
            target_chunk_chars=160,
            max_chunk_chars=220,
            overlap_chars=30,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_builds_canonical_parent_child_and_private_isolation(self) -> None:
        manifest, audit = build_corpus(self.config)
        self.assertTrue(audit["all_passed"], audit)
        self.assertTrue(audit["required_checks_passed"])
        self.assertIn("inventory_metadata_complete", audit["quality_warnings"])
        self.assertFalse(audit["quality_checks_passed"])
        self.assertEqual(manifest["counts"]["physical_sources"], 5)
        self.assertEqual(manifest["counts"]["canonical_documents"], 4)
        self.assertEqual(manifest["counts"]["duplicate_sources"], 1)
        self.assertEqual(manifest["counts"]["question_public"], 4)
        self.assertEqual(manifest["counts"]["question_private"], 4)
        self.assertEqual(manifest["execution"]["embedding_calls"], 0)
        self.assertEqual(manifest["execution"]["reranker_calls"], 0)
        self.assertEqual(manifest["retrieval_contract"]["reranker"], "required_after_rrf_pending_probe")

        parents = read_jsonl(self.output / "case_parents.jsonl")
        chunks = read_jsonl(self.output / "legal_chunks.jsonl")
        case_children = [row for row in chunks if row["source_type"] == "case"]
        self.assertEqual({row["section_type"] for row in parents}, {"summary", "facts", "rule_reasoning"})
        self.assertTrue(all(row["retrieval_unit"] == "child" for row in case_children))
        self.assertTrue(all(row["parent_id"] for row in case_children))
        self.assertEqual(
            {row["parent_id"] for row in case_children},
            {row["parent_id"] for row in parents},
        )

        public = read_jsonl(self.output / "question_public.jsonl")
        private = read_jsonl(self.output / "question_private.jsonl")
        self.assertFalse(set().union(*(row.keys() for row in public)) & PRIVATE_FIELD_NAMES)
        self.assertTrue(all("embed_text" in row for row in public))
        self.assertTrue(all("embed_text" not in row for row in private))
        self.assertTrue(all(row["student_retrieval_allowed"] is False for row in private))
        self.assertNotIn("民法题", "\n".join(row["stem"] for row in public))

    def test_generated_rows_match_frozen_schemas(self) -> None:
        build_corpus(self.config)
        schema_rows = [
            ("hybrid-rag-source-manifest-v1.schema.json", "source_manifest.jsonl"),
            ("hybrid-rag-document-v1.schema.json", "canonical_documents.jsonl"),
            ("hybrid-rag-chunk-v1.schema.json", "legal_chunks.jsonl"),
            ("hybrid-rag-case-parent-v1.schema.json", "case_parents.jsonl"),
            ("hybrid-rag-textbook-chunk-v1.schema.json", "textbook_chunks.jsonl"),
            ("hybrid-rag-question-public-v1.schema.json", "question_public.jsonl"),
            ("hybrid-rag-question-private-v1.schema.json", "question_private.jsonl"),
        ]
        for schema_name, data_name in schema_rows:
            schema = json.loads((REPO / "schemas" / schema_name).read_text(encoding="utf-8"))
            validator = Draft202012Validator(schema)
            for row in read_jsonl(self.output / data_name):
                errors = sorted(validator.iter_errors(row), key=lambda item: list(item.path))
                self.assertFalse(errors, f"{data_name}: {errors}")

    def test_chunk_outputs_are_deterministic(self) -> None:
        build_corpus(self.config)
        first = {
            name: (self.output / name).read_bytes()
            for name in ("source_manifest.jsonl", "canonical_documents.jsonl", "legal_chunks.jsonl", "case_parents.jsonl", "textbook_chunks.jsonl", "question_public.jsonl", "question_private.jsonl")
        }
        second_output = self.root / "output-second"
        build_corpus(BuildConfig(**{**self.config.__dict__, "output_dir": second_output}))
        for name, content in first.items():
            self.assertEqual(content, (second_output / name).read_bytes(), name)


if __name__ == "__main__":
    unittest.main()
