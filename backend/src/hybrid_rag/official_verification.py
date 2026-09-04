"""Deterministic and incremental official-source metadata verification."""

from __future__ import annotations

import json
import re
import zipfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence
from xml.etree import ElementTree


SOURCE_DIRS = {
    "law": "法律",
    "regulation": "行政法规",
    "judicial_interpretation": "司法解释",
    "case": "指导性案例",
}
DATE_SUFFIX_RE = re.compile(r"[_-](\d{8})$")
DATE_RE = re.compile(r"(?P<year>19\d{2}|20\d{2})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日")
CASE_ID_RE = re.compile(r"FBM-CLI\.C\.\d+")
VERSION_SUFFIX_RE = re.compile(r"[（(][^（）()]*(?:年|版|修订|修正|文本)[^（）()]*[）)]")
BRACKET_NUMBER_RE = re.compile(
    r"(?:[\u4e00-\u9fff]{1,18})?[〔\[](?:19\d{2}|20\d{2})[〕\]][第\d一二三四五六七八九十百千万零〇两字第-]{1,18}号"
)
ORDER_NUMBER_RE = re.compile(
    r"(?:(?:中华人民共和国)?主席令|国务院令|中央军事委员会命令|[\u4e00-\u9fff]{2,16}(?:部|委员会)令)第[\d一二三四五六七八九十百千万零〇两]+号"
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def normalize_title(value: Any, *, remove_version: bool = False) -> str:
    text = str(value or "").strip()
    text = DATE_SUFFIX_RE.sub("", text)
    if remove_version:
        text = VERSION_SUFFIX_RE.sub("", text)
    return re.sub(r"[\s　《》:：·,，。()（）…\.\-_]+", "", text).lower()


def iso_date(value: str) -> str:
    match = re.fullmatch(r"(19\d{2}|20\d{2})(\d{2})(\d{2})", str(value or ""))
    if not match:
        return ""
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
    except ValueError:
        return ""


def chinese_date(value: str) -> str:
    match = DATE_RE.search(str(value or ""))
    if not match:
        return ""
    try:
        return date(int(match["year"]), int(match["month"]), int(match["day"])).isoformat()
    except ValueError:
        return ""


def _docx_text(path: Path, limit: int = 16000) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paragraphs = []
        for paragraph in root.iter(namespace + "p"):
            text = "".join(node.text or "" for node in paragraph.iter(namespace + "t")).strip()
            if text:
                paragraphs.append(text)
            if sum(len(item) for item in paragraphs) >= limit:
                break
        return "\n".join(paragraphs)[:limit]
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError):
        return ""


def local_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _docx_text(path)
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")[:16000]
    return ""


def evidence_identity(source_type: str, title: str) -> tuple[str, str, list[str], str, list[str]]:
    if source_type == "law":
        return "law", "法律", ["normative_rule"], "可作为规范依据使用。", []
    if source_type == "regulation":
        return (
            "administrative_regulation",
            "行政法规",
            ["normative_rule"],
            "可作为行政法规层级的规范依据，不得覆盖上位法。",
            ["不得覆盖法律及其他上位规范"],
        )
    if source_type == "judicial_interpretation":
        is_interpretation = "解释" in title or "批复" in title
        return (
            "judicial_interpretation" if is_interpretation else "judicial_normative_document",
            "司法解释" if is_interpretation else "司法规范性文件",
            ["judicial_application"],
            "用于说明司法适用口径，须结合适用范围和效力状态。",
            ["司法适用依据不得与上位规范冲突"],
        )
    guiding = bool(re.match(r"^(?:指导性?案例|检例)", title))
    return (
        "guiding_case" if guiding else "typical_case",
        "指导性案例" if guiding else "典型案例",
        ["case_reference"],
        "用于裁判参考和事实适用示例，不作为规范条文本身。",
        ["案例不是法律或司法解释", "命中检索子块后必须回填完整语义父段"],
    )


def infer_issuer(source_type: str, title: str, text: str) -> str:
    joined = f"{title}\n{text[:2500]}"
    issuers = []
    for name in (
        "全国人民代表大会常务委员会",
        "全国人民代表大会",
        "中华人民共和国国务院",
        "国务院",
        "最高人民法院",
        "最高人民检察院",
    ):
        if name in joined and name not in issuers:
            issuers.append(name)
    if source_type == "law" and not issuers:
        issuers.append("全国人民代表大会或其常务委员会")
    if source_type == "regulation" and not issuers:
        issuers.append("国务院或经国务院批准的发布机关")
    if source_type == "case" and not issuers:
        if title.startswith("检例") or title.startswith("指导性案例"):
            issuers.append("最高人民检察院")
        elif title.startswith("指导案例"):
            issuers.append("最高人民法院")
    return "、".join(issuers[:2])


def infer_document_number(text: str) -> str:
    header = text[:5000]
    match = BRACKET_NUMBER_RE.search(header) or ORDER_NUMBER_RE.search(header)
    return match.group(0).strip() if match else ""


