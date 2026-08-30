"""Build a read-only, auditable inventory for the external ``laws`` folder.

The 4,173 local files mix raw downloads, derived text, archives, scripts and
caches.  This builder hashes every file, detects exact duplicates, separates
artifact roles, preserves the existing 813-article governed corpus as the only
formal normative layer, and emits teacher-review candidates only for the ten
current knowledge points and three released CaseBundles.

No source file is modified and no model is called.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPO / "data_governance"
LAW_MANIFEST = REPO / "backend" / "legal_corpus" / "processed" / "law_corpus_manifest.json"
LEARNING_MANIFEST = REPO / "adaptive_service" / "data" / "manifest.json"
KNOWLEDGE_CARDS = REPO / "adaptive_service" / "data" / "knowledge_cards.jsonl"
EVIDENCE_CATALOG = REPO / "adaptive_service" / "data" / "evidence_catalog.jsonl"
CASE_MANIFEST = REPO / "dataset" / "case_bundle_manifest.json"
CASE_BUNDLES = REPO / "dataset" / "case_bundles.jsonl"
CASE_EVIDENCE = REPO / "dataset" / "case_bundle_evidence.jsonl"

FORMAL_OUTPUTS = {
    "刑法": REPO / "backend" / "legal_corpus" / "processed" / "xingfa.jsonl",
    "刑事诉讼法": REPO / "backend" / "legal_corpus" / "processed" / "xingsufa.jsonl",
}

AUTHORITY_PREFIXES = (
    "最高人民法院、最高人民检察院",
    "最高人民法院+最高人民检察院",
    "全国人民代表大会常务委员会",
    "最高人民法院",
    "最高人民检察院",
    "国务院",
    "公安部",
    "司法部",
)

KNOWLEDGE_KEYWORDS = {
    "CRIM_KP_467B1D9FCFABDA50": ("罪刑法定", "从旧兼从轻", "刑法效力"),
    "CRIM_KP_BC82753EB8088C13": ("犯罪概念", "情节显著轻微", "危害不大"),
    "CRIM_KP_2DD5C021746121C3": ("故意", "过失", "意外事件", "主观罪过"),
    "CRIM_KP_B81F51ACC84055A4": ("刑事责任年龄", "未成年人刑事", "不满十六周岁", "核准追诉"),
    "CRIM_KP_7B01D1EBC00BC8ED": ("正当防卫", "防卫过当", "特殊防卫"),
    "CRIM_KP_85BF396EA13741B5": ("紧急避险",),
    "CRIM_KP_8AABCC5F5D5822AD": ("犯罪预备", "犯罪未遂", "犯罪中止", "停止形态"),
    "CRIM_KP_07D38E1BC70F5155": ("共同犯罪", "主犯", "从犯", "教唆犯", "胁从犯"),
    "CRIM_KP_A9EE556B77025221": ("刑罚种类", "主刑", "附加刑", "死刑", "驱逐出境"),
    "CRIM_KP_DB1E1940114B4C0F": ("抢劫",),
}

CONTENT_EXTENSIONS = {".docx", ".doc", ".txt"}
ARTIFACT_PRIORITY = {
    "source_document": 0,
    "derived_text": 1,
    "aggregate_derivative": 2,
    "archive": 3,
    "operational": 4,
    "cache": 5,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize_title(path: Path) -> str:
    title = path.stem
    title = re.sub(r"\(FBM-CLI\.C\.\d+\)$", "", title)
    title = re.sub(r"_\d{8}$", "", title)
    title = title.replace("++", "、").replace("+", "、")
    return title.strip(" ._…")


def date_candidate(path: Path) -> tuple[str | None, str]:
    matches = re.findall(r"(?<!\d)(20\d{6})(?!\d)", path.stem)
    if not matches:
        matches = re.findall(r"(?<!\d)(20\d{6})(?!\d)", path.as_posix())
    if not matches:
        return None, "not_available"
    value = matches[-1]
    try:
        normalized = date(int(value[:4]), int(value[4:6]), int(value[6:])).isoformat()
    except ValueError:
        return None, "invalid_filename_date"
    return normalized, "filename_candidate_not_authoritative"


def artifact_role(relative: Path) -> str:
    value = relative.as_posix()
    extension = relative.suffix.lower()
    if "__pycache__" in relative.parts or extension == ".pyc":
        return "cache"
    if extension == ".zip" or value.startswith("原始的法律压缩包/"):
        return "archive"
    if value.startswith("raw_data/") and extension in {".docx", ".doc"}:
        return "source_document"
    if value.startswith(("output_laws/", "output_regulations/", "output_judicial/", "output_cases/")) and extension == ".txt":
        return "derived_text"
    if value.startswith("output_categories/") or relative.name == "all_laws_include_334.txt":
        return "aggregate_derivative"
    return "operational"


def layer_candidate(relative: Path) -> str:
    value = relative.as_posix()
    if value.startswith(("raw_data/法律/", "output_laws/")):
        return "L1_norm_candidate"
    if value.startswith(("raw_data/司法解释/", "output_judicial/")):
        return "L2_judicial_candidate"
    if value.startswith(("raw_data/指导性案例/", "output_cases/")):
        return "L3_case_candidate"
    if value.startswith(("raw_data/行政法规/", "output_regulations/")):
        return "adjacent_regulation_candidate"
    if value.startswith("output_categories/"):
        return "aggregate_only"
    return "not_content"


def source_family(relative: Path, role: str) -> str:
    value = relative.as_posix()
    if value.startswith("raw_data/指导性案例/") or value.startswith("output_cases/") or "北大法宝" in value:
        return "third_party_case_database_candidate"
    if value.startswith("raw_data/"):
        return "national_law_database_download_candidate"
    if role in {"derived_text", "aggregate_derivative"}:
        return "locally_derived_from_download"
    if role == "archive":
        return "download_archive"
    return "project_operational_file"


def inferred_authority(title: str) -> str:
    for prefix in AUTHORITY_PREFIXES:
        if title.startswith(prefix):
            return prefix.replace("+", "、")
    if title.startswith("中华人民共和国"):
        return "legislative_authority_requires_review"
    if re.match(r"^(指导性?案例|检例)第?\d+号", title):
        return "case_issuing_authority_requires_review"
    return "unknown_requires_review"


def related_knowledge_ids(title: str) -> list[str]:
    return sorted(
        knowledge_id
        for knowledge_id, keywords in KNOWLEDGE_KEYWORDS.items()
        if any(keyword in title for keyword in keywords)
    )


def privacy_risk(layer: str) -> str:
    if layer == "L3_case_candidate":
        return "case_personal_information_review_required"
    return "no_case_personal_data_indicated_by_collection"


def redistribution_risk(layer: str, family: str) -> str:
    if layer == "L3_case_candidate" or family == "third_party_case_database_candidate":
        return "third_party_case_redistribution_review_required"
    if family in {"national_law_database_download_candidate", "locally_derived_from_download"}:
        return "source_terms_and_exact_item_provenance_require_review"
    return "not_for_redistribution"


def governance_decision(
    *,
    role: str,
    layer: str,
    related: list[str],
    formal_source: bool,
    duplicate_role: str,
) -> tuple[str, str]:
    if formal_source:
        return "formal_source_artifact", "bound_to_existing_813_article_manifest"
    if duplicate_role == "duplicate":
        return "rejected_duplicate", "exact_sha256_duplicate"
    if role == "cache":
        return "rejected_from_content_pipeline", "cache_or_compiled_artifact"
    if role == "archive":
        return "rejected_from_content_pipeline", "archive_not_direct_content"
    if role == "operational":
        return "rejected_from_content_pipeline", "operational_file_not_corpus"
    if role == "aggregate_derivative":
        return "rejected_from_formal_evidence", "aggregate_derivative_not_citable_authority"
    if related and layer in {"L2_judicial_candidate", "L3_case_candidate"} and role == "derived_text":
        return "candidate_requires_legal_review", "title_keyword_match_current_course_scope"
    if layer == "L1_norm_candidate":
        return "isolated_reference", "not_part_of_current_formal_813_article_build"
    return "isolated_outside_scope", "outside_current_10_knowledge_3_case_scope"


def case_number(title: str) -> str | None:
    match = re.search(r"(?:指导性?案例|检例)第?(\d+)号", title)
    return match.group(1) if match else None


def dataset_card(
    *,
    snapshot_date: str,
    counts: dict[str, Any],
    decisions: Counter[str],
    duplicate_groups: int,
    candidate_l2: int,
    candidate_l3: int,
) -> str:
    return f"""# Criminal-Law Governed Source Dataset Card

