"""Build 10 knowledge short-answer and 3 CaseBundle role-reversal tasks."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.case_bundle.service import CaseBundleService  # noqa: E402
from src.knowledge.service import KnowledgeService  # noqa: E402

OUTPUT = REPO_ROOT / "adaptive_service" / "data" / "subjective_tasks.jsonl"
MANIFEST = REPO_ROOT / "adaptive_service" / "data" / "subjective_task_manifest.json"
SCHEMA_PATH = REPO_ROOT / "schemas" / "subjective-task-v1.schema.json"

RUBRIC = {
    "version": "subjective-rubric-v1",
    "dimensions": [
        {"code": "rule_accuracy", "name": "规范准确", "weight": 0.3},
        {"code": "fact_rule_mapping", "name": "事实与规则对应", "weight": 0.35},
        {"code": "boundary_awareness", "name": "边界与反例", "weight": 0.2},
        {"code": "evidence_use", "name": "法源证据", "weight": 0.15},
    ],
}


def stable_hash(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def task_id(seed: str) -> str:
    return f"SUBJ_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:20].upper()}"


def finalize(row: dict[str, Any]) -> dict[str, Any]:
    row["content_sha256"] = stable_hash(row)
    return row


def main() -> int:
    knowledge = KnowledgeService()
    cases = CaseBundleService()
    rows: list[dict[str, Any]] = []
    for card in knowledge.cards:
        rows.append(
            finalize(
                {
                    "schema_version": "criminal-law-subjective-task-v1",
                    "task_id": task_id(f"short|{card['knowledge_id']}|v1"),
                    "domain": "刑法",
                    "status": "pilot_teacher_approved",
                    "task_type": "short_answer",
                    "phase_eligibility": ["prestudy", "review"],
                    "knowledge_ids": [card["knowledge_id"]],
                    "knowledge_names": [card["canonical_name"]],
                    "target_abilities": ["rule_retrieval", "subsumption", "claim_construction"],
                    "difficulty": 2,
                    "cognitive_dimension": "分析",
                    "prompt": (
                        f"请用150—350字分析“{card['canonical_name']}”：先列出核心法律条件，"
                        "再自拟一组成立与不成立的对照事实，逐项说明事实如何对应条件，"
                        "并至少引用一条给定法条。不要只复述结论。"
                    ),
                    "context_public": {
                        "learning_objective": card["learning_objective"],
                        "summary": card["summary"],
                        "law_article_refs": card["law_article_refs"],
                    },
                    "response_constraints": {"min_characters": 80, "max_characters": 1200, "citations_required": True},
                    "standard_evidence_ids": card["standard_evidence_ids"],
                    "rubric_private": RUBRIC,
                    "expected_points_private": [
                        card["learning_objective"],
                        card["summary"],
                        *card["common_errors"],
                    ],
                    "review": {
                        "status": "pilot_teacher_approved",
                        "reviewer_role": "teacher_gate",
                        "teacher_recheck_required_each_term": True,
                    },
                    "source_versions": {
                        "knowledge_id": card["knowledge_id"],
                        "knowledge_content_sha256": card["content_sha256"],
                        "law_corpus_snapshot": card["law_corpus_snapshot"],
                    },
                }
            )
        )

    for bundle in cases.bundles:
        names = [item["knowledge_name"] for item in bundle["knowledge_links"]]
        rows.append(
            finalize(
                {
                    "schema_version": "criminal-law-subjective-task-v1",
                    "task_id": task_id(f"role|{bundle['case_bundle_id']}|v1"),
                    "domain": "刑法",
                    "status": "pilot_teacher_approved",
                    "task_type": "role_reversal",
                    "phase_eligibility": ["review"],
                    "knowledge_ids": [item["knowledge_id"] for item in bundle["knowledge_links"]],
                    "knowledge_names": names,
                    "target_abilities": ["claim_construction", "evidence_marshalling", "evidentiary_advocacy", "position_consistency"],
                    "difficulty": 3,
                    "cognitive_dimension": "评价",
                    "prompt": (
                        f"请站在公诉人立场，围绕“{bundle['title']}”写200—500字反驳意见："
                        "指出辩护主张可能忽略的事实与规范条件，再以辩护人身份写一句回应。"
                        "必须区分事实争议与法律争议，并至少引用一条给定法条。"
                    ),
                    "context_public": {
                        "case_bundle_id": bundle["case_bundle_id"],
                        "case_bundle_version": bundle["version"],
                        "title": bundle["title"],
                        "charge": bundle["charge"],
                        "student_brief": bundle["student_brief"],
                        "contested_issues": bundle["stage_packets"]["CR"]["student_visible"].get("contested_issues") or [],
                    },
                    "response_constraints": {"min_characters": 120, "max_characters": 1800, "citations_required": True},
                    "standard_evidence_ids": bundle["evidence_ids"],
                    "rubric_private": {
                        "version": "subjective-rubric-v1",
                        "dimensions": [
                            {"code": "counter_argument", "name": "反方主张", "weight": 0.3},
                            {"code": "fact_rule_mapping", "name": "事实与规范对应", "weight": 0.3},
                            {"code": "evidence_use", "name": "法源与证据", "weight": 0.2},
                            {"code": "position_consistency", "name": "立场回应", "weight": 0.2},
                        ],
                    },
                    "expected_points_private": [
                        "区分事实争议与规范争议",
                        "公诉反驳与辩护回应分别成段",
                        "引用受治理法条并说明连接步骤",
                    ],
                    "review": {
                        "status": "pilot_teacher_approved",
                        "reviewer_role": "teacher_gate",
                        "teacher_recheck_required_each_term": True,
                    },
                    "source_versions": {
                        "case_bundle_id": bundle["case_bundle_id"],
                        "case_bundle_content_sha256": bundle["content_sha256"],
                        "law_corpus_manifest_sha256": bundle["law_corpus_manifest_sha256"],
                    },
                }
            )
        )

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for row in rows:
        Draft202012Validator(schema).validate(row)
    OUTPUT.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8", newline="\n")
    manifest = {
        "schema_version": "criminal-law-subjective-task-manifest-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "builder": Path(__file__).name,
        "counts": {
            "subjective_tasks": len(rows),
            "short_answer": sum(row["task_type"] == "short_answer" for row in rows),
            "role_reversal": sum(row["task_type"] == "role_reversal" for row in rows),
        },
        "files": {OUTPUT.name: {"bytes": OUTPUT.stat().st_size, "sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}},
        "schema": {"path": str(SCHEMA_PATH.relative_to(REPO_ROOT)), "sha256": hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()},
        "limits": [
            "AI feedback is formative and never directly creates mastery evidence",
            "teacher review is required before eligible LearningEvent creation",
            "tasks require term-level law teacher recheck",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