def _keyword_date(text: str, keywords: str, *, last: bool = False) -> str:
    header = text[:7000]
    matches = []
    for match in DATE_RE.finditer(header):
        window = header[max(0, match.start() - 28) : min(len(header), match.end() + 38)]
        if re.search(keywords, window):
            parsed = chinese_date(match.group(0))
            if parsed:
                matches.append(parsed)
    if not matches:
        return ""
    return sorted(matches)[-1 if last else 0]


def _direct_dates(text: str, pattern: str) -> list[str]:
    values = []
    for match in re.finditer(pattern, text[:7000]):
        parsed = chinese_date(match.group(0))
        if parsed:
            values.append(parsed)
    return values


def infer_dates(text: str, filename_date: str) -> dict[str, str]:
    token = r"(?:19\d{2}|20\d{2})年\d{1,2}月\d{1,2}日"
    promulgated_values = _direct_dates(text, rf"{token}.{{0,20}}(?:公布|发布|印发)")
    effective_values = _direct_dates(text, rf"自\s*{token}\s*(?:起)?(?:施行|实施|生效)")
    revision_values = _direct_dates(text, rf"{token}.{{0,24}}(?:修订|修正|修改)")
    expiry_values = _direct_dates(text, rf"{token}.{{0,24}}(?:废止|失效|停止执行|不再适用)")
    promulgated = (promulgated_values[0] if promulgated_values else "") or filename_date
    effective = effective_values[0] if effective_values else ""
    if not effective and re.search(r"自发布之日起施行|自公布之日起施行", text[:7000]):
        effective = promulgated
    revision = sorted(revision_values)[-1] if revision_values else _keyword_date(text, r"修订|修正|修改", last=True)
    expiry = sorted(expiry_values)[-1] if expiry_values else _keyword_date(text, r"废止|失效|停止执行|不再适用", last=True)
    return {
        "promulgated_date": promulgated,
        "effective_date": effective,
        "revision_date": revision,
        "expiry_date": expiry,
    }


def index_raw_sources(source_root: Path) -> dict[str, list[Path]]:
    result: dict[str, list[Path]] = defaultdict(list)
    for source_type, folder in SOURCE_DIRS.items():
        directory = source_root / "laws" / "raw_data" / folder
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".doc", ".docx", ".txt"}:
                continue
            stem = DATE_SUFFIX_RE.sub("", path.stem)
            result[f"{source_type}:exact:{normalize_title(stem)}"].append(path)
            result[f"{source_type}:alias:{normalize_title(stem, remove_version=True)}"].append(path)
            case_id = CASE_ID_RE.search(path.name)
            if case_id:
                result[f"case:id:{case_id.group(0)}"].append(path)
    root_directory = source_root / "laws" / "raw_data"
    for path in root_directory.iterdir():
        if not path.is_file() or path.suffix.lower() not in {".doc", ".docx", ".txt"}:
            continue
        stem = DATE_SUFFIX_RE.sub("", path.stem)
        result[f"law:exact:{normalize_title(stem)}"].append(path)
        result[f"law:alias:{normalize_title(stem, remove_version=True)}"].append(path)
    return result


def match_raw(document: dict[str, Any], raw_index: dict[str, list[Path]]) -> list[Path]:
    source_type = str(document["source_type"])
    title = str(document["title"])
    if source_type == "case":
        case_id = str(document.get("case_id") or "")
        if case_id and raw_index.get(f"case:id:{case_id}"):
            return raw_index[f"case:id:{case_id}"]
    exact = raw_index.get(f"{source_type}:exact:{normalize_title(title)}", [])
    if exact:
        return exact
    return raw_index.get(f"{source_type}:alias:{normalize_title(title, remove_version=True)}", [])


def local_version(path: Path) -> str:
    match = DATE_SUFFIX_RE.search(path.stem)
    return iso_date(match.group(1)) if match else ""


def build_deterministic_record(document: dict[str, Any], matches: Sequence[Path], checked_at: str) -> dict[str, Any]:
    source_type = str(document["source_type"])
    title = str(document["title"])
    versions = sorted({local_version(path) for path in matches if local_version(path)})
    selected = sorted(matches, key=lambda path: (local_version(path), path.name))[-1] if matches else None
    text = local_text(selected) if selected else ""
    dates = infer_dates(text, local_version(selected) if selected else "")
    evidence_source_type, authority, usages, source_use, usage_notes = evidence_identity(source_type, title)
    conflicts = ["同名材料存在多个本地版本，当前选择日期最新文件作为元数据候选"] if len(versions) > 1 else []
    status = "verified_historical" if source_type == "case" and selected else "unresolved"
    verification_status = "partially_verified" if selected else "unresolved"
    methods = ["canonical_content_identity"]
    if selected:
        methods.extend(["official_archive_filename_match", "local_header_parse"])
    if len(versions) > 1:
        methods.append("local_version_chain_compare")
    return {
        "schema_version": "official-source-verification-v1",
        "document_id": document["document_id"],
        "source_type": source_type,
        "evidence_source_type": evidence_source_type,
        "authority_level": authority,
        "official_category": "",
        "allowed_usage": usages,
        "title": title,
        "document_number": infer_document_number(text),
        "issuing_authority": infer_issuer(source_type, title, text),
        **dates,
        "effective_status": status,
        "version": versions[-1] if versions else str(document.get("source_snapshot_id") or ""),
        "official_source_url": "",
        "verification_method": "+".join(methods),
        "verification_status": verification_status,
        "source_use": source_use,
        "usage_notes": usage_notes,
        "local_source_matches": len(matches),
        "local_version_candidates": versions,
        "metadata_conflicts": conflicts,
        "content_sha256": document["document_content_sha256"],
        "checked_at": checked_at,
    }


