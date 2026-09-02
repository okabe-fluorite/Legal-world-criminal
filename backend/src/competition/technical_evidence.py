from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]

ARTIFACTS = {
    "data_governance": Path("data_governance/DATA_GOVERNANCE_AUDIT.json"),
    "law_version": Path("data_governance/CRIMINAL_LAW_2024_VERSION_AUDIT.json"),
    "legal_reasoning": Path("docs/LEGAL_REASONING_GATE_AUDIT.json"),
    "legal_edu_eval": Path("backend/evaluation/legal_edu_eval_v1_manifest.json"),
    "agent_ablation": Path("docs/AGENT_ABLATION_V1.json"),
    "tutor_assets": Path("frontend/src/assets/tutor/manifest.json"),
    "hybrid_rag_index": Path("docs/HYBRID_RAG_INDEX_V1_REPORT.json"),
    "hybrid_rag_ablation": Path("docs/HYBRID_RAG_ABLATION_V1.json"),
}


class TechnicalEvidenceUnavailableError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(root: Path, relative: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise TechnicalEvidenceUnavailableError(f"technical evidence artifact missing: {relative.name}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TechnicalEvidenceUnavailableError(
            f"technical evidence artifact invalid: {relative.name}"
        ) from exc
    if not isinstance(payload, dict) or not payload.get("schema_version"):
        raise TechnicalEvidenceUnavailableError(
            f"technical evidence artifact has no schema: {relative.name}"
        )
    return payload, {
        "artifact_id": relative.stem,
        "schema_version": payload["schema_version"],
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _condition_projection(row: dict[str, Any]) -> dict[str, Any]:
    usage = dict(row.get("usage") or {})
    return {
        "workflow_completed": bool(row.get("workflow_completed")),
        "state_count": len(row.get("states") or []),
        "model_calls": int(usage.get("model_calls") or 0),
        "elapsed_ms": float(usage.get("elapsed_ms") or 0.0),
        "total_tokens": int(usage.get("total_tokens") or 0),
        "gate_pass": bool(row.get("gate_pass")),
        "raw_schema_pass": bool(row.get("raw_schema_pass", row.get("gate_pass"))),
        "required_element_coverage": int(row.get("required_element_coverage") or 0),
        "required_element_total": int(row.get("required_element_total") or 0),
        "counterargument_count": int(row.get("counterargument_count") or 0),
    }


def build_technical_evidence_snapshot(
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    loaded: dict[str, dict[str, Any]] = {}
    provenance: list[dict[str, Any]] = []
    for artifact_id, relative in ARTIFACTS.items():
        payload, metadata = _load(root, relative)
        loaded[artifact_id] = payload
        provenance.append({"artifact_id": artifact_id, **metadata})

    governance = loaded["data_governance"]
    law_version = loaded["law_version"]
    reasoning = loaded["legal_reasoning"]
    benchmark = loaded["legal_edu_eval"]
    ablation = loaded["agent_ablation"]
    tutor = loaded["tutor_assets"]
    hybrid_index = loaded["hybrid_rag_index"]
    hybrid_ablation = loaded["hybrid_rag_ablation"]

    governance_gates = dict(governance.get("gates") or {})
    reasoning_checks = []
    fixtures = list(reasoning.get("fixtures") or [])
    positive = next((row for row in fixtures if row.get("actual_pass")), None)
    if positive:
        reasoning_checks = [
            str(row.get("check_id"))
            for row in (positive.get("gate_result") or {}).get("checks") or []
            if row.get("check_id")
        ]

    conditions = dict(ablation.get("conditions") or {})
    c0 = _condition_projection(dict(conditions.get("C0") or {}))
    c1 = _condition_projection(dict(conditions.get("C1") or {}))
    model_route = dict((ablation.get("fixed_conditions") or {}).get("model_route") or {})
    safe_model_route = {
        key: model_route.get(key)
        for key in ("task", "provider", "model_name", "api_base", "configured")
        if key in model_route
    }

    counts = dict(governance.get("counts") or {})
    eval_counts = dict(benchmark.get("counts") or {})
    comparison = dict(law_version.get("comparison") or {})
    agent_comparison = dict(ablation.get("automatic_comparison") or {})
    tutor_states = list(tutor.get("states") or [])
    hybrid_totals = dict(hybrid_index.get("totals") or {})
    hybrid_r4 = dict((hybrid_ablation.get("conditions") or {}).get("R4_Reranked") or {})

    pending = [
        {
            "item": "Qwen3-8B队友模型",
            "status": "pending_model_delivery",
            "required_evidence": "API、模型卡、训练manifest、日志、许可证与独立评测",
        },
        {
            "item": "LegalEduEval教师Gold",
            "status": "pending",
            "required_evidence": "法学教师逐题核对法源、答案、争议边界与Rubric",
        },
        {
            "item": "Agent双教师盲评",
            "status": str(ablation.get("teacher_blind_review") or "pending"),
            "required_evidence": "两名独立法学教师锁定A/B评分与一致性",
        },
        {
            "item": "真实目标用户与伦理",
            "status": "pending",
            "required_evidence": "至少2名目标用户、知情同意、伦理签字与团队终审",
        },
    ]

    return {
        "schema_version": "competition-technical-evidence-snapshot-v1",
        "title": "星火智学·刑法学科技术证据总账",
        "summary": {
            "candidate_files": int(counts.get("inventory_files") or 0),
            "formal_articles": int(counts.get("formal_articles") or 0),
            "reasoning_gate_checks": len(reasoning_checks),
            "benchmark_items": int(eval_counts.get("items") or 0),
            "agent_conditions": 2,
            "tutor_states": len(tutor_states),
            "hybrid_records": int(hybrid_totals.get("records") or 0),
        },
        "data_governance": {
            "snapshot_date": governance.get("snapshot_date"),
            "inventory_files": int(counts.get("inventory_files") or 0),
            "inventory_bytes": int(counts.get("inventory_bytes") or 0),
            "formal_articles": int(counts.get("formal_articles") or 0),
            "criminal_law_articles": int(comparison.get("official_article_count") or 0),
            "criminal_procedure_articles": int(counts.get("formal_articles") or 0)
            - int(comparison.get("official_article_count") or 0),
            "l2_candidates": int(counts.get("L2_candidates") or 0),
            "l3_candidates": int(counts.get("L3_candidates") or 0),
            "knowledge_evidence_links": int(counts.get("knowledge_evidence_links") or 0),
            "gates_passed": sum(bool(value) for value in governance_gates.values()),
            "gates_total": len(governance_gates),
            "model_calls": int((governance.get("execution_counts") or {}).get("model_calls") or 0),
            "version_as_of": (law_version.get("official_version_chain") or {}).get("result_version_as_of"),
            "amendment_12_matches": sum(
                bool(value) for value in (law_version.get("amendment_12_article_matches") or {}).values()
            ),
            "reference_exact_articles": int(
                comparison.get("exact_after_heading_and_watermark_cleanup") or 0
            ),
            "reference_differences": int(comparison.get("remaining_difference_count") or 0),
            "reference_formal_admission": bool(
                (law_version.get("decision") or {}).get("formal_evidence_admitted")
            ),
            "boundary": list(governance.get("boundaries") or []),
        },
        "legal_reasoning": {
            "fixture_suite_id": reasoning.get("fixture_suite_id"),
            "fixtures": int((reasoning.get("counts") or {}).get("fixtures") or 0),
            "positive_passed": int((reasoning.get("counts") or {}).get("positive_passed") or 0),
            "negative_blocked": int((reasoning.get("counts") or {}).get("negative_blocked") or 0),
            "all_expectations_met": bool(reasoning.get("all_expectations_met")),
            "model_calls": int(reasoning.get("model_calls") or 0),
            "network_calls": int(reasoning.get("network_calls") or 0),
            "checks": reasoning_checks,
            "negative_fixtures": [
                {
                    "fixture_id": str(row.get("fixture_id") or ""),
                    "failed_checks": [str(value) for value in row.get("actual_failed_checks") or []],
                }
                for row in fixtures
                if not row.get("actual_pass")
            ],
            "boundary": list(reasoning.get("evidence_boundary") or []),
        },
        "legal_edu_eval": {
            "dataset_id": benchmark.get("dataset_id"),
            "status": benchmark.get("status"),
            "gold_status": benchmark.get("gold_status"),
            "items": int(eval_counts.get("items") or 0),
            "by_type": dict(eval_counts.get("by_type") or {}),
            "by_split": dict(eval_counts.get("by_split") or {}),
            "source_families": int(eval_counts.get("source_families") or 0),
            "cross_split_family_overlap": int(
                eval_counts.get("cross_split_family_overlap") or 0
            ),
            "evaluation_matrix": dict(benchmark.get("evaluation_matrix") or {}),
            "training_manifest_check_required": bool(
                (benchmark.get("data_separation") or {}).get(
                    "training_manifest_check_required"
                )
            ),
            "boundary": list(benchmark.get("limits") or []),
        },
        "agent_ablation": {
            "protocol_id": ablation.get("protocol_id"),
            "run_status": ablation.get("run_status"),
            "case_bundle_id": (ablation.get("fixed_conditions") or {}).get("case_bundle_id"),
            "stage": (ablation.get("fixed_conditions") or {}).get("stage"),
            "model_route": safe_model_route,
            "c0": c0,
            "c1": c1,
            "comparison": {
                key: agent_comparison.get(key)
                for key in (
                    "counterargument_count_delta",
                    "elapsed_ms_delta",
                    "total_tokens_delta",
                    "elapsed_ratio_c1_over_c0",
                    "token_ratio_c1_over_c0",
                )
            },
            "teacher_blind_review": ablation.get("teacher_blind_review"),
            "schema_normalization": {
                "additional_model_calls": int(
                    (ablation.get("reprocessed_with") or {}).get(
                        "additional_model_calls"
                    )
                    or 0
                ),
                "semantic_fields_changed": bool(
                    (ablation.get("reprocessed_with") or {}).get(
                        "semantic_fields_changed"
                    )
                ),
            },
            "boundary": list(ablation.get("evidence_boundary") or []),
        },
        "interaction": {
            "tutor_states": len(tutor_states),
            "tutor_canvas": dict(tutor.get("canvas") or {}),
            "allowed_contexts": list(tutor.get("allowed_contexts") or []),
            "creates_learning_event": bool(
                (tutor.get("learning_boundary") or {}).get("creates_learning_event")
            ),
            "formal_grading_eligible": bool(
                (tutor.get("learning_boundary") or {}).get("formal_grading_eligible")
            ),
            "label": (tutor.get("identity") or {}).get("role"),
        },
        "hybrid_rag": {
            "status": hybrid_index.get("status"),
            "records": int(hybrid_totals.get("records") or 0),
            "collections": {
                key: int((value or {}).get("records") or 0)
                for key, value in (hybrid_index.get("collections") or {}).items()
            },
            "embedding_model": hybrid_index.get("embedding_model"),
            "vector_dimension": int(hybrid_index.get("vector_dimension") or 0),
            "retrieval_pipeline": "BM25F + Dense → RRF → 条号/弃权保护 → Reranker",
            "candidate_qrels": int((hybrid_ablation.get("qrels") or {}).get("total") or 0),
            "teacher_reviewed_qrels": int((hybrid_ablation.get("qrels") or {}).get("teacher_reviewed") or 0),
            "candidate_recall_at_5": float(hybrid_r4.get("recall_at_5") or 0.0),
            "candidate_ndcg_at_10": float(hybrid_r4.get("ndcg_at_10") or 0.0),
            "no_answer_false_positive_rate": float(
                hybrid_r4.get("no_answer_false_positive_rate") or 0.0
            ),
            "private_question_index": hybrid_index.get("private_question_index"),
            "boundary": hybrid_ablation.get("evidence_boundary"),
        },
        "pending": pending,
        "provenance": provenance,
        "global_boundary": [
            "automatic gates are software evidence, not expert legal accuracy",
            "MOOCCubeX ORCDF remains civil/constitutional shadow and mastery is uncalibrated",
            "candidate benchmark items are not teacher Gold",
            "fixed scripted E2E and one ablation run do not establish learning effects",
        ],
    }


__all__ = [
    "ARTIFACTS",
    "TechnicalEvidenceUnavailableError",
    "build_technical_evidence_snapshot",
]
