from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from src.knowledge.routes import router
from src.knowledge.service import KnowledgeService


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "adaptive_service" / "data"
SCHEMA_DIR = REPO_ROOT / "schemas"


def load_jsonl(name: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (DATA_DIR / name).read_text(encoding="utf-8").splitlines()
        if line
    ]


class KnowledgeContractTests(unittest.TestCase):
    def test_hybrid_candidates_are_projected_back_to_governed_articles(self) -> None:
        class FakeHybridRetriever:
            def search(self, query, **kwargs):
                return {
                    "stages": {"dense": "succeeded", "reranker": "succeeded"},
                    "results": [
                        {
                            "title": "中华人民共和国刑法（2024年最新版）",
                            "article_ref": "第二十条",
                            "quote": "候选来源中的文本不能直接替代治理法源。",
                        }
                    ],
                }

        service = KnowledgeService(hybrid_retriever=FakeHybridRetriever())
        result = service.search(query="刑法第二十条正当防卫", top_k=3)
        article = next(row for row in result["evidences"] if row["article_ref"] == "第二十条")
        self.assertNotEqual(article["quote"], "候选来源中的文本不能直接替代治理法源。")
        self.assertEqual(article["match_reasons"], ["hybrid_retrieval", "governed_article_projection"])
        self.assertIn("词法与语义融合检索", " ".join(result["warnings"]))

    def test_manifest_and_frozen_contracts_are_governed(self) -> None:
        manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["counts"], {
            "knowledge_cards": 10,
            "task_items": 30,
            "evidence_items": 22,
            "q_edges": 30,
        })
        for filename, expected in manifest["files"].items():
            actual = hashlib.sha256((DATA_DIR / filename).read_bytes()).hexdigest()
            self.assertEqual(actual, expected["sha256"])
        cards = load_jsonl("knowledge_cards.jsonl")
        tasks = load_jsonl("task_items.jsonl")
        evidence = load_jsonl("evidence_catalog.jsonl")
        payload = json.dumps(cards + tasks + evidence, ensure_ascii=False)
        self.assertNotIn("中国刑事辩护网", payload)
        self.assertNotRegex(payload, r'"[A-Za-z]:[\\/]')
        self.assertTrue(all(card["standard_evidence_ids"] for card in cards))
        self.assertTrue(all(task["standard_evidence_ids"] for task in tasks))
        card_schema = json.loads((SCHEMA_DIR / "knowledge-card-v1.schema.json").read_text(encoding="utf-8"))
        task_schema = json.loads((SCHEMA_DIR / "task-item-v1.schema.json").read_text(encoding="utf-8"))
        for row in cards:
            Draft202012Validator(card_schema).validate(row)
        for row in tasks:
            Draft202012Validator(task_schema).validate(row)

    def test_public_task_never_contains_private_answer_or_rationale(self) -> None:
        service = KnowledgeService()
        task_id = service.tasks[0]["task_id"]
        public = service.get_public_task(task_id)
        serialized = json.dumps(public, ensure_ascii=False)
        self.assertNotIn("answer_private", serialized)
        self.assertNotIn("rationale_private", serialized)
        self.assertNotIn("misconceptions_private", serialized)
        self.assertFalse(public["answer_included"])

    def test_evidence_pack_returns_exact_governed_article_and_honest_coverage(self) -> None:
        service = KnowledgeService()
        self_defense = next(
            card for card in service.cards if card["canonical_name"] == "正当防卫与防卫过当"
        )
        result = service.search(
            query="刑法第二十条正当防卫的时间与限度",
            task_type="争点辨析",
            top_k=5,
            knowledge_ids=[self_defense["knowledge_id"]],
            key_judgments=["防卫必须针对正在进行的不法侵害"],
        )
        article20 = next(
            evidence for evidence in result["evidences"] if evidence["article_ref"] == "第二十条"
        )
        self.assertEqual(article20["authority_level"], "法律")
        self.assertEqual(article20["effective_from"], "2024-03-01")
        self.assertTrue(article20["source_bundle_sha256"])
        coverage = result["coverage"]["防卫必须针对正在进行的不法侵害"]
        self.assertIn(coverage["status"], {
            "candidate_requires_semantic_audit",
            "insufficient_evidence",
        })
        self.assertIn("not semantic entailment", " ".join(result["warnings"]))
        pack_schema = json.loads((SCHEMA_DIR / "evidence-pack-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(pack_schema).validate(result)

    def test_citation_audit_checks_existence_and_quote_without_claiming_entailment(self) -> None:
        service = KnowledgeService()
        result = service.audit_citations(
            [
                {
                    "title": "刑法",
                    "article_ref": "第二十条",
                    "quote": "为了使国家、公共利益、本人或者他人的人身、财产和其他权利免受正在进行的不法侵害",
                    "claim": "正当防卫要求存在正在进行的不法侵害",
                },
                {"title": "刑法", "article_ref": "第九千条"},
            ]
        )
        self.assertEqual(result["items"][0]["status"], "valid")
        self.assertEqual(result["items"][0]["quote_status"], "exact_fragment")
        self.assertIn("semantic_entailment_not_evaluated", result["items"][0]["risk_flags"])
        self.assertEqual(result["items"][1]["status"], "invalid_article")

    def test_fastapi_contracts_are_callable(self) -> None:
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client:
            catalog = client.get("/api/knowledge/catalog")
            self.assertEqual(catalog.status_code, 200)
            self.assertEqual(catalog.json()["counts"]["knowledge_cards"], 10)
            response = client.post(
                "/api/knowledge/search",
                json={"query": "抢劫罪暴力胁迫", "top_k": 3},
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["evidences"])


if __name__ == "__main__":
    unittest.main()