def merge_agent_record(base: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    if str(candidate.get("document_id") or "") != base["document_id"]:
        return base
    result = dict(base)
    for field in (
        "document_number",
        "issuing_authority",
        "promulgated_date",
        "effective_date",
        "revision_date",
        "expiry_date",
        "official_source_url",
    ):
        if candidate.get(field):
            result[field] = str(candidate[field])
    agent_status = str(candidate.get("effective_status") or "")
    agent_verification = str(candidate.get("verification_status") or "")
    if agent_status in {"verified_current", "verified_historical", "superseded", "repealed"}:
        result["effective_status"] = agent_status
    if agent_verification == "verified" or candidate.get("official_source_url"):
        result["verification_status"] = "verified"
    methods = [part for part in (result["verification_method"], str(candidate.get("verification_method") or "")) if part]
    result["verification_method"] = "+agent_luna:".join(methods)
    notes = str(candidate.get("notes") or "").strip()
    if notes:
        result["usage_notes"] = [*result["usage_notes"], notes[:500]]
        category_match = re.search(r"官方分类为([^；。]+)", notes)
        if category_match:
            official_category = category_match.group(1).strip()
            result["official_category"] = official_category
            if official_category == "宪法":
                result["authority_level"] = "宪法"
                result["source_use"] = "作为国家根本法层级的规范依据使用。"
            elif "法律解释" in official_category:
                result["authority_level"] = "全国人大常委会法律解释"
                result["source_use"] = "按官方法律解释身份作为规范依据使用。"
            elif "决定" in official_category:
                result["authority_level"] = "全国人大常委会决定"
                result["source_use"] = "按官方决定身份及其适用范围作为规范依据使用。"
    return result


def build_verification_records(
    canonical_documents: Sequence[dict[str, Any]],
    *,
    source_root: Path,
    agent_rows: Iterable[dict[str, Any]] = (),
    previous_rows: Iterable[dict[str, Any]] = (),
    checked_at: str | None = None,
) -> list[dict[str, Any]]:
    date_value = checked_at or date.today().isoformat()
    previous = {str(row.get("document_id")): row for row in previous_rows}
    agents: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in agent_rows:
        agents[str(row.get("document_id"))].append(dict(row))
    raw_index = index_raw_sources(source_root)
    records = []
    for document in canonical_documents:
        identifier = str(document["document_id"])
        cached = previous.get(identifier)
        if (
            cached
            and cached.get("content_sha256") == document.get("document_content_sha256")
            and int(cached.get("local_source_matches") or 0) > 0
        ):
            base = dict(cached)
            base["checked_at"] = date_value
        else:
            base = build_deterministic_record(document, match_raw(document, raw_index), date_value)
        for candidate in agents.get(identifier, []):
            base = merge_agent_record(base, candidate)
        records.append(base)
    if len(records) != len(canonical_documents) or len({row["document_id"] for row in records}) != len(records):
        raise ValueError("official verification coverage or ID uniqueness failed")
    return records


def summarize_records(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    conflicts = [row["document_id"] for row in records if row.get("metadata_conflicts")]
    return {
        "schema_version": "official-source-verification-summary-v1",
        "documents": len(records),
        "by_source_type": dict(Counter(row["source_type"] for row in records)),
        "by_evidence_source_type": dict(Counter(row["evidence_source_type"] for row in records)),
        "by_effective_status": dict(Counter(row["effective_status"] for row in records)),
        "by_verification_status": dict(Counter(row["verification_status"] for row in records)),
        "metadata_coverage": {
            field: sum(bool(row.get(field)) for row in records)
            for field in (
                "document_number",
                "issuing_authority",
                "promulgated_date",
                "effective_date",
                "revision_date",
                "expiry_date",
                "official_source_url",
            )
        },
        "local_source_matched": sum(int(row.get("local_source_matches") or 0) > 0 for row in records),
        "multiple_local_versions": len(conflicts),
        "manual_confirmation_candidates": conflicts,
        "unresolved_non_blocking": True,
        "hard_blockers": [],
        "checked_at": max((str(row.get("checked_at") or "") for row in records), default=""),
    }


__all__ = [
    "build_verification_records",
    "evidence_identity",
    "merge_agent_record",
    "normalize_title",
    "read_jsonl",
    "summarize_records",
    "write_jsonl",
]
