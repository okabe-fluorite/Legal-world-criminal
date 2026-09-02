from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from src.hybrid_rag.lexical_index import build_lexical_index  # noqa: E402
from src.hybrid_rag.retriever import HybridRagRetriever, public_search_result, rerank_instruction  # noqa: E402
from src.hybrid_rag.siliconflow import EmbeddingResult, RerankItem, RerankResult  # noqa: E402
from src.hybrid_rag.vector_index import IndexRecord  # noqa: E402


class FakeClient:
    def __init__(self, *, fail_embedding: bool = False, fail_rerank: bool = False) -> None:
        self.fail_embedding = fail_embedding
        self.fail_rerank = fail_rerank

    def embed(self, texts, dimensions=1024):
        if self.fail_embedding:
            raise RuntimeError("embedding unavailable")
        vector = [0.0] * dimensions
        vector[0] = 1.0
        return EmbeddingResult([vector], "test", "local", 1.0, 1, 1)

    def rerank(self, query, documents, **kwargs):
        if self.fail_rerank:
            raise RuntimeError("reranker unavailable")
        return RerankResult(
            items=[RerankItem(index=index, relevance_score=float(index), document=None) for index in reversed(range(len(documents)))],
            model="test",
            host="local",
            latency_ms=1.0,
            input_tokens=1,
            output_tokens=0,
        )


class HybridRagRetrieverTests(unittest.TestCase):
    def test_reranker_instruction_is_collection_specific(self) -> None:
        self.assertIn("教材章节", rerank_instruction("textbook_explanation"))
        self.assertIn("公开练习", rerank_instruction("question_public"))
        self.assertIn("法名条号", rerank_instruction("legal_authority"))

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.index_root = root / "indexes"
        self.corpus_root = root / "corpus"
        collection = self.index_root / "legal_authority"
        collection.mkdir(parents=True)
        self.corpus_root.mkdir(parents=True)
        rows = [
            {
                "retrieval_id": "A1",
                "source_type": "law",
                "title": "中华人民共和国刑法（2024年最新版）",
                "article_ref": "第二十条",
                "section_title": "正当防卫",
                "content": "为了使国家公共利益免受正在进行的不法侵害而采取制止行为。",
                "retrieval_text": "中华人民共和国刑法 第二十条 正当防卫 不法侵害",
                "parent_id": "",
                "governance_status": "candidate_requires_legal_review",
            },
            {
                "retrieval_id": "A2",
                "source_type": "law",
                "title": "中华人民共和国民法典",
                "article_ref": "第二十条",
                "section_title": "民事行为能力",
                "content": "不满八周岁的未成年人为无民事行为能力人。",
                "retrieval_text": "中华人民共和国民法典 第二十条 民事行为能力",
                "parent_id": "",
                "governance_status": "isolated_reference",
            },
            {
                "retrieval_id": "C1",
                "source_type": "case",
                "title": "张某正当防卫案",
                "article_ref": "",
                "section_title": "裁判规则",
                "content": "对于正在进行的不法侵害可以依法防卫。",
                "retrieval_text": "张某正当防卫案 裁判规则 不法侵害",
                "parent_id": "P1",
                "governance_status": "isolated_outside_scope",
            },
        ]
        metadata = collection / "metadata.jsonl"
        metadata.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        vectors = np.zeros((3, 1024), dtype=np.float16)
        vectors[:, 0] = 1.0
        np.save(collection / "embeddings.float16.npy", vectors)
        records = [IndexRecord(row["retrieval_id"], row["retrieval_text"], row) for row in rows]
        build_lexical_index(records, collection / "lexical.sqlite")
        (collection / "manifest.json").write_text(
            json.dumps(
                {
                    "metadata_file": "metadata.jsonl",
                    "vector_file": "embeddings.float16.npy",
                    "lexical_file": "lexical.sqlite",
                    "vector_dim": 1024,
                }
            ),
            encoding="utf-8",
        )
        (self.corpus_root / "case_parents.jsonl").write_text(
            json.dumps(
                {
                    "parent_id": "P1",
                    "title": "张某正当防卫案",
                    "section_type": "rule_reasoning",
                    "section_title": "裁判规则与理由",
                    "content": "完整的裁判规则父段内容。",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_exact_law_and_article_is_protected_from_reranker(self) -> None:
        retriever = HybridRagRetriever(index_root=self.index_root, corpus_root=self.corpus_root, client=FakeClient())
        response = retriever.search("请解释《刑法》第二十条正当防卫", top_k=2)
        self.assertEqual(response["results"][0]["retrieval_id"], "A1")
        self.assertTrue(response["results"][0]["scores"]["exact_article_protected"])

    def test_dense_failure_falls_back_to_bm25f(self) -> None:
        retriever = HybridRagRetriever(
            index_root=self.index_root,
            corpus_root=self.corpus_root,
            client=FakeClient(fail_embedding=True),
        )
        response = retriever.search("正当防卫不法侵害", top_k=2)
        self.assertEqual(response["stages"]["dense"], "fallback_to_bm25f")
        self.assertEqual(response["stages"]["reranker"], "skipped")
        self.assertTrue(response["results"])

    def test_reranker_failure_uses_rrf_and_case_hit_expands_parent(self) -> None:
        retriever = HybridRagRetriever(
            index_root=self.index_root,
            corpus_root=self.corpus_root,
            client=FakeClient(fail_rerank=True),
        )
        response = retriever.search("张某正当防卫案裁判规则", top_k=3)
        self.assertEqual(response["stages"]["reranker"], "fallback_to_rrf")
        case = next(row for row in response["results"] if row["retrieval_id"] == "C1")
        self.assertEqual(case["parent_context"]["content"], "完整的裁判规则父段内容。")

    def test_public_projection_hides_internal_ids_scores_and_machine_codes(self) -> None:
        retriever = HybridRagRetriever(index_root=self.index_root, corpus_root=self.corpus_root, client=FakeClient())
        internal = retriever.search("张某正当防卫案裁判规则", top_k=3)
        public = public_search_result(internal)
        serialized = json.dumps(public, ensure_ascii=False)
        self.assertNotIn("retrieval_id", serialized)
        self.assertNotIn('"scores"', serialized)
        self.assertNotIn("succeeded", serialized)
        self.assertNotIn("fallback_to_", serialized)
        case = next(row for row in public["results"] if row["source_type"] == "case")
        self.assertEqual(case["parent_context"]["content"], "完整的裁判规则父段内容。")

    def test_explicit_nonexistent_law_and_article_abstains(self) -> None:
        retriever = HybridRagRetriever(index_root=self.index_root, corpus_root=self.corpus_root, client=FakeClient())
        response = retriever.search("请查找《不存在的测试法》第九百九十九条", top_k=3)
        self.assertTrue(response["abstained"])
        self.assertEqual(response["results"], [])
        public = public_search_result(response)
        self.assertTrue(public["abstained"])
        self.assertIn("未找到", public["notice"])


if __name__ == "__main__":
    unittest.main()
