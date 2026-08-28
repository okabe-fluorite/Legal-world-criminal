"""Build governed CaseBundle records from the three released criminal cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
SCRIPTS_DIR = BACKEND_DIR / "scripts"
for entry in (BACKEND_DIR, SCRIPTS_DIR):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from audit_case_dataset import audit_case  # noqa: E402
from src.case_bundle.selection import select_diverse_cases  # noqa: E402
from src.knowledge.service import KnowledgeService  # noqa: E402
from src.teaching.rubrics import (  # noqa: E402
    CAPABILITIES,
    STAGE_CAPABILITY_MATRIX,
    STAGE_NAMES,
)


DEFAULT_SOURCE = REPO_ROOT / "dataset" / "released_case_dataset.json"
DEFAULT_BUNDLES = REPO_ROOT / "dataset" / "case_bundles.jsonl"
DEFAULT_EVIDENCE = REPO_ROOT / "dataset" / "case_bundle_evidence.jsonl"
DEFAULT_MANIFEST = REPO_ROOT / "dataset" / "case_bundle_manifest.json"
LAW_MANIFEST = BACKEND_DIR / "legal_corpus" / "processed" / "law_corpus_manifest.json"
CASE_SCHEMA = REPO_ROOT / "schemas" / "case-bundle-v1.schema.json"
EVIDENCE_SCHEMA = REPO_ROOT / "schemas" / "evidence-pack-v1.schema.json"
BUNDLE_VERSION = "2026-08-27.1"
ARTICLE_RE = re.compile(r"第[零〇一二三四五六七八九十百千万两]+条")


STAGE_ERRORS = {
    "LC": ["未核实委托关系与当事人身份", "在事实未查清前承诺案件结果"],
    "INV": ["忽略强制措施期限与会见权", "只陈述结论而不核对取保事实"],
    "PR": ["未区分定罪证据与量刑材料", "忽略不起诉或罪名调整的论证路径"],
    "DS": ["辩护主张没有事实与法条双重支撑", "无罪、罪轻与量刑意见层级混乱"],
    "CR": ["质证意见只表态不说明真实性合法性关联性", "庭审立场与书面辩护相互冲突"],
    "CRA": ["上诉理由没有回应一审裁判逻辑", "忽略上诉不加刑与二审审查范围"],
}


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def stable_hash(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return digest_bytes(body.encode("utf-8"))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        for row in rows
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(body, encoding="utf-8", newline="\n")
    temporary.replace(path)


def article_refs(legal_basis: str) -> list[str]:
    return list(dict.fromkeys(ARTICLE_RE.findall(str(legal_basis or ""))))


def unresolved_fragments(legal_basis: str) -> list[str]:
    text = str(legal_basis or "").strip()
    flags = []
    if "以原判为准" in text:
        flags.append("一审定罪的其他具体条文以原判为准（未在发布记录中逐条展开）")
    return flags


def rubric(stage: str) -> dict[str, Any]:
    return {
        "schema_version": "criminal-law-stage-rubric-v1",
        "stage": stage,
        "capabilities": [
            {
                "code": code,
                "name": CAPABILITIES[code]["name"],
                "role": role,
                "weight": 1.0 if role == "primary" else 0.5,
            }
            for code, role in STAGE_CAPABILITY_MATRIX[stage].items()
        ],
    }


def stage_packet(
    stage: str,
    *,
    student_visible: dict[str, Any],
    teacher_reference: dict[str, Any],
    typical_errors: list[str],
    availability: str = "available",
) -> dict[str, Any]:
    return {
        "stage": stage,
        "stage_name": STAGE_NAMES[stage],
        "availability": availability,
        "student_visible": student_visible,
        "rubric": rubric(stage),
        "teacher_reference_private": teacher_reference,
        "typical_errors_private": list(dict.fromkeys(typical_errors + STAGE_ERRORS[stage])),
    }


def build_stage_packets(info: dict[str, Any], common_errors: list[str]) -> dict[str, Any]:
    investigation = info.get("investigation_stage") or {}
    prosecution = info.get("prosecution_stage") or {}
    defense = info.get("defense_stage") or {}
    trial = info.get("trial_stage") or {}
    appeal = info.get("appeal_stage") or {}
    party = info.get("party_info") or {}
    defendant = party.get("defendant") or {}
    has_appeal = bool(appeal.get("has_appeal"))
    return {
        "LC": stage_packet(
            "LC",
            student_visible={
                "case_summary": investigation.get("case_summary") or info.get("case_background"),
                "defendant_role": {
                    "display_name": defendant.get("name"),
                    "type": defendant.get("type"),
                },
                "initial_questions": defendant.get("questions") or [],
            },
            teacher_reference={
                "case_background": info.get("case_background"),
                "fact_collection_focus": investigation.get("key_facts_for_bail") or [],
            },
            typical_errors=common_errors,
        ),
        "INV": stage_packet(
            "INV",
            student_visible={
                "suspect_identity": investigation.get("suspect_identity"),
                "suspected_charge": investigation.get("suspected_charge"),
                "custody_status": investigation.get("custody_status"),
                "detention_date": investigation.get("detention_date"),
                "bail_status": investigation.get("bail_status"),
                "case_summary": investigation.get("case_summary"),
            },
            teacher_reference={
                "key_facts_for_bail": investigation.get("key_facts_for_bail") or [],
                "expected_lawyer_actions": investigation.get("lawyer_actions") or [],
            },
            typical_errors=common_errors,
        ),
        "PR": stage_packet(
            "PR",
            student_visible={
                "indictment_summary": prosecution.get("indictment_summary"),
                "evidence_catalog": prosecution.get("evidence_catalog") or [],
                "sentencing_factors": prosecution.get("sentencing_factors") or [],
            },
            teacher_reference={
                "defense_opportunities": prosecution.get("defense_opportunities") or [],
                "non_prosecution_arguments": prosecution.get("non_prosecution_arguments") or [],
            },
            typical_errors=common_errors,
        ),
        "DS": stage_packet(
            "DS",
            student_visible={
                "charge": defense.get("charge") or info.get("charge"),
                "facts_agreed": defense.get("facts_agreed") or [],
                "facts_disputed": defense.get("facts_disputed") or [],
                "mitigating_factors": defense.get("mitigating_factors") or [],
            },
            teacher_reference={
                "defense_positions": defense.get("defense_positions") or [],
                "guiding_points": info.get("guiding_points"),
                "defense_hint": info.get("defense_hint"),
            },
            typical_errors=common_errors,
        ),
        "CR": stage_packet(
            "CR",
            student_visible={
                "prosecution_claims": trial.get("prosecution_claims") or [],
                "contested_issues": trial.get("contested_issues") or [],
                "evidence_confrontation_points": trial.get("evidence_confrontation_points") or [],
            },
            teacher_reference={
                "reference_judgment": trial.get("reference_judgment"),
                "court_finding": (info.get("first_instance") or {}).get("court_finding"),
                "court_opinion": (info.get("first_instance") or {}).get("court_opinion"),
                "guiding_points": info.get("guiding_points"),
            },
            typical_errors=common_errors,
        ),
        "CRA": stage_packet(
            "CRA",
            availability="available" if has_appeal else "not_applicable",
            student_visible=(
                {
                    "first_verdict_summary": appeal.get("first_verdict_summary"),
                    "appeal_reasons": appeal.get("appeal_reasons") or [],
                }
                if has_appeal
                else {"not_applicable_reason": "发布案例记录显示未进入二审"}
            ),
            teacher_reference={
                "second_instance_grounds": appeal.get("second_instance_grounds") or [],
                "second_instance": info.get("second_instance") or {},
            },
            typical_errors=common_errors,
        ),
    }


def bundle_id(record: dict[str, Any]) -> str:
    provenance = record.get("provenance") or {}
    seed = f"{record.get('original_id')}|{provenance.get('local_source_sha256')}"
    return f"CRIM_CASE_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:20].upper()}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--bundles-output", type=Path, default=DEFAULT_BUNDLES)
    parser.add_argument("--evidence-output", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    source = args.source.resolve()
    records = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(records, list) or not records:
        raise ValueError("released case dataset must be a non-empty list")
    for record in records:
        audit = audit_case(record)
        if not audit["releasable"]:
            raise ValueError(f"unreleasable case {record.get('original_id')}: {audit['flags']}")

    selected = select_diverse_cases(list(records), len(records))
    knowledge = KnowledgeService()
    law_manifest_sha = digest_file(LAW_MANIFEST)
    source_sha = digest_file(source)
    evidence_by_id: dict[str, dict[str, Any]] = {}
    bundles = []

    for index, record in enumerate(selected, start=1):
        info = record.get("extracted_info") or {}
        links = []
        common_errors = []
        for link in info.get("knowledge_points") or []:
            card = knowledge.card_by_id.get(str(link.get("knowledge_id") or ""))
            if card is None:
                raise ValueError(f"case {record.get('original_id')} has unknown knowledge link")
            links.append(
                {
                    "knowledge_id": card["knowledge_id"],
                    "knowledge_name": card["canonical_name"],
                    "role": str(link.get("role") or "secondary"),
                    "knowledge_version": card["content_sha256"],
                }
            )
            common_errors.extend(str(value) for value in card.get("common_errors") or [])

        legal_basis = str((info.get("first_instance") or {}).get("legal_basis") or "")
        evidence_ids = []
        for article_ref in article_refs(legal_basis):
            evidence = knowledge.evidence_for_article("刑法", article_ref)
            if evidence is None:
                raise ValueError(
                    f"case {record.get('original_id')} references missing governed article {article_ref}"
                )
            evidence.pop("relevance", None)
            evidence.pop("match_reasons", None)
            evidence_by_id[evidence["evidence_id"]] = evidence
            evidence_ids.append(evidence["evidence_id"])

        provenance = dict(record.get("provenance") or {})
        local_path = str(provenance.get("local_source_path") or "")
        if re.match(r"^[A-Za-z]:[\\/]", local_path) or local_path.startswith(("/", "\\")):
            raise ValueError("CaseBundle provenance must keep a relative local source path")
        stage_packets = build_stage_packets(info, common_errors)
        release = dict(record.get("release") or {})
        bundle = {
            "schema_version": "criminal-law-case-bundle-v1",
            "case_bundle_id": bundle_id(record),
            "runtime_case_id": f"case_{index}",
            "original_case_id": int(record["original_id"]),
            "domain": "刑法",
            "version": BUNDLE_VERSION,
            "title": str(provenance.get("source_title") or info.get("source_title") or ""),
            "case_type": str(info.get("case_type") or "刑事案件"),
            "case_category": "criminal",
            "case_cause": str(info.get("case_cause") or info.get("charge") or ""),
            "charge": str(info.get("charge") or info.get("case_cause") or ""),
            "release": release,
            "provenance": provenance,
            "knowledge_links": links,
            "evidence_ids": list(dict.fromkeys(evidence_ids)),
            "unresolved_legal_basis_fragments": unresolved_fragments(legal_basis),
            "student_brief": {
                "title": str(provenance.get("source_title") or info.get("source_title") or ""),
                "case_cause": str(info.get("case_cause") or ""),
                "initial_charge": str(info.get("charge") or ""),
                "defendant_type": str(
                    ((info.get("party_info") or {}).get("defendant") or {}).get("type") or ""
                ),
                "knowledge_ids": [link["knowledge_id"] for link in links],
            },
            "stage_packets": stage_packets,
            "reference_private": {
                "stage_gold": {
                    "LC": {"investigation_stage": info.get("investigation_stage") or {}},
                    "INV": {"investigation_stage": info.get("investigation_stage") or {}},
                    "PR": {"prosecution_stage": info.get("prosecution_stage") or {}},
                    "DS": {
                        "defense_stage": info.get("defense_stage") or {},
                        "guiding_points": info.get("guiding_points"),
                        "defense_hint": info.get("defense_hint"),
                    },
                    "CR": {
                        "trial_stage": info.get("trial_stage") or {},
                        "guiding_points": info.get("guiding_points"),
                    },
                    "CRA": {"appeal_stage": info.get("appeal_stage") or {}},
                },
                "first_instance": info.get("first_instance") or {},
                "second_instance": info.get("second_instance") or {},
                "guiding_points": info.get("guiding_points"),
                "defense_hint": info.get("defense_hint"),
            },
            "review": {
                "status": str(release.get("release_status") or ""),
                "intended_use": str(release.get("intended_use") or ""),
                "not_for": str(release.get("not_for") or ""),
                "teacher_recheck_required": bool(
                    release.get("human_law_teacher_recheck_required", True)
                ),
                "reviewed_at": str(release.get("reviewed_at") or ""),
                "risk_flags": (
                    ["unresolved_legal_basis_requires_teacher_review"]
                    if unresolved_fragments(legal_basis)
                    else []
                ),
            },
            "source_dataset_sha256": source_sha,
            "law_corpus_manifest_sha256": law_manifest_sha,
        }
        bundle["content_sha256"] = stable_hash(bundle)
        bundles.append(bundle)

    case_schema = json.loads(CASE_SCHEMA.read_text(encoding="utf-8"))
    evidence_schema = json.loads(EVIDENCE_SCHEMA.read_text(encoding="utf-8"))["$defs"][
        "evidenceItem"
    ]
    for bundle in bundles:
        Draft202012Validator(case_schema).validate(bundle)
    evidence_rows = sorted(evidence_by_id.values(), key=lambda row: row["evidence_id"])
    for evidence in evidence_rows:
        Draft202012Validator(evidence_schema).validate(evidence)

    write_jsonl(args.bundles_output.resolve(), bundles)
    write_jsonl(args.evidence_output.resolve(), evidence_rows)
    manifest = {
        "schema_version": "criminal-law-case-bundle-manifest-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "builder": Path(__file__).name,
        "selection_policy": "round_robin_sorted_case_cause_v1",
        "source": {
            "path": str(source.relative_to(REPO_ROOT)),
            "sha256": source_sha,
        },
        "counts": {
            "case_bundles": len(bundles),
            "evidence_items": len(evidence_rows),
            "runtime_mappings": len(bundles),
        },
        "runtime_mapping": {
            bundle["runtime_case_id"]: {
                "case_bundle_id": bundle["case_bundle_id"],
                "original_case_id": bundle["original_case_id"],
                "content_sha256": bundle["content_sha256"],
            }
            for bundle in bundles
        },
        "law_corpus_manifest_sha256": law_manifest_sha,
        "files": {
            args.bundles_output.name: {
                "bytes": args.bundles_output.resolve().stat().st_size,
                "sha256": digest_file(args.bundles_output.resolve()),
            },
            args.evidence_output.name: {
                "bytes": args.evidence_output.resolve().stat().st_size,
                "sha256": digest_file(args.evidence_output.resolve()),
            },
        },
        "schema": {
            "path": str(CASE_SCHEMA.relative_to(REPO_ROOT)),
            "sha256": digest_file(CASE_SCHEMA),
        },
        "limits": [
            "reference_private fields are teacher/scorer only",
            "unresolved legal-basis fragments require term-level teacher review",
            "pilot CaseBundles do not establish learning gain or legal gold status",
        ],
    }
    args.manifest_output.resolve().write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "case_bundles": len(bundles),
                "evidence_items": len(evidence_rows),
                "runtime_mapping": manifest["runtime_mapping"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
