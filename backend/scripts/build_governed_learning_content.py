"""Build governed KnowledgeCard, TaskItem, and Evidence records.

The stage12/13 item bank is teacher-approved, but its legacy legal_basis points
to a quarantined third-party consolidation. This builder preserves item text
and teacher decisions while rebinding every citation to the governed official
law corpus and producing the three frozen product contracts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "adaptive_service" / "data"
DEFAULT_LAW_DIR = REPO_ROOT / "backend" / "legal_corpus" / "processed"
SCHEMA_DIR = REPO_ROOT / "schemas"


CURRICULUM = {
    "罪刑法定原则": {
        "chapter": "刑法总论·基本原则与效力",
        "summary": "法律明文规定为犯罪的，依照法律定罪处刑；并结合行为时法与裁判时法审查从旧兼从轻。",
        "law_refs": ["第三条", "第十二条"],
        "prerequisites": [],
        "common_errors": ["以社会危害性替代明文规定", "忽略行为时法与新法轻重比较"],
    },
    "犯罪概念与但书": {
        "chapter": "刑法总论·犯罪概念",
        "summary": "从危害行为、依法应受刑罚处罚及但书三个层面判断犯罪成立的外部边界。",
        "law_refs": ["第十三条"],
        "prerequisites": ["罪刑法定原则"],
        "common_errors": ["把任何违法行为等同犯罪", "把情节轻微与显著轻微危害不大混同"],
    },
    "故意、过失与意外事件": {
        "chapter": "刑法总论·主观罪过",
        "summary": "依据认识因素与意志因素区分故意、过失和不能预见或不能抗拒的意外事件。",
        "law_refs": ["第十四条", "第十五条", "第十六条"],
        "prerequisites": ["犯罪概念与但书"],
        "common_errors": ["只凭结果严重倒推故意", "混淆放任与轻信能够避免", "忽略过失犯罪须有法律规定"],
    },
    "刑事责任年龄": {
        "chapter": "刑法总论·责任能力",
        "summary": "按行为时年龄、罪名范围、情节与最高检核准条件判断未成年人刑事责任。",
        "law_refs": ["第十七条"],
        "prerequisites": ["犯罪概念与但书"],
        "common_errors": ["按审判时年龄判断", "忽略十二至十四周岁核准追诉条件"],
    },
    "正当防卫与防卫过当": {
        "chapter": "刑法总论·违法阻却事由",
        "summary": "围绕不法侵害、时间、对象、防卫意图、限度和特殊防卫逐项判断。",
        "law_refs": ["第二十条"],
        "prerequisites": ["犯罪概念与但书"],
        "common_errors": ["见到伤亡即认定防卫过当", "忽略侵害是否正在进行", "把事后报复当作防卫"],
    },
    "紧急避险": {
        "chapter": "刑法总论·违法阻却事由",
        "summary": "审查现实危险、不得已性、保护利益、损害限度及负有特定责任者的例外。",
        "law_refs": ["第二十一条"],
        "prerequisites": ["犯罪概念与但书"],
        "common_errors": ["有其他可行方式仍认定不得已", "忽略避免本人危险的特定责任例外"],
    },
    "犯罪预备、未遂与中止": {
        "chapter": "刑法总论·犯罪停止形态",
        "summary": "以是否着手、未得逞原因及放弃或防止结果的自动性、有效性区分停止形态。",
        "law_refs": ["第二十二条", "第二十三条", "第二十四条"],
        "prerequisites": ["故意、过失与意外事件"],
        "common_errors": ["把未得逞一律认定未遂", "混淆意志以外原因与自动放弃", "忽略中止的有效性"],
    },
    "共同犯罪与主从犯": {
        "chapter": "刑法总论·共同犯罪",
        "summary": "先判断共同故意，再依据组织、领导、主要、次要、辅助、胁迫或教唆作用认定责任。",
        "law_refs": ["第二十五条", "第二十六条", "第二十七条", "第二十八条", "第二十九条"],
        "prerequisites": ["故意、过失与意外事件"],
        "common_errors": ["把共同过失当共同犯罪", "按分赃多少机械判断主从犯", "忽略教唆未遂规则"],
    },
    "刑罚种类": {
        "chapter": "刑法总论·刑罚",
        "summary": "区分主刑、附加刑和对外国人适用的驱逐出境，并判断能否独立或附加适用。",
        "law_refs": ["第三十二条", "第三十三条", "第三十四条", "第三十五条"],
        "prerequisites": ["犯罪概念与但书"],
        "common_errors": ["把罚金列为主刑", "认为附加刑只能附加适用", "混淆驱逐出境与剥夺政治权利"],
    },
    "抢劫罪的基本构成": {
        "chapter": "刑法分论·侵犯财产罪",
        "summary": "结合非法占有目的、暴力胁迫等手段、当场性和取财行为判断抢劫罪基本构成。",
        "law_refs": ["第二百六十三条"],
        "prerequisites": ["故意、过失与意外事件", "犯罪概念与但书"],
        "common_errors": ["因财物价值低否定抢劫", "混淆当场暴力胁迫与敲诈勒索", "忽略非法占有目的"],
    },
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def stable_hash(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(body.encode("utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def normalize_quote(value: Any) -> str:
    return re.sub(r"[\s　]+", "", str(value or "")).replace("“", "").replace("”", "")


def evidence_id(record: dict[str, Any]) -> str:
    seed = f"{record['document_id']}|{record['source_bundle_sha256']}"
    return f"EVID_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:20].upper()}"


def build_evidence(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "evidence-pack-item-v1",
        "evidence_id": evidence_id(record),
        "source_type": "法律条文",
        "document_id": record["document_id"],
        "title": f"{record['source_title']}{record['article_ref']}",
        "source_title": record["source_title"],
        "article_ref": record["article_ref"],
        "quote": record["content"],
        "authority_level": "法律",
        "effective_from": record.get("version_as_of"),
        "effective_to": None,
        "effective_status": record.get("effective_status"),
        "source_url": record.get("source_url"),
        "source_url_scope": record.get("source_url_scope"),
        "source_snapshot_id": record.get("source_snapshot_id"),
        "source_bundle_sha256": record.get("source_bundle_sha256"),
        "risk_flags": [
            "official_item_url_not_preserved",
            "recheck_validity_before_classroom_term",
        ],
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    body = "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows
    )
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(body, encoding="utf-8", newline="\n")
    temp.replace(path)


def public_task_projection(task: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in task.items()
        if key not in {"answer_private", "rationale_private", "misconceptions_private"}
    }


def find_absolute_paths(value: Any, path: str = "") -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            hits.extend(find_absolute_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(find_absolute_paths(child, f"{path}[{index}]"))
    elif isinstance(value, str) and re.match(r"^[A-Za-z]:[\\/]", value):
        hits.append((path, value))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--law-dir", type=Path, default=DEFAULT_LAW_DIR)
    args = parser.parse_args()
    data_dir = args.data_dir.resolve()
    law_dir = args.law_dir.resolve()

    approved_path = data_dir / "approved_items.jsonl"
    q_path = data_dir / "q_matrix.jsonl"
    node_path = data_dir / "knowledge_nodes.jsonl"
    law_path = law_dir / "xingfa.jsonl"
    law_manifest_path = law_dir / "law_corpus_manifest.json"
    approved = read_jsonl(approved_path)
    q_edges = read_jsonl(q_path)
    nodes = read_jsonl(node_path)
    laws = read_jsonl(law_path)
    law_manifest = json.loads(law_manifest_path.read_text(encoding="utf-8"))
    law_by_ref = {row["article_ref"]: row for row in laws}
    node_by_name = {row["canonical_name"]: row for row in nodes}
    if len(approved) != 30 or len(q_edges) != 30 or len(nodes) != 10:
        raise ValueError("expected 30 approved items, 30 Q edges, and 10 knowledge nodes")
    if set(node_by_name) != set(CURRICULUM):
        raise ValueError("curriculum names do not match approved knowledge nodes")

    required_refs = {
        ref for spec in CURRICULUM.values() for ref in spec["law_refs"]
    }
    for row in approved:
        required_refs.update(
            citation["article"] for citation in row["item"].get("legal_basis_citations", [])
        )
    missing = sorted(required_refs - set(law_by_ref))
    if missing:
        raise ValueError(f"governed law corpus is missing article refs: {missing}")
    evidence_by_ref = {ref: build_evidence(law_by_ref[ref]) for ref in sorted(required_refs)}

    cards: list[dict[str, Any]] = []
    id_by_name = {name: node_by_name[name]["knowledge_id"] for name in CURRICULUM}
    for name, spec in CURRICULUM.items():
        node = node_by_name[name]
        card = {
            "schema_version": "criminal-law-knowledge-card-v1",
            "knowledge_id": node["knowledge_id"],
            "canonical_name": name,
            "domain": "刑法",
            "chapter": spec["chapter"],
            "knowledge_type": "course_core",
            "learning_objective": node["learning_objective"],
            "summary": spec["summary"],
            "law_article_refs": spec["law_refs"],
            "standard_evidence_ids": [evidence_by_ref[ref]["evidence_id"] for ref in spec["law_refs"]],
            "prerequisite_ids": [id_by_name[value] for value in spec["prerequisites"]],
            "common_errors": spec["common_errors"],
            "theory_scope": "本科刑法课程基础规范口径；争议观点须另行标识，不以本卡替代教师裁量。",
            "review_status": "pilot_teacher_approved",
            "reviewer_role": "teacher_gate",
            "version": "2026-08-27",
            "law_corpus_snapshot": law_manifest["download_snapshot_date"],
        }
        card["content_sha256"] = stable_hash(card)
        cards.append(card)

    governed_approved: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    q_by_item = {row["item_id"]: row for row in q_edges}
    for row in approved:
        item = row["item"]
        task_id = row["candidate_id"]
        q_edge = q_by_item.get(task_id)
        if q_edge is None or q_edge["knowledge_id"] != item["knowledge_id"]:
            raise ValueError(f"bad Q edge for {task_id}")
        governed_basis = []
        quote_by_evidence: dict[str, str] = {}
        for citation in item.get("legal_basis_citations", []):
            ref = citation["article"]
            law = law_by_ref[ref]
            quote = str(citation.get("quote") or "").strip()
            if normalize_quote(quote) not in normalize_quote(law["content"]):
                raise ValueError(f"citation quote mismatch: {task_id} {ref}")
            evidence = evidence_by_ref[ref]
            quote_by_evidence[evidence["evidence_id"]] = quote
            governed_basis.append(
                {
                    "evidence_id": evidence["evidence_id"],
                    "article": ref,
                    "law_name": law["source_title"],
                    "quote": quote,
                    "authority_level": "法律",
                    "effective_status": law["effective_status"],
                    "version_as_of": law["version_as_of"],
                    "source_url": law["source_url"],
                    "source_snapshot_id": law["source_snapshot_id"],
                    "source_bundle_sha256": law["source_bundle_sha256"],
                    "risk_flags": evidence["risk_flags"],
                }
            )
        if not governed_basis:
            raise ValueError(f"task has no governed legal basis: {task_id}")

        governed = dict(row)
        governed["schema_version"] = "law-parallel-diagnostic-item-v2.0"
        governed["legal_basis"] = governed_basis
        governed["governance"] = {
            "law_corpus_manifest_sha256": sha256_file(law_manifest_path),
            "law_corpus_snapshot": law_manifest["download_snapshot_date"],
            "legacy_third_party_provenance_removed": True,
        }
        governed_approved.append(governed)

        dimension = str(item.get("cognitive_dimension") or "")
        target_abilities = (
            ["fact_identification", "subsumption"]
            if dimension == "应用"
            else ["rule_retrieval", "fact_identification"]
        )
        task = {
            "schema_version": "criminal-law-task-item-v1",
            "task_id": task_id,
            "domain": "刑法",
            "status": "pilot_teacher_approved",
            "task_type": "diagnostic_item",
            "phase_eligibility": ["prestudy", "review"],
            "knowledge_ids": [item["knowledge_id"]],
            "knowledge_name": item["knowledge_name"],
            "target_abilities": target_abilities,
            "difficulty": int(item.get("difficulty") or 2),
            "cognitive_dimension": dimension,
            "stem": item["stem"],
            "options": item["options"],
            "answer_private": item["answer"],
            "rationale_private": item.get("rationale") or "",
            "misconceptions_private": item.get("misconceptions") or [],
            "standard_evidence_ids": list(quote_by_evidence),
            "standard_evidence_quotes": quote_by_evidence,
            "scoring_rule": {"type": "exact_option_set", "max_score": 1.0},
            "review": row.get("teacher_decision") or {},
            "source_item_sha256": item.get("source_hash") or stable_hash(item),
        }
        task["content_sha256"] = stable_hash(public_task_projection(task))
        tasks.append(task)

    if len({row["task_id"] for row in tasks}) != 30:
        raise ValueError("task IDs are not unique")
    generated = {
        "approved_items": governed_approved,
        "knowledge_cards": cards,
        "task_items": tasks,
        "evidence_catalog": list(evidence_by_ref.values()),
    }
    absolute_paths = find_absolute_paths(generated)
    if absolute_paths:
        raise ValueError(
            "generated product content contains an absolute Windows path: "
            f"{absolute_paths[0][0]}"
        )

    evidence_rows = list(evidence_by_ref.values())
    from jsonschema import Draft202012Validator

    card_schema = json.loads((SCHEMA_DIR / "knowledge-card-v1.schema.json").read_text(encoding="utf-8"))
    task_schema = json.loads((SCHEMA_DIR / "task-item-v1.schema.json").read_text(encoding="utf-8"))
    evidence_pack_schema = json.loads((SCHEMA_DIR / "evidence-pack-v1.schema.json").read_text(encoding="utf-8"))
    evidence_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **evidence_pack_schema["$defs"]["evidenceItem"],
    }
    for schema in (card_schema, task_schema, evidence_pack_schema, evidence_schema):
        Draft202012Validator.check_schema(schema)
    for row in cards:
        Draft202012Validator(card_schema).validate(row)
    for row in tasks:
        Draft202012Validator(task_schema).validate(row)
    for row in evidence_rows:
        Draft202012Validator(evidence_schema).validate(row)
    write_jsonl(approved_path, governed_approved)
    write_jsonl(data_dir / "knowledge_cards.jsonl", cards)
    write_jsonl(data_dir / "task_items.jsonl", tasks)
    write_jsonl(data_dir / "evidence_catalog.jsonl", evidence_rows)

    files = {}
    for filename in (
        "approved_items.jsonl",
        "knowledge_cards.jsonl",
        "task_items.jsonl",
        "evidence_catalog.jsonl",
        "q_matrix.jsonl",
    ):
        path = data_dir / filename
        files[filename] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    manifest = {
        "schema_version": "criminal-law-learning-content-manifest-v3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "builder": Path(__file__).name,
        "counts": {
            "knowledge_cards": len(cards),
            "task_items": len(tasks),
            "evidence_items": len(evidence_rows),
            "q_edges": len(q_edges),
        },
        "law_corpus": {
            "manifest_sha256": sha256_file(law_manifest_path),
            "download_snapshot_date": law_manifest["download_snapshot_date"],
            "criminal_law_version": law_manifest["documents"]["xingfa"]["version_as_of"],
        },
        "answer_policy": "private fields never returned by recommendation or knowledge APIs",
        "limits": [
            "pilot items require empirical item analysis before high-stakes use",
            "teacher review is required before every real classroom term",
        ],
        "files": files,
        "schemas": {
            filename: {"sha256": sha256_file(SCHEMA_DIR / filename)}
            for filename in (
                "knowledge-card-v1.schema.json",
                "task-item-v1.schema.json",
                "evidence-pack-v1.schema.json",
            )
        },
    }
    (data_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
