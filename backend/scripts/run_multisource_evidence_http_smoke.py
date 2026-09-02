"""Run eight HTTP-level multi-source EvidencePack and fallback checks."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def read_env(path: Path) -> None:
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


class FailureClient:
    def __init__(self, client: Any, *, fail_embedding: bool = False, fail_reranker: bool = False) -> None:
        self.client = client
        self.fail_embedding = fail_embedding
        self.fail_reranker = fail_reranker

    def embed(self, *args: Any, **kwargs: Any) -> Any:
        if self.fail_embedding:
            raise RuntimeError("injected embedding outage")
        return self.client.embed(*args, **kwargs)

    def rerank(self, *args: Any, **kwargs: Any) -> Any:
        if self.fail_reranker:
            raise RuntimeError("injected reranker outage")
        return self.client.rerank(*args, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=REPO / ".env")
    parser.add_argument("--output", type=Path, default=REPO / "docs" / "MULTISOURCE_EVIDENCE_HTTP_SMOKE.json")
    args = parser.parse_args()
    read_env(args.env.resolve())
    os.environ["SIMLAW_HYBRID_RAG_ENABLED"] = "1"

    from src.hybrid_rag.retriever import HybridRagRetriever
    from src.hybrid_rag.runtime import clear_hybrid_rag_runtime_cache, get_hybrid_rag_retriever
    from src.knowledge import routes
    from src.knowledge.service import KnowledgeService

    clear_hybrid_rag_runtime_cache()
    retriever = get_hybrid_rag_retriever()
    if retriever is None:
        raise RuntimeError("Hybrid RAG runtime is not available")
    schema = json.loads((REPO / "schemas" / "evidence-pack-v1.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    def client_for(service: KnowledgeService, runtime: HybridRagRetriever) -> TestClient:
        routes.get_knowledge_service = lambda: service
        routes.get_hybrid_rag_retriever = lambda: runtime
        app = FastAPI()
        app.include_router(routes.router)
        return TestClient(app)

    service = KnowledgeService(hybrid_retriever=retriever)
    client = client_for(service, retriever)
    checks: list[dict[str, Any]] = []

    def pack_check(check_id: str, query: str, collections: list[str], expected_type: str) -> None:
        response = client.post(
            "/api/knowledge/search",
            json={"query": query, "top_k": 5, "collections": collections},
        )
        payload = response.json()
        schema_errors = len(list(validator.iter_errors(payload))) if response.status_code == 200 else -1
        evidences = payload.get("evidences") or []
        matched = [row for row in evidences if row.get("source_type") == expected_type]
        checks.append(
            {
                "check_id": check_id,
                "http_status": response.status_code,
                "evidence_count": len(evidences),
                "expected_source_type": expected_type,
                "expected_type_count": len(matched),
                "schema_errors": schema_errors,
                "parent_context_count": sum(bool(row.get("parent_context")) for row in evidences),
                "unresolved_notice_count": sum(row.get("effective_status") == "unresolved" for row in evidences),
                "private_answer_leak": "answer_private" in json.dumps(payload, ensure_ascii=False),
                "passed": response.status_code == 200 and schema_errors == 0 and bool(matched),
            }
        )

    pack_check("exact_law", "请解释《中华人民共和国刑法》第二十条", ["legal_authority"], "法律条文")
    pack_check("judicial_interpretation", "人民检察院刑事诉讼规则第一条如何规定", ["legal_authority"], "judicial_normative_document")
    pack_check("case_parent", "指导案例144号张那木拉正当防卫案的裁判规则", ["legal_authority"], "guiding_case")
    checks[-1]["passed"] = checks[-1]["passed"] and checks[-1]["parent_context_count"] > 0
    pack_check("textbook", "请用刑法教材解释正当防卫的成立条件", ["textbook_explanation"], "textbook_explanation")
    pack_check("similar_question", "查找抢劫罪构成要件的相似练习", ["question_public"], "learning_resource")

    missing = client.post(
        "/api/knowledge/search",
        json={"query": "请查找《不存在的测试法》第九百九十九条", "top_k": 5, "collections": ["legal_authority"]},
    )
    missing_payload = missing.json()
    checks.append(
        {
            "check_id": "explicit_missing_law",
            "http_status": missing.status_code,
            "evidence_count": len(missing_payload.get("evidences") or []),
            "coverage": [row.get("status") for row in (missing_payload.get("coverage") or {}).values()],
            "passed": missing.status_code == 200 and not missing_payload.get("evidences") and all(
                row.get("status") == "insufficient_evidence" for row in (missing_payload.get("coverage") or {}).values()
            ),
        }
    )

    def failure_runtime(*, embedding: bool = False, reranker: bool = False) -> HybridRagRetriever:
        return HybridRagRetriever(
            index_root=retriever.index_root,
            corpus_root=retriever.corpus_root,
            client=FailureClient(retriever.client, fail_embedding=embedding, fail_reranker=reranker),
            verification_path=retriever.verification_path,
        )

    for check_id, runtime, expected_method in (
        ("embedding_fallback", failure_runtime(embedding=True), "词法检索（语义服务暂不可用）"),
        ("reranker_fallback", failure_runtime(reranker=True), "词法与语义融合（重排服务暂不可用）"),
    ):
        response = client_for(KnowledgeService(hybrid_retriever=runtime), runtime).post(
            "/api/knowledge/hybrid-search",
            json={"query": "正当防卫的成立条件", "collection": "legal_authority", "top_k": 5},
        )
        payload = response.json()
        serialized = json.dumps(payload, ensure_ascii=False).lower()
        leaks = [value for value in ("retrieval_id", '"scores"', "sha256", "fallback_to_", "succeeded") if value in serialized]
        checks.append(
            {
                "check_id": check_id,
                "http_status": response.status_code,
                "retrieval_method": payload.get("retrieval_method"),
                "result_count": len(payload.get("results") or []),
                "public_internal_leaks": leaks,
                "passed": response.status_code == 200 and payload.get("retrieval_method") == expected_method and not leaks,
            }
        )

    report = {
        "schema_version": "multisource-evidence-http-smoke-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "passed": sum(bool(row["passed"]) for row in checks),
        "total": len(checks),
        "all_passed": all(bool(row["passed"]) for row in checks),
        "evidence_boundary": "HTTP and software behavior only; retrieval relevance and legal application are not expert conclusions.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "total": report["total"], "checks": checks}, ensure_ascii=False))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