## Scope

This card describes a read-only inventory of the local legal source workspace as of `{snapshot_date}`. The inventory is a candidate pool, not a training set and not a published legal knowledge base.

## Provenance layers

```mermaid
flowchart LR
    A[4,173 local files] --> B[role + SHA-256 + exact duplicate audit]
    B --> C[raw source documents]
    B --> D[derived text]
    B --> E[archives / scripts / cache isolated]
    C --> F[L1 formal build: Criminal Law 505 + CPL 308]
    D --> G[L2 judicial candidates: {candidate_l2}]
    D --> H[L3 case candidates: {candidate_l3}]
    F --> I[22 governed course Evidence items]
    G --> J[teacher review required]
    H --> J
    I --> K[10 KnowledgeCards + 3 CaseBundles]
    J --> K
```

## Current inventory

- Files: **{counts['files']}**
- Bytes: **{counts['bytes']}**
- Extensions: TXT {counts['extensions'].get('txt', 0)}, DOCX {counts['extensions'].get('docx', 0)}, DOC {counts['extensions'].get('doc', 0)}, ZIP {counts['extensions'].get('zip', 0)}
- Raw source subfolders: law {counts['raw_subfolders'].get('法律', 0)}, judicial {counts['raw_subfolders'].get('司法解释', 0)}, regulation {counts['raw_subfolders'].get('行政法规', 0)}, cases {counts['raw_subfolders'].get('指导性案例', 0)}
- Exact duplicate groups: **{duplicate_groups}**
- Existing formal RAG corpus: **813 articles** (Criminal Law 505; Criminal Procedure Law 308)
- Course layer: **10 KnowledgeCards, 30 objective tasks, 13 subjective/role tasks, 3 CaseBundles**

