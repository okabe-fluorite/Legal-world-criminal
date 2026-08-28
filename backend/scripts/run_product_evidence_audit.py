"""Run deterministic product-mechanism audits without LLM or classroom data.

This script measures governed retrieval/citation behavior and adaptive ranking
mechanics. It deliberately does not report learning gain, path efficacy, legal
entailment, or calibrated mastery.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
ADAPTIVE_SRC = REPO_ROOT / "adaptive_service" / "src"
for entry in (BACKEND_DIR, ADAPTIVE_SRC):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from edubrain_adaptive.service import AdaptiveService  # noqa: E402
from edubrain_adaptive.store import AdaptiveStore  # noqa: E402
from src.case_bundle.service import CaseBundleService, PRIVATE_KEYS  # noqa: E402
from src.knowledge.service import KnowledgeService  # noqa: E402
from src.utils.model_config import MODEL_TASKS, ModelEndpoint  # noqa: E402


AUDIT_VERSION = "product-evidence-audit-v1"
FIXED_TIMESTAMP = "2026-08-27T00:00:00+00:00"
PRIVATE_FIELDS = {"answer_private", "rationale_private", "misconceptions_private"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nested_keys(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from nested_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_keys(child)


def git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def first_rank(rows: list[dict[str, Any]], knowledge_id: str) -> int | None:
    for index, row in enumerate(rows, start=1):
        if str(row.get("knowledge_id") or "") == knowledge_id:
            return index
    return None


def retrieval_audit(knowledge: KnowledgeService) -> dict[str, Any]:
    cases = []
    bm25_hits = 0
    governed_hits = 0
    honest_coverage = True
    for card in knowledge.cards:
        expected = set(card.get("law_article_refs") or [])
        query = f"{card['canonical_name']} {card['summary']}"
        bm25 = knowledge.search(query=query, top_k=5)
        governed = knowledge.search(
            query=query,
            top_k=5,
            knowledge_ids=[card["knowledge_id"]],
            key_judgments=[card["learning_objective"]],
        )
        bm25_refs = {str(row.get("article_ref") or "") for row in bm25["evidences"]}
        governed_refs = {
            str(row.get("article_ref") or "") for row in governed["evidences"]
        }
        bm25_found = bool(expected & bm25_refs)
        governed_found = bool(expected & governed_refs)
        bm25_hits += int(bm25_found)
        governed_hits += int(governed_found)
        statuses = {
            str(row.get("status") or "") for row in governed.get("coverage", {}).values()
        }
        honest_coverage = honest_coverage and statuses.issubset(
            {"candidate_requires_semantic_audit", "insufficient_evidence"}
        )
        cases.append(
            {
                "knowledge_id": card["knowledge_id"],
                "knowledge_name": card["canonical_name"],
                "expected_article_refs": sorted(expected),
                "bm25_top5_refs": sorted(bm25_refs),
                "governed_top5_plus_standard_refs": sorted(governed_refs),
                "bm25_expected_hit": bm25_found,
                "governed_expected_hit": governed_found,
                "coverage_statuses": sorted(statuses),
            }
        )

    citations = [
        {
            "title": row["source_title"],
            "article_ref": row["article_ref"],
            "quote": row["quote"],
            "claim": "",
        }
        for row in knowledge.evidence_catalog
    ]
    citation_result = knowledge.audit_citations(citations)
    exact_quotes = sum(
        1 for row in citation_result["items"] if row["quote_status"] == "exact_fragment"
    )
    return {
        "query_count": len(cases),
        "bm25_expected_hit_rate_at_5": round(bm25_hits / max(1, len(cases)), 4),
        "governed_expected_hit_rate_at_5": round(governed_hits / max(1, len(cases)), 4),
        "coverage_status_boundary_passed": honest_coverage,
        "citation_catalog_count": len(citations),
        "citation_valid_count": citation_result["summary"]["valid"],
        "exact_quote_count": exact_quotes,
        "semantic_entailment_evaluated": False,
        "cases": cases,
    }


def adaptive_audit(data_dir: Path) -> dict[str, Any]:
    missing_rank_pairs = []
    confusion_rank_pairs = []
    answer_leaks = []
    completed_exclusion_passed = True
    with tempfile.TemporaryDirectory() as temp:
        service = AdaptiveService(
            data_dir=data_dir,
            store=AdaptiveStore(Path(temp) / "adaptive-audit.db"),
        )
        for index, card in enumerate(service.nodes):
            knowledge_id = str(card["knowledge_id"])
            cold_student = f"audit-missing-{index}"
            cold = service.recommendations(cold_student, limit=30)
            cold_rank = first_rank(cold, knowledge_id)
            missing = service.ingest(
                {
                    "schema_version": "edubrain-learning-event-v2",
                    "event_id": f"audit-missing-event-{index}",
                    "event_type": "case_stage_assessment",
                    "student_pseudonym": cold_student,
                    "course_id": "undergraduate-criminal-law",
                    "task_id": f"audit-case-stage-{index}",
                    "capability_scores": {},
                    "knowledge_evidence": [
                        {
                            "knowledge_id": knowledge_id,
                            "knowledge_name": card["canonical_name"],
                            "normalization_status": "canonical",
                            "status": "missing",
                        }
                    ],
                    "error_tags": [],
                    "evidence_eligibility": {"long_term_profile": True},
                }
            )
            missing_rank_pairs.append(
                {
                    "knowledge_id": knowledge_id,
                    "cold_rank": cold_rank,
                    "after_missing_rank": first_rank(missing["recommendations"], knowledge_id),
                }
            )

            confusion_student = f"audit-confusion-{index}"
            confusion_cold = service.recommendations(confusion_student, limit=30)
            target_task_id = service.items_by_knowledge[knowledge_id][0]
            confusion = service.annotate_confusion(
                {
                    "schema_version": "criminal-law-confusion-annotation-v1",
                    "annotation_id": f"audit-confusion-{index}",
                    "student_pseudonym": confusion_student,
                    "course_id": "undergraduate-criminal-law",
                    "phase": "prestudy",
                    "task_id": target_task_id,
                    "knowledge_id": knowledge_id,
                    "confusion_type": "fact_application",
                    "note": "deterministic audit self-report",
                    "request_help": True,
                    "submitted_at": FIXED_TIMESTAMP,
                }
            )
            confusion_rank_pairs.append(
                {
                    "knowledge_id": knowledge_id,
                    "cold_rank": first_rank(confusion_cold, knowledge_id),
                    "after_confusion_rank": first_rank(
                        confusion["recommendations"], knowledge_id
                    ),
                }
            )

        attempt_task = service.approved[0]
        attempt = service.submit_attempt(
            {
                "schema_version": "criminal-law-task-attempt-v1",
                "attempt_id": "audit-completed-exclusion",
                "student_pseudonym": "audit-attempt-student",
                "course_id": "undergraduate-criminal-law",
                "task_id": attempt_task["task_id"],
                "content_version": attempt_task["content_sha256"],
                "phase": "review",
                "selected_options": list(attempt_task["answer_private"]),
                "submitted_at": FIXED_TIMESTAMP,
                "response_time_ms": 10000,
                "confidence": 3,
                "hint_count": 0,
                "answer_revealed_before_submit": False,
            }
        )
        completed_exclusion_passed = attempt_task["task_id"] not in {
            str(row.get("task_id") or "") for row in attempt["recommendations"]
        }
        answer_leaks = sorted(PRIVATE_FIELDS & set(nested_keys(attempt["recommendations"])))

    missing_improvements = [
        row["cold_rank"] - row["after_missing_rank"]
        for row in missing_rank_pairs
        if row["cold_rank"] is not None and row["after_missing_rank"] is not None
    ]
    confusion_improvements = [
        row["cold_rank"] - row["after_confusion_rank"]
        for row in confusion_rank_pairs
        if row["cold_rank"] is not None and row["after_confusion_rank"] is not None
    ]
    return {
        "knowledge_count": len(missing_rank_pairs),
        "missing_signal_mean_rank_improvement": round(mean(missing_improvements), 4),
        "missing_signal_rank1_count": sum(
            row["after_missing_rank"] == 1 for row in missing_rank_pairs
        ),
        "confusion_signal_mean_rank_improvement": round(
            mean(confusion_improvements), 4
        ),
        "confusion_signal_rank1_count": sum(
            row["after_confusion_rank"] == 1 for row in confusion_rank_pairs
        ),
        "completed_task_exclusion_passed": completed_exclusion_passed,
        "recommendation_private_field_leaks": answer_leaks,
        "missing_rank_pairs": missing_rank_pairs,
        "confusion_rank_pairs": confusion_rank_pairs,
        "learning_gain_evaluated": False,
        "path_effect_evaluated": False,
    }


def public_projection_audit(knowledge: KnowledgeService) -> dict[str, Any]:
    payload = {
        "catalog": knowledge.catalog(),
        "tasks": [knowledge.get_public_task(task["task_id"]) for task in knowledge.tasks],
    }
    leaks = sorted(PRIVATE_FIELDS & set(nested_keys(payload)))
    return {
        "knowledge_cards": len(knowledge.cards),
        "public_tasks": len(knowledge.tasks),
        "private_field_leaks": leaks,
        "answer_included_false_count": sum(
            task.get("answer_included") is False for task in payload["tasks"]
        ),
    }


def model_routing_audit() -> dict[str, Any]:
    secret = "audit-secret-must-not-serialize"
    endpoint = ModelEndpoint(
        task="teaching_judge",
        provider="audit",
        model_name="audit-model",
        api_base_url="https://models.example/private/path",
        api_key=secret,
        timeout_seconds=30,
    )
    safe = endpoint.safe_dict()
    serialized = json.dumps(safe, ensure_ascii=False)
    return {
        "registered_tasks": list(MODEL_TASKS),
        "safe_catalog_api_key_absent": "api_key" not in safe and secret not in serialized,
        "safe_catalog_url_path_absent": "/private/path" not in serialized,
        "failover_behavior_test_file_sha256": sha256(
            REPO_ROOT / "backend" / "tests" / "test_model_config.py"
        ),
        "live_model_called": False,
    }


def case_bundle_audit() -> dict[str, Any]:
    service = CaseBundleService()
    leaks = []
    stage_checks = 0
    for bundle in service.bundles:
        for stage in (None, "LC", "INV", "PR", "DS", "CR", "CRA"):
            public = service.public_bundle(bundle["runtime_case_id"], stage=stage)
            stage_checks += 1
            found = sorted(PRIVATE_KEYS & set(nested_keys(public)))
            if found:
                leaks.append(
                    {
                        "runtime_case_id": bundle["runtime_case_id"],
                        "stage": stage,
                        "private_keys": found,
                    }
                )
    mapping = {
        runtime_id: int(row["original_case_id"])
        for runtime_id, row in service.manifest["runtime_mapping"].items()
    }
    return {
        "case_bundle_count": len(service.bundles),
        "case_evidence_count": len(service.evidence),
        "runtime_to_original_mapping": mapping,
        "mapping_matches_seed_policy": mapping
        == {"case_1": 1, "case_2": 3, "case_3": 2},
        "public_stage_projection_checks": stage_checks,
        "private_projection_leaks": leaks,
        "unresolved_legal_basis_case_count": sum(
            bool(bundle.get("unresolved_legal_basis_fragments"))
            for bundle in service.bundles
        ),
    }


def build_report() -> dict[str, Any]:
    knowledge = KnowledgeService()
    data_dir = REPO_ROOT / "adaptive_service" / "data"
    report = {
        "schema_version": AUDIT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "protocol": {
            "seed": 20260827,
            "network_calls": 0,
            "llm_calls": 0,
            "classroom_records": 0,
            "scope": "deterministic software-mechanism audit",
        },
        "inputs": {
            "audit_script_sha256": sha256(Path(__file__).resolve()),
            "content_manifest_sha256": sha256(data_dir / "manifest.json"),
            "law_manifest_sha256": sha256(
                REPO_ROOT
                / "backend"
                / "legal_corpus"
                / "processed"
                / "law_corpus_manifest.json"
            ),
            "real_e2e_audit_sha256": sha256(REPO_ROOT / "docs" / "REAL_E2E_AUDIT.md"),
            "case_bundle_manifest_sha256": sha256(
                REPO_ROOT / "dataset" / "case_bundle_manifest.json"
            ),
        },
        "case_bundles": case_bundle_audit(),
        "retrieval_and_citation": retrieval_audit(knowledge),
        "adaptive_mechanism": adaptive_audit(data_dir),
        "public_projection": public_projection_audit(knowledge),
        "model_routing": model_routing_audit(),
        "agent_pipeline": {
            "current_evidence": "real six-stage E2E documented separately",
            "real_e2e_document": "docs/REAL_E2E_AUDIT.md",
            "agent_ablation_run_in_this_audit": False,
            "learning_gain_evaluated": False,
        },
        "evidence_boundary": {
            "proves": [
                "governed statute retrieval returns expected course-law candidates",
                "citation existence and exact quote checks are deterministic",
                "missing/confusion signals change recommendation rank as implemented",
                "completed tasks are excluded and public projections omit private fields",
                "model route catalog redacts keys and URL paths",
            ],
            "does_not_prove": [
                "legal semantic entailment",
                "criminal-law mastery calibration",
                "student learning gain",
                "adaptive path causal effect",
                "LLM scoring validity or formal-grade suitability",
            ],
        },
    }
    checks = {
        "retrieval_governed_all_hit": (
            report["retrieval_and_citation"]["governed_expected_hit_rate_at_5"] == 1.0
        ),
        "citations_all_valid": (
            report["retrieval_and_citation"]["citation_valid_count"]
            == report["retrieval_and_citation"]["citation_catalog_count"]
            == report["retrieval_and_citation"]["exact_quote_count"]
        ),
        "coverage_boundary": report["retrieval_and_citation"][
            "coverage_status_boundary_passed"
        ],
        "missing_signals_rank_first": (
            report["adaptive_mechanism"]["missing_signal_rank1_count"]
            == report["adaptive_mechanism"]["knowledge_count"]
        ),
        "confusion_signals_rank_first": (
            report["adaptive_mechanism"]["confusion_signal_rank1_count"]
            == report["adaptive_mechanism"]["knowledge_count"]
        ),
        "completed_task_excluded": report["adaptive_mechanism"][
            "completed_task_exclusion_passed"
        ],
        "answer_isolation": not report["adaptive_mechanism"][
            "recommendation_private_field_leaks"
        ]
        and not report["public_projection"]["private_field_leaks"],
        "model_catalog_redaction": report["model_routing"][
            "safe_catalog_api_key_absent"
        ]
        and report["model_routing"]["safe_catalog_url_path_absent"],
        "case_bundle_runtime_mapping": report["case_bundles"][
            "mapping_matches_seed_policy"
        ],
        "case_bundle_public_projection": not report["case_bundles"][
            "private_projection_leaks"
        ],
    }
    report["checks"] = checks
    report["status"] = "pass" if all(checks.values()) else "fail"
    return report


def markdown_summary(report: dict[str, Any]) -> str:
    retrieval = report["retrieval_and_citation"]
    adaptive = report["adaptive_mechanism"]
    lines = [
        "# 产品机制证据审计",
        "",
        f"- 协议：`{report['schema_version']}`",
        f"- Git：`{report['git_commit']}`",
        f"- 结果：**{report['status'].upper()}**",
        "- 本次调用：网络0、LLM 0、真实课堂记录0",
        "",
        "## 机制结果",
        "",
        "| 项目 | 结果 | 可解释边界 |",
        "|---|---:|---|",
        f"| 10个课程查询BM25 expected-hit@5 | {retrieval['bm25_expected_hit_rate_at_5']:.2%} | 只表示候选召回 |",
        f"| KnowledgeCard标准证据增强 expected-hit@5 | {retrieval['governed_expected_hit_rate_at_5']:.2%} | 不表示法律蕴含 |",
        f"| 证据目录有效条号/逐字片段 | {retrieval['citation_valid_count']}/{retrieval['exact_quote_count']} | 确定性存在与原文检查 |",
        f"| CaseBundle运行映射/公开投影 | {'通过' if report['case_bundles']['mapping_matches_seed_policy'] and not report['case_bundles']['private_projection_leaks'] else '失败'} | 3案×7种公开投影，不含教师参考字段 |",
        f"| missing信号平均排序提升 | {adaptive['missing_signal_mean_rank_improvement']:.2f}位 | 软件策略响应，不是学习效果 |",
        f"| confusion信号平均排序提升 | {adaptive['confusion_signal_mean_rank_improvement']:.2f}位 | 自报信号响应，不是负掌握证据 |",
        f"| 已答任务排除 | {'通过' if adaptive['completed_task_exclusion_passed'] else '失败'} | 只验证任务闭环 |",
        f"| 私有字段泄漏 | {len(adaptive['recommendation_private_field_leaks'])} | 推荐/公开投影 |",
        "",
        "## 结论边界",
        "",
        "本审计证明受治理检索、确定性引用核验、自适应排序、已答排除、答案隔离和模型目录脱敏按当前代码工作。它不评估法律语义蕴含、刑法掌握校准、学生学习增益、路径因果效果或LLM正式成绩效度。Agent六阶段真实E2E证据仍见`docs/REAL_E2E_AUDIT.md`，本脚本没有再次调用模型，也没有制造所谓Agent消融结果。",
        "",
        "完整逐知识点结果见同名JSON。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=REPO_ROOT / "docs" / "PRODUCT_EVIDENCE_AUDIT.json",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=REPO_ROOT / "docs" / "PRODUCT_EVIDENCE_AUDIT.md",
    )
    args = parser.parse_args()
    report = build_report()
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(markdown_summary(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "json_output": str(args.json_output),
                "markdown_output": str(args.markdown_output),
                "checks": report["checks"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