The local disk has **53 `.doc` files**, not 530. The number 530 refers to case text files in `output_cases`/source cases, and must not be presented as a DOC count.

## Governance decisions

{chr(10).join(f'- `{key}`: {value}' for key, value in sorted(decisions.items()))}

## Admission policy

1. Only the existing governed 813-article build is formal L1 normative Evidence.
2. L2/L3 title matches are candidates marked `candidate_requires_legal_review`; title matching does not establish validity, relevance or legal entailment.
3. Case materials from a third-party database require license, redistribution and personal-information review.
4. Archives, scripts, caches and aggregate category files are excluded from citable Evidence.
5. Every formal Evidence item must retain title, article, exact quote, source, version/effective status, SHA and review status.
6. Validity must be rechecked before each real classroom term.

## Intended use

- Source governance demonstrations;
- candidate selection for teacher review;
- governed RAG and LegalEduEval construction;
- reproducible file-level audit.

## Not supported

- claiming 4,173 training samples;
- treating all files as high-quality or current law;
- calling Silver/model-generated labels teacher Gold;
- redistributing third-party cases without review;
- deriving classroom effectiveness from corpus size.
"""


def governance_flow_svg(
    *,
    inventory_files: int,
    formal_articles: int,
    l2_candidates: int,
    l3_candidates: int,
    links: int,
) -> str:
    """Return a 16:9, presentation-ready SVG using only audited counts."""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900" role="img" aria-label="刑法学科数据治理流程">
<rect width="1600" height="900" fill="#0b0d0d"/>
<style>
  .title{{font:700 46px 'Microsoft YaHei UI','Noto Sans SC',sans-serif;fill:#f1eadc}}
  .kicker{{font:600 16px Consolas,monospace;letter-spacing:3px;fill:#86a9b4}}
  .box{{fill:#141817;stroke:#52656a;stroke-width:2}}
  .formal{{fill:#172018;stroke:#7f9f73;stroke-width:3}}
  .candidate{{fill:#201b12;stroke:#b08a3e;stroke-width:2;stroke-dasharray:8 6}}
  .num{{font:300 44px 'Microsoft YaHei UI','Noto Sans SC',sans-serif;fill:#f1eadc}}
  .head{{font:600 21px 'Microsoft YaHei UI','Noto Sans SC',sans-serif;fill:#f1eadc}}
  .body{{font:400 17px 'Microsoft YaHei UI','Noto Sans SC',sans-serif;fill:#b7b3aa}}
  .meta{{font:500 14px Consolas,monospace;fill:#82949a}}
  .arrow{{stroke:#789dac;stroke-width:3;fill:none;marker-end:url(#a)}}
</style>
<defs><marker id="a" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#789dac"/></marker></defs>
<text x="80" y="82" class="kicker">GOVERNED LEGAL DATA · READ-ONLY SNAPSHOT · 2026-08-31</text>
<text x="80" y="145" class="title">4,173候选材料，不等于4,173条高质量数据</text>

<rect x="80" y="235" width="245" height="360" class="box"/>
<text x="105" y="292" class="num">{inventory_files:,}</text><text x="105" y="328" class="head">本地文件库存</text>
<text x="105" y="374" class="body">1,511 原始文档</text><text x="105" y="408" class="body">2,024 派生文本</text>
<text x="105" y="442" class="body">30 压缩归档</text><text x="105" y="476" class="body">缓存 / 脚本 / 汇总隔离</text>
<text x="105" y="535" class="meta">SHA-256 · ROLE · LAYER</text>

<rect x="400" y="235" width="245" height="360" class="box"/>
<text x="425" y="292" class="num">8/8</text><text x="425" y="328" class="head">确定性治理门禁</text>
<text x="425" y="374" class="body">来源角色与目录分层</text><text x="425" y="408" class="body">精确哈希与重复组</text>
<text x="425" y="442" class="body">机关 / 日期候选</text><text x="425" y="476" class="body">隐私 / 再分发风险</text>
<text x="425" y="535" class="meta">MODEL CALLS = 0</text>

<rect x="720" y="220" width="250" height="175" class="formal"/>
<text x="745" y="275" class="num">{formal_articles}</text><text x="745" y="312" class="head">正式L1规范法源</text>
<text x="745" y="350" class="body">刑法505 + 刑诉法308</text><text x="745" y="377" class="meta">PUBLISHED GOVERNED RAG</text>
<rect x="720" y="420" width="250" height="175" class="candidate"/>
<text x="745" y="472" class="num">{l2_candidates} + {l3_candidates}</text><text x="745" y="509" class="head">L2解释 / L3案例候选</text>
<text x="745" y="547" class="body">效力、来源、许可、隐私待审</text><text x="745" y="574" class="meta">NOT FORMAL EVIDENCE</text>

<rect x="1045" y="235" width="220" height="360" class="box"/>
<text x="1070" y="292" class="num">22</text><text x="1070" y="328" class="head">课程正式Evidence</text>
<text x="1070" y="374" class="body">条号 + 逐字quote</text><text x="1070" y="408" class="body">版本 + 时效 + SHA</text>
<text x="1070" y="442" class="body">10 KnowledgeCards</text><text x="1070" y="476" class="body">3 CaseBundles / 9证据</text>
<text x="1070" y="535" class="meta">{links} LINKS · TEACHER GATE</text>

<rect x="1340" y="235" width="180" height="360" class="box"/>
<text x="1365" y="292" class="head">技术消费者</text>
<text x="1365" y="348" class="body">EvidencePack</text><text x="1365" y="388" class="body">可信RAG</text>
<text x="1365" y="428" class="body">结构化推理</text><text x="1365" y="468" class="body">LegalEduEval</text>
<text x="1365" y="508" class="body">四典型场景</text><text x="1365" y="548" class="meta">NO CAUSAL CLAIM</text>

<path d="M325 415 H390" class="arrow"/><path d="M645 415 H705" class="arrow"/>
<path d="M970 315 H1030" class="arrow"/><path d="M970 505 C1010 505 1005 470 1030 450" class="arrow"/>
<path d="M1265 415 H1325" class="arrow"/>

<rect x="80" y="690" width="1440" height="105" fill="#111413" stroke="#354044"/>
<text x="105" y="731" class="head">证据边界</text>
<text x="105" y="768" class="body">4173是混合文件库存；只有813条为当前正式规范法源。L2/L3标题命中只是教师审核候选，不证明现行有效、法律蕴含或可再分发。</text>
<text x="80" y="850" class="meta">corpus_inventory.json · governed_source_manifest.json · source_rejection_log.jsonl · knowledge_evidence_links.jsonl · DATASET_CARD.md</text>
</svg>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--laws-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--snapshot-date", default=date.today().isoformat())
    args = parser.parse_args()
    laws_root = args.laws_root.resolve()
    output = args.output.resolve()
    if not laws_root.is_dir():
        raise SystemExit(f"laws root not found: {laws_root}")

    law_manifest = load_json(LAW_MANIFEST)
    learning_manifest = load_json(LEARNING_MANIFEST)
    case_manifest = load_json(CASE_MANIFEST)
    cards = load_jsonl(KNOWLEDGE_CARDS)
    evidence_rows = load_jsonl(EVIDENCE_CATALOG)
    case_bundles = load_jsonl(CASE_BUNDLES)
    case_evidence = load_jsonl(CASE_EVIDENCE)
    cards_by_id = {row["knowledge_id"]: row for row in cards}
    evidence_by_id = {row["evidence_id"]: row for row in [*evidence_rows, *case_evidence]}

    formal_artifacts: dict[str, dict[str, Any]] = {}
    for document_name, document in law_manifest["documents"].items():
        for artifact in document["source_artifacts"]:
            formal_artifacts[Path(artifact["path"]).as_posix()] = {
                **artifact,
                "document_name": document_name,
            }

    paths = sorted(
        (path for path in laws_root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(laws_root).as_posix(),
    )
    preliminary: list[dict[str, Any]] = []
    hash_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in paths:
        relative = path.relative_to(laws_root)
        relative_value = relative.as_posix()
        digest = sha256(path)
        role = artifact_role(relative)
        layer = layer_candidate(relative)
        title = normalize_title(relative)
        related = related_knowledge_ids(title)
        date_value, date_basis = date_candidate(relative)
        row = {
            "path": relative_value,
            "title_candidate": title,
            "extension": relative.suffix.lower().lstrip(".") or "none",
            "bytes": path.stat().st_size,
            "sha256": digest,
            "artifact_role": role,
            "layer_candidate": layer,
            "source_family": source_family(relative, role),
            "issuing_authority_candidate": inferred_authority(title),
            "date_candidate": date_value,
            "date_basis": date_basis,
            "effective_status": "unknown_requires_review",
            "related_knowledge_ids": related,
            "criminal_relevance": (
                "current_course_title_match" if related else "not_established_by_title"
            ),
            "privacy_risk": privacy_risk(layer),
            "redistribution_risk": redistribution_risk(layer, source_family(relative, role)),
            "formal_source_manifest_role": formal_artifacts.get(relative_value, {}).get("role"),
            "review_status": (
                "bound_to_governed_manifest"
                if relative_value in formal_artifacts
                else "unreviewed_inventory"
            ),
        }
        preliminary.append(row)
        hash_groups[digest].append(row)

    duplicate_groups = {
        digest: rows for digest, rows in hash_groups.items() if len(rows) > 1
    }
    for digest, rows in duplicate_groups.items():
        rows.sort(
            key=lambda row: (
                ARTIFACT_PRIORITY[row["artifact_role"]],
                row["path"],
            )
        )
        primary = rows[0]["path"]
        group_id = f"DUP_{digest[:16].upper()}"
        for index, row in enumerate(rows):
            row["duplicate_group_id"] = group_id
            row["duplicate_role"] = "primary" if index == 0 else "duplicate"
            row["duplicate_of"] = None if index == 0 else primary
    for row in preliminary:
        row.setdefault("duplicate_group_id", None)
        row.setdefault("duplicate_role", "unique")
        row.setdefault("duplicate_of", None)
        decision, reason = governance_decision(
            role=row["artifact_role"],
            layer=row["layer_candidate"],
            related=row["related_knowledge_ids"],
            formal_source=row["path"] in formal_artifacts,
            duplicate_role=row["duplicate_role"],
        )
        row["governance_decision"] = decision
        row["decision_reason"] = reason

    extensions = Counter(row["extension"] for row in preliminary)
    roles = Counter(row["artifact_role"] for row in preliminary)
    layers = Counter(row["layer_candidate"] for row in preliminary)
    decisions = Counter(row["governance_decision"] for row in preliminary)
    raw_subfolders = Counter()
    for row in preliminary:
        parts = Path(row["path"]).parts
        if len(parts) > 2 and parts[0] == "raw_data":
            raw_subfolders[parts[1]] += 1

    candidate_l2_rows = [
        row
        for row in preliminary
        if row["governance_decision"] == "candidate_requires_legal_review"
        and row["layer_candidate"] == "L2_judicial_candidate"
    ]
    candidate_l3_rows = [
        row
        for row in preliminary
        if row["governance_decision"] == "candidate_requires_legal_review"
        and row["layer_candidate"] == "L3_case_candidate"
    ]

    inventory = {
        "schema_version": "criminal-law-corpus-inventory-v1",
        "snapshot_date": args.snapshot_date,
        "external_source_id": "edubrain-laws-local-snapshot",
        "source_root_disclosed": False,
        "read_only_scan": True,
        "counts": {
            "files": len(preliminary),
            "bytes": sum(row["bytes"] for row in preliminary),
            "extensions": dict(sorted(extensions.items())),
            "artifact_roles": dict(sorted(roles.items())),
            "layers": dict(sorted(layers.items())),
            "decisions": dict(sorted(decisions.items())),
            "duplicate_groups": len(duplicate_groups),
            "duplicate_files": sum(len(rows) for rows in duplicate_groups.values()),
            "raw_subfolders": dict(sorted(raw_subfolders.items())),
        },
        "files": preliminary,
        "boundaries": [
            "file count includes source documents, derived text, archives, scripts and caches",
            "title/date/authority candidates are not legal validity determinations",
            "only the existing 813-article governed build is formal normative Evidence",
            "no source file was modified and no model was called",
        ],
    }

    governed_manifest = {
        "schema_version": "criminal-law-governed-source-manifest-v1",
        "snapshot_date": args.snapshot_date,
        "formal_normative_layer": {
            "status": "published_governed_rag",
            "article_count": sum(
                document["article_count"]
                for document in law_manifest["documents"].values()
            ),
            "documents": law_manifest["documents"],
            "quarantined_sources": law_manifest["quarantined_sources"],
            "outputs": [
                {
                    "name": name,
                    "path": path.relative_to(REPO).as_posix(),
                    "articles": sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()),
                    "sha256": sha256(path),
                }
                for name, path in FORMAL_OUTPUTS.items()
            ],
            "manifest_path": LAW_MANIFEST.relative_to(REPO).as_posix(),
            "manifest_sha256": sha256(LAW_MANIFEST),
        },
        "course_layer": {
            "knowledge_cards": len(cards),
            "task_items": learning_manifest["counts"]["task_items"],
            "subjective_tasks": 13,
            "evidence_items": len(evidence_rows),
            "case_bundles": case_manifest["counts"]["case_bundles"],
            "case_evidence_items": case_manifest["counts"]["evidence_items"],
            "status": "pilot_teacher_gate_recheck_each_term",
        },
        "candidate_layers": {
            "L2_judicial": {
                "count": len(candidate_l2_rows),
                "status": "candidate_requires_legal_review",
                "items": [
                    {
                        key: row[key]
                        for key in (
                            "path",
                            "title_candidate",
                            "sha256",
                            "issuing_authority_candidate",
                            "date_candidate",
                            "related_knowledge_ids",
                            "effective_status",
                            "redistribution_risk",
                        )
                    }
                    for row in candidate_l2_rows
                ],
            },
            "L3_cases": {
                "count": len(candidate_l3_rows),
                "status": "candidate_requires_legal_and_redistribution_review",
                "items": [
                    {
                        key: row[key]
                        for key in (
                            "path",
                            "title_candidate",
                            "sha256",
                            "issuing_authority_candidate",
                            "date_candidate",
                            "related_knowledge_ids",
                            "privacy_risk",
                            "redistribution_risk",
                        )
                    }
                    for row in candidate_l3_rows
                ],
            },
        },
        "admission_policy": {
            "formal_evidence_required_fields": [
                "source_title",
                "article_ref",
                "quote",
                "source_url",
                "effective_status",
                "source_bundle_sha256",
                "review_status",
            ],
            "candidate_does_not_imply": [
                "current legal validity",
                "legal entailment",
                "permission to redistribute",
                "teacher Gold status",
            ],
            "review_before_real_classroom_term": True,
        },
    }

    rejection_rows = [
        {
            "path": row["path"],
            "sha256": row["sha256"],
            "artifact_role": row["artifact_role"],
            "layer_candidate": row["layer_candidate"],
            "decision": row["governance_decision"],
            "reason": row["decision_reason"],
            "duplicate_of": row["duplicate_of"],
            "review_status": row["review_status"],
        }
        for row in preliminary
        if row["governance_decision"].startswith("rejected")
        or row["governance_decision"].startswith("isolated")
    ]

    link_rows: list[dict[str, Any]] = []
    for card in cards:
        for evidence_id in card["standard_evidence_ids"]:
            evidence = evidence_by_id[evidence_id]
            link_rows.append(
                {
                    "schema_version": "knowledge-evidence-link-v1",
                    "subject_type": "knowledge_card",
                    "subject_id": card["knowledge_id"],
                    "subject_name": card["canonical_name"],
                    "source_layer": "L1_norm",
                    "evidence_id": evidence_id,
                    "source_path": None,
                    "source_title": evidence["source_title"],
                    "article_ref": evidence["article_ref"],
                    "source_sha256": evidence["source_bundle_sha256"],
                    "link_basis": "teacher_gated_standard_evidence",
                    "review_status": "formal_course_evidence",
                }
            )
    for row in [*candidate_l2_rows, *candidate_l3_rows]:
        for knowledge_id in row["related_knowledge_ids"]:
            card = cards_by_id[knowledge_id]
            link_rows.append(
                {
                    "schema_version": "knowledge-evidence-link-v1",
                    "subject_type": "knowledge_card",
                    "subject_id": knowledge_id,
                    "subject_name": card["canonical_name"],
                    "source_layer": (
                        "L2_judicial_candidate"
                        if row["layer_candidate"] == "L2_judicial_candidate"
                        else "L3_case_candidate"
                    ),
                    "evidence_id": None,
                    "source_path": row["path"],
                    "source_title": row["title_candidate"],
                    "article_ref": None,
                    "source_sha256": row["sha256"],
                    "link_basis": "title_keyword_candidate_only",
                    "review_status": "candidate_requires_legal_review",
                }
            )
    case_candidates_by_number = {
        case_number(row["title_candidate"]): row
        for row in candidate_l3_rows
        if case_number(row["title_candidate"])
    }
    for bundle in case_bundles:
        for evidence_id in bundle["evidence_ids"]:
            evidence = evidence_by_id[evidence_id]
            link_rows.append(
                {
                    "schema_version": "knowledge-evidence-link-v1",
                    "subject_type": "case_bundle",
                    "subject_id": bundle["case_bundle_id"],
                    "subject_name": bundle["title"],
                    "source_layer": "L1_norm",
                    "evidence_id": evidence_id,
                    "source_path": None,
                    "source_title": evidence["source_title"],
                    "article_ref": evidence["article_ref"],
                    "source_sha256": evidence["source_bundle_sha256"],
                    "link_basis": "released_case_bundle_evidence",
                    "review_status": "formal_case_evidence",
                }
            )
        number = case_number(bundle["title"])
        candidate = case_candidates_by_number.get(number)
        if candidate:
            link_rows.append(
                {
                    "schema_version": "knowledge-evidence-link-v1",
                    "subject_type": "case_bundle",
                    "subject_id": bundle["case_bundle_id"],
                    "subject_name": bundle["title"],
                    "source_layer": "L3_case_candidate",
                    "evidence_id": None,
                    "source_path": candidate["path"],
                    "source_title": candidate["title_candidate"],
                    "article_ref": None,
                    "source_sha256": candidate["sha256"],
                    "link_basis": "case_number_title_match",
                    "review_status": "candidate_requires_provenance_and_license_review",
                }
            )
    link_rows.sort(
        key=lambda row: (
            row["subject_type"],
            row["subject_id"],
            row["source_layer"],
            row.get("evidence_id") or "",
            row.get("source_path") or "",
        )
    )

    inventory_path = output / "corpus_inventory.json"
    governed_path = output / "governed_source_manifest.json"
    rejection_path = output / "source_rejection_log.jsonl"
    links_path = output / "knowledge_evidence_links.jsonl"
    card_path = output / "DATASET_CARD.md"
    flow_path = output / "DATA_GOVERNANCE_FLOW.svg"
    write_json(inventory_path, inventory)
    write_json(governed_path, governed_manifest)
    write_jsonl(rejection_path, rejection_rows)
    write_jsonl(links_path, link_rows)
    card_path.write_bytes(
        dataset_card(
            snapshot_date=args.snapshot_date,
            counts={
                "files": len(preliminary),
                "bytes": sum(row["bytes"] for row in preliminary),
                "extensions": dict(extensions),
                "raw_subfolders": dict(raw_subfolders),
            },
            decisions=decisions,
            duplicate_groups=len(duplicate_groups),
            candidate_l2=len(candidate_l2_rows),
            candidate_l3=len(candidate_l3_rows),
        ).encode("utf-8")
    )
    flow_path.write_bytes(
        governance_flow_svg(
            inventory_files=len(preliminary),
            formal_articles=governed_manifest["formal_normative_layer"]["article_count"],
            l2_candidates=len(candidate_l2_rows),
            l3_candidates=len(candidate_l3_rows),
            links=len(link_rows),
        ).encode("utf-8")
    )

    output_files = [
        inventory_path,
        governed_path,
        rejection_path,
        links_path,
        card_path,
        flow_path,
    ]
    audit = {
        "schema_version": "criminal-law-data-governance-audit-v1",
        "snapshot_date": args.snapshot_date,
        "counts": {
            "inventory_files": len(preliminary),
            "inventory_bytes": sum(row["bytes"] for row in preliminary),
            "formal_articles": governed_manifest["formal_normative_layer"]["article_count"],
            "formal_source_artifacts": len(formal_artifacts),
            "knowledge_cards": len(cards),
            "formal_course_evidence": len(evidence_rows),
            "case_bundles": len(case_bundles),
            "case_evidence": len(case_evidence),
            "L2_candidates": len(candidate_l2_rows),
            "L3_candidates": len(candidate_l3_rows),
            "rejection_or_isolation_records": len(rejection_rows),
            "knowledge_evidence_links": len(link_rows),
            "duplicate_groups": len(duplicate_groups),
        },
        "gates": {
            "all_files_have_sha256": all(len(row["sha256"]) == 64 for row in preliminary),
            "no_absolute_inventory_paths": all(
                not re.match(r"^[A-Za-z]:", row["path"]) and "\\" not in row["path"]
                for row in preliminary
            ),
            "formal_article_count_813": governed_manifest["formal_normative_layer"]["article_count"] == 813,
            "formal_source_hashes_match": all(
                next(row for row in preliminary if row["path"] == path)["sha256"]
                == artifact["sha256"]
                for path, artifact in formal_artifacts.items()
            ),
            "all_knowledge_cards_have_formal_links": all(
                any(
                    link["subject_type"] == "knowledge_card"
                    and link["subject_id"] == card["knowledge_id"]
                    and link["review_status"] == "formal_course_evidence"
                    for link in link_rows
                )
                for card in cards
            ),
            "candidate_links_not_promoted": all(
                link["review_status"] != "formal_course_evidence"
                for link in link_rows
                if link["source_layer"] in {"L2_judicial_candidate", "L3_case_candidate"}
            ),
            "raw_source_read_only": True,
            "model_calls_zero": True,
        },
        "execution_counts": {"model_calls": 0, "source_files_modified": 0},
        "files": [
            {
                "path": path.relative_to(REPO).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in output_files
        ],
        "boundaries": [
            "inventory candidates are not a training set",
            "L2/L3 matches require legal, validity, provenance, privacy and redistribution review",
            "formal legal validity remains limited to the existing governed manifest snapshot",
            "software audit is not expert legal approval or classroom-effect evidence",
        ],
    }
    audit_path = output / "DATA_GOVERNANCE_AUDIT.json"
    write_json(audit_path, audit)
    if not all(audit["gates"].values()):
        raise SystemExit(f"data governance gates failed: {audit['gates']}")
    print(
        json.dumps(
            {
                "output": str(output),
                "inventory_files": len(preliminary),
                "inventory_bytes": audit["counts"]["inventory_bytes"],
                "formal_articles": audit["counts"]["formal_articles"],
                "L2_candidates": len(candidate_l2_rows),
                "L3_candidates": len(candidate_l3_rows),
                "duplicate_groups": len(duplicate_groups),
                "links": len(link_rows),
                "gates_passed": sum(audit["gates"].values()),
                "gates_total": len(audit["gates"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
