from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from jsonschema import Draft202012Validator


BUILDER_VERSION = "hybrid-rag-corpus-builder-v1"
SOURCE_DIRS = {
    "law": "output_laws",
    "regulation": "output_regulations",
    "judicial_interpretation": "output_judicial",
    "case": "output_cases",
}
AUTHORITY_LABELS = {
    "law": "法律候选",
    "regulation": "行政法规候选",
    "judicial_interpretation": "司法解释或司法文件候选",
    "case": "案例候选",
}
SOURCE_PRECEDENCE = {name: index for index, name in enumerate(SOURCE_DIRS)}
PRIVATE_FIELD_NAMES = {
    "answer",
    "answer_private",
    "rationale_private",
    "misconceptions_private",
    "rubric_private",
    "expected_points_private",
    "scoring_rule",
    "teacher_notes",
}
CHINESE_NUMBER = "零〇一二三四五六七八九十百千万亿两0-9"
ARTICLE_REF = rf"第[{CHINESE_NUMBER}]{{1,20}}条(?:之[{CHINESE_NUMBER}]{{1,10}})?"
ARTICLE_RE = re.compile(
    rf"(?m)^\s*《(?P<title>[^》\r\n]{{1,120}})》(?P<article>{ARTICLE_REF})(?:规定)?[，,:：]?"
)
CASE_SECTION_RE = re.compile(r"(?m)^\s*【(?P<header>[^】\r\n]{1,60})】\s*$")
CASE_ID_RE = re.compile(r"\((?P<id>(?:FBM-)?CLI\.C\.[^)]+)\)", re.IGNORECASE)
BOOK_HEADING_RE = re.compile(rf"^(?:第[{CHINESE_NUMBER}]{{1,12}}[章节编篇]|【[^】]+】)")
SCHEMAS_ROOT = Path(__file__).resolve().parents[3] / "schemas"


@dataclass(frozen=True)
class BuildConfig:
    laws_root: Path
    textbook_root: Path
    task_items_path: Path
    subjective_tasks_path: Path
    jecqa_single_path: Path
    jecqa_multiple_path: Path
    output_dir: Path
    snapshot_date: str
    inventory_path: Path | None = None
    public_audit_json: Path | None = None
    public_audit_md: Path | None = None
    max_chunk_chars: int = 1400
    target_chunk_chars: int = 1000
    overlap_chars: int = 120


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _with_hash(row: dict[str, Any], field: str = "content_sha256") -> dict[str, Any]:
    payload = dict(row)
    payload[field] = _sha256_text(_canonical_json(row))
    return payload


def _stable_id(prefix: str, *parts: str, length: int = 24) -> str:
    digest = _sha256_text("\x1f".join(parts))[:length].upper()
    return f"{prefix}_{digest}"


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\ufeff", "").replace("\u00a0", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t\u3000]+", " ", line).strip() for line in text.split("\n")]
    compact: list[str] = []
    blank = False
    for line in lines:
        if line:
            compact.append(line)
            blank = False
        elif compact and not blank:
            compact.append("")
            blank = True
    return "\n".join(compact).strip()


def _safe_relative(path: Path, root: Path, label: str) -> str:
    return f"{label}/{path.resolve().relative_to(root.resolve()).as_posix()}"


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    return count


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            yield value


def _choose_boundary(text: str, start: int, proposed: int, maximum: int) -> int:
    upper = min(len(text), maximum)
    if upper >= len(text):
        return len(text)
    lower = max(start + 1, proposed - 220)
    for token in ("\n\n", "\n", "。", "；", "！", "？"):
        index = text.rfind(token, lower, upper)
        if index >= lower:
            return index + len(token)
    return upper


def split_long_text(
    text: str,
    *,
    target_chars: int,
    max_chars: int,
    overlap_chars: int,
) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        proposed = min(len(normalized), start + target_chars)
        end = _choose_boundary(normalized, start, proposed, start + max_chars)
        if end <= start:
            end = min(len(normalized), start + max_chars)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        next_start = max(start + 1, end - overlap_chars)
        start = next_start
    return chunks


def _chunk_row(
    *,
    document: dict[str, Any],
    content: str,
    section_type: str,
    section_title: str,
    article_ref: str = "",
    section_index: int = 1,
    part_index: int = 1,
    part_total: int = 1,
    parent_id: str = "",
    parent_content_sha256: str = "",
) -> dict[str, Any]:
    embed_parts = [
        f"来源类型：{document['source_type']}",
        f"标题：{document['title']}",
    ]
    if article_ref:
        embed_parts.append(f"条号：{article_ref}")
    if section_title:
        embed_parts.append(f"段落：{section_title}")
    embed_parts.append(content)
    chunk_id = _stable_id(
        "RAGC",
        document["document_id"],
        section_type,
        article_ref,
        section_title,
        str(section_index),
        str(part_index),
        _sha256_text(content),
    )
    row = {
        "schema_version": "hybrid-rag-chunk-v1",
        "chunk_id": chunk_id,
        "document_id": document["document_id"],
        "parent_id": parent_id,
        "retrieval_unit": "child" if parent_id else "chunk",
        "retrieval_tier": "legal_authority",
        "source_type": document["source_type"],
        "authority_level": document["authority_level"],
        "title": document["title"],
        "article_ref": article_ref,
        "case_id": document.get("case_id", ""),
        "issuing_authority": document.get("issuing_authority", ""),
        "promulgated_date": document.get("promulgated_date", ""),
        "effective_date": document.get("effective_date", ""),
        "effective_status": document["effective_status"],
        "governance_status": document["governance_status"],
        "section_type": section_type,
        "section_title": section_title,
        "section_index": section_index,
        "part_index": part_index,
        "part_total": part_total,
        "content": content,
        "embed_text": "\n".join(embed_parts),
        "source_path": document["source_path"],
        "source_snapshot_id": document["source_snapshot_id"],
        "source_file_sha256": document["source_file_sha256"],
        "document_content_sha256": document["document_content_sha256"],
        "parent_content_sha256": parent_content_sha256,
        "risk_flags": list(document["risk_flags"]),
    }
    return _with_hash(row)


def _case_section_type(header: str) -> str:
    value = header.replace(" ", "")
    if "摘要" in value:
        return "summary"
    if "案情" in value or "事实" in value:
        return "facts"
    if "裁判要点" in value or "规则" in value or "要旨" in value:
        return "rule_reasoning"
    if "理由" in value:
        return "reasoning"
    if "结果" in value or "结论" in value:
        return "holding"
    if "法条" in value or "依据" in value:
        return "cited_authorities"
    if "关键词" in value:
        return "keywords"
    return "case_section"


def _case_parent_row(
    *,
    document: dict[str, Any],
    section_type: str,
    section_title: str,
    content: str,
    section_index: int,
) -> dict[str, Any]:
    parent_id = _stable_id(
        "RAGP",
        document["document_id"],
        section_type,
        section_title,
        str(section_index),
        _sha256_text(content),
    )
    row = {
        "schema_version": "hybrid-rag-case-parent-v1",
        "parent_id": parent_id,
        "document_id": document["document_id"],
        "retrieval_tier": "case_parent_context",
        "source_type": "case",
        "authority_level": document["authority_level"],
        "title": document["title"],
        "case_id": document.get("case_id", ""),
        "section_index": section_index,
        "section_type": section_type,
        "section_title": section_title,
        "content": content,
        "source_path": document["source_path"],
        "source_snapshot_id": document["source_snapshot_id"],
        "source_file_sha256": document["source_file_sha256"],
        "document_content_sha256": document["document_content_sha256"],
        "governance_status": document["governance_status"],
        "risk_flags": list(document["risk_flags"]),
    }
    return _with_hash(row)


def split_legal_document_with_parents(
    document: dict[str, Any],
    text: str,
    *,
    target_chars: int,
    max_chars: int,
    overlap_chars: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    chunks: list[dict[str, Any]] = []
    parents: list[dict[str, Any]] = []
    if document["source_type"] != "case":
        return (
            split_legal_document(
                document,
                text,
                target_chars=target_chars,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
            ),
            parents,
        )
    matches = list(CASE_SECTION_RE.finditer(text))
    sections: list[tuple[str, str, str]] = []
    if matches:
        preamble = normalize_text(text[: matches[0].start()])
        if preamble:
            sections.append(("summary", "案例标题与前言", preamble))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            header = normalize_text(match.group("header"))
            body = normalize_text(text[match.end() : end])
            if body:
                sections.append((_case_section_type(header), header, body))
    else:
        sections.append(("case_text", "案例全文候选", text))
    for section_index, (section_type, section_title, body) in enumerate(sections, 1):
        parent = _case_parent_row(
            document=document,
            section_type=section_type,
            section_title=section_title,
            content=body,
            section_index=section_index,
        )
        parents.append(parent)
        parts = split_long_text(
            body,
            target_chars=target_chars,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )
        for index, part in enumerate(parts, 1):
            chunks.append(
                _chunk_row(
                    document=document,
                    content=part,
                    section_type=section_type,
                    section_title=section_title,
                    section_index=section_index,
                    part_index=index,
                    part_total=len(parts),
                    parent_id=parent["parent_id"],
                    parent_content_sha256=parent["content_sha256"],
                )
            )
    return chunks, parents


def split_legal_document(
    document: dict[str, Any],
    text: str,
    *,
    target_chars: int,
    max_chars: int,
    overlap_chars: int,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    if document["source_type"] == "case":
        case_chunks, _ = split_legal_document_with_parents(
            document,
            text,
            target_chars=target_chars,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )
        return case_chunks

    matches = list(ARTICLE_RE.finditer(text))
    sections: list[tuple[str, str, str]] = []
    if matches:
        preamble = normalize_text(text[: matches[0].start()])
        if preamble:
            sections.append(("preamble", "文首说明", preamble))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            article_ref = normalize_text(match.group("article"))
            body = normalize_text(text[match.start() : end])
            if body:
                sections.append(("article", article_ref, body))
    else:
        sections.append(("unstructured_provision", "未识别条款结构", text))
    for section_index, (section_type, section_title, body) in enumerate(sections, 1):
        article_ref = section_title if section_type == "article" else ""
        parts = split_long_text(
            body,
            target_chars=target_chars,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )
        for index, part in enumerate(parts, 1):
            chunks.append(
                _chunk_row(
                    document=document,
                    content=part,
                    section_type=section_type,
                    section_title=section_title,
                    article_ref=article_ref,
                    section_index=section_index,
                    part_index=index,
                    part_total=len(parts),
                )
            )
    return chunks


def _load_source_candidates(config: BuildConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    candidates: list[dict[str, Any]] = []
    source_roots: dict[str, str] = {}
    inventory_by_path: dict[str, dict[str, Any]] = {}
    if config.inventory_path and config.inventory_path.is_file():
        payload = json.loads(config.inventory_path.read_text(encoding="utf-8"))
        inventory_by_path = {
            str(row["path"]): row
            for row in payload.get("files") or []
            if isinstance(row, dict) and row.get("path")
        }
    for source_type, directory_name in SOURCE_DIRS.items():
        directory = config.laws_root / directory_name
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        source_roots[source_type] = f"laws/{directory_name}"
        for path in sorted(directory.glob("*.txt"), key=lambda value: value.name):
            raw = path.read_text(encoding="utf-8", errors="strict")
            text = normalize_text(raw)
            if not text:
                continue
            case_match = CASE_ID_RE.search(path.stem)
            inventory_relative = path.resolve().relative_to(config.laws_root.resolve()).as_posix()
            inventory = inventory_by_path.get(inventory_relative, {})
            source_sha = _sha256_file(path)
            if inventory and str(inventory.get("sha256") or "") != source_sha:
                raise ValueError(f"governance inventory hash drift: {inventory_relative}")
            candidates.append(
                {
                    "source_type": source_type,
                    "title": normalize_text(path.stem),
                    "case_id": case_match.group("id") if case_match else "",
                    "path": path,
                    "source_path": _safe_relative(path, config.laws_root, "laws"),
                    "source_file_sha256": source_sha,
                    "document_content_sha256": _sha256_text(text),
                    "char_count": len(text),
                    "text": text,
                    "inventory_relative": inventory_relative,
                    "inventory": inventory,
                }
            )
    candidates.sort(key=lambda row: (SOURCE_PRECEDENCE[row["source_type"]], row["source_path"]))
    by_content: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_content[candidate["document_content_sha256"]].append(candidate)

    source_manifest: list[dict[str, Any]] = []
    canonical_documents: list[dict[str, Any]] = []
    canonical_by_hash: dict[str, dict[str, Any]] = {}
    for content_hash, rows in sorted(by_content.items()):
        primary = rows[0]
        inventory = primary.get("inventory") or {}
        document_id = _stable_id("RAGD", primary["source_type"], content_hash)
        risk_flags = ["candidate_not_formal_authority", "effective_status_requires_review"]
        for field in ("privacy_risk", "redistribution_risk", "review_status"):
            value = str(inventory.get(field) or "").strip()
            if value:
                risk_flags.append(value)
        if primary["source_type"] == "case":
            risk_flags.append("case_relevance_not_legal_entailment")
        document = {
            "schema_version": "hybrid-rag-document-v1",
            "document_id": document_id,
            "source_type": primary["source_type"],
            "authority_level": AUTHORITY_LABELS[primary["source_type"]],
            "title": primary["title"],
            "case_id": primary["case_id"],
            "issuing_authority": str(inventory.get("issuing_authority_candidate") or "unknown_requires_review"),
            "promulgated_date": str(inventory.get("date_candidate") or ""),
            "effective_date": "",
            "effective_status": str(inventory.get("effective_status") or "unknown_requires_review"),
            "governance_status": str(inventory.get("governance_decision") or "candidate_requires_legal_review"),
            "inventory_metadata_present": bool(inventory),
            "layer_candidate": str(inventory.get("layer_candidate") or ""),
            "source_family": str(inventory.get("source_family") or ""),
            "criminal_relevance": str(inventory.get("criminal_relevance") or ""),
            "privacy_risk": str(inventory.get("privacy_risk") or ""),
            "redistribution_risk": str(inventory.get("redistribution_risk") or ""),
            "inventory_review_status": str(inventory.get("review_status") or ""),
            "source_path": primary["source_path"],
            "source_snapshot_id": f"edubrain-laws-{config.snapshot_date}",
            "source_file_sha256": primary["source_file_sha256"],
            "document_content_sha256": content_hash,
            "char_count": primary["char_count"],
            "duplicate_source_count": len(rows) - 1,
            "aliases": [
                {"title": row["title"], "source_path": row["source_path"], "source_type": row["source_type"]}
                for row in rows[1:]
            ],
            "risk_flags": risk_flags,
        }
        canonical_documents.append(document)
        canonical_by_hash[content_hash] = {**document, "text": primary["text"]}
        for index, row in enumerate(rows):
            source_manifest.append(
                {
                    "schema_version": "hybrid-rag-source-manifest-v1",
                    "source_id": _stable_id("RAGS", row["source_path"], row["source_file_sha256"]),
                    "document_id": document_id,
                    "source_type": row["source_type"],
                    "title": row["title"],
                    "source_path": row["source_path"],
                    "source_file_sha256": row["source_file_sha256"],
                    "document_content_sha256": content_hash,
                    "char_count": row["char_count"],
                    "is_canonical": index == 0,
                    "inventory_metadata_present": bool(row.get("inventory")),
                    "inventory_governance_decision": str(
                        (row.get("inventory") or {}).get("governance_decision") or ""
                    ),
                    "duplicate_of_source_path": "" if index == 0 else primary["source_path"],
                }
            )
    source_manifest.sort(key=lambda row: row["source_path"])
    canonical_documents.sort(key=lambda row: (SOURCE_PRECEDENCE[row["source_type"]], row["source_path"]))
    canonical_payloads = [canonical_by_hash[row["document_content_sha256"]] for row in canonical_documents]
    return source_manifest, canonical_documents, {row["document_id"]: row["text"] for row in canonical_payloads}


def _is_book_heading(value: str) -> bool:
    text = normalize_text(value)
    if not text or len(text) > 90:
        return False
    if BOOK_HEADING_RE.match(text):
        return True
    if len(text) <= 26 and not re.search(r"[。；，：,;]", text):
        return True
    return False


def _book_rows(config: BuildConfig) -> list[dict[str, Any]]:
    if not config.textbook_root.is_dir():
        raise FileNotFoundError(config.textbook_root)
    result: list[dict[str, Any]] = []
    for path in sorted(config.textbook_root.rglob("*.txt"), key=lambda value: value.as_posix()):
        if path.name.startswith("."):
            continue
        raw = path.read_text(encoding="utf-8", errors="strict")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw.splitlines()
        values = parsed if isinstance(parsed, list) else [parsed]
        items = [normalize_text(str(value)) for value in values if normalize_text(str(value))]
        if not items:
            continue
        relative = path.resolve().relative_to(config.textbook_root.resolve())
        subject = relative.parts[0] if len(relative.parts) > 1 else "其他法律教材"
        chapter_title = normalize_text(path.stem)
        section_title = chapter_title
        section_items: list[str] = []
        sections: list[tuple[str, list[str]]] = []
        for item in items:
            if _is_book_heading(item):
                if section_items:
                    sections.append((section_title, section_items))
                    section_items = []
                section_title = item
            else:
                section_items.append(item)
        if section_items:
            sections.append((section_title, section_items))
        if not sections:
            sections.append((chapter_title, items))
        source_path = _safe_relative(path, config.textbook_root, "JEC-QA/reference_book")
        source_sha = _sha256_file(path)
        priority = "primary" if subject in {"刑法", "刑事诉讼法"} else "secondary"
        for section_no, (section, bodies) in enumerate(sections, 1):
            joined = "\n".join(bodies)
            parts = split_long_text(
                joined,
                target_chars=config.target_chunk_chars,
                max_chars=config.max_chunk_chars,
                overlap_chars=config.overlap_chars,
            )
            for part_index, content in enumerate(parts, 1):
                chunk_id = _stable_id(
                    "RAGT", subject, chapter_title, section, str(section_no), str(part_index), _sha256_text(content)
                )
                row = {
                    "schema_version": "hybrid-rag-textbook-chunk-v1",
                    "chunk_id": chunk_id,
                    "retrieval_tier": "textbook_explanation",
                    "source_type": "textbook_explanation",
                    "authority_level": "教材解释",
                    "subject": subject,
                    "priority": priority,
                    "chapter_no": re.match(rf"^(第[{CHINESE_NUMBER}]+章)", chapter_title).group(1)
                    if re.match(rf"^(第[{CHINESE_NUMBER}]+章)", chapter_title)
                    else "",
                    "chapter_title": chapter_title,
                    "section_title": section,
                    "part_index": part_index,
                    "part_total": len(parts),
                    "content": content,
                    "embed_text": f"学科：{subject}\n章节：{chapter_title}\n小节：{section}\n{content}",
                    "related_knowledge_ids": [],
                    "related_article_refs": [],
                    "effective_status": "edition_unknown",
                    "governance_status": "teaching_reference_requires_review",
                    "source_path": source_path,
                    "source_file_sha256": source_sha,
                    "source_snapshot_id": f"jecqa-reference-book-{config.snapshot_date}",
                    "risk_flags": ["edition_unknown", "textbook_does_not_override_current_law"],
                }
                result.append(_with_hash(row))
    result.sort(key=lambda row: (row["subject"], row["source_path"], row["chunk_id"]))
    return result


def _question_public(
    *,
    question_id: str,
    source_dataset: str,
    source_path: str,
    subject: str,
    question_type: str,
    stem: str,
    options: dict[str, str] | None,
    knowledge_ids: Sequence[str] = (),
    ability_tags: Sequence[str] = (),
    difficulty: Any = None,
    phase_eligibility: Sequence[str] = (),
    publication_status: str = "candidate_requires_legal_review",
    context_public: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_options = {str(key): normalize_text(str(value)) for key, value in (options or {}).items()}
    normalized_stem = normalize_text(stem)
    option_text = "\n".join(f"{key}. {value}" for key, value in sorted(normalized_options.items()))
    embed_parts = [f"学科：{subject}", f"题型：{question_type}", normalized_stem]
    if option_text:
        embed_parts.append(option_text)
    row = {
        "schema_version": "hybrid-rag-question-public-v1",
        "question_id": question_id,
        "visibility": "public",
        "retrieval_tier": "question_teaching_public",
        "source_dataset": source_dataset,
        "subject": subject,
        "question_type": question_type,
        "stem": normalized_stem,
        "options": normalized_options,
        "knowledge_ids": list(knowledge_ids),
        "ability_tags": list(ability_tags),
        "difficulty_candidate": difficulty,
        "phase_eligibility": list(phase_eligibility),
        "publication_status": publication_status,
        "context_public": context_public or {},
        "embed_text": "\n".join(embed_parts),
        "source_path": source_path,
    }
    return _with_hash(row)


def _question_private(
    *,
    question_id: str,
    source_dataset: str,
    source_path: str,
    answer: Any = None,
    rationale: Any = None,
    misconceptions: Any = None,
    rubric: Any = None,
    expected_points: Any = None,
    scoring_rule: Any = None,
) -> dict[str, Any]:
    row = {
        "schema_version": "hybrid-rag-question-private-v1",
        "question_id": question_id,
        "visibility": "private",
        "student_retrieval_allowed": False,
        "embedding_enabled": False,
        "source_dataset": source_dataset,
        "answer_private": answer,
        "rationale_private": rationale,
        "misconceptions_private": misconceptions,
        "rubric_private": rubric,
        "expected_points_private": expected_points,
        "scoring_rule": scoring_rule,
        "source_path": source_path,
    }
    return _with_hash(row)


def _question_rows(config: BuildConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    public: list[dict[str, Any]] = []
    private: list[dict[str, Any]] = []
    product_sources = [
        (config.task_items_path, "legalworld_product_objective"),
        (config.subjective_tasks_path, "legalworld_product_subjective"),
    ]
    for path, dataset in product_sources:
        if not path.is_file():
            raise FileNotFoundError(path)
        source_path = f"repo/{path.name}"
        for row in _read_jsonl(path):
            question_id = str(row["task_id"])
            is_subjective = "prompt" in row
            stem = str(row.get("prompt") if is_subjective else row.get("stem") or "")
            public.append(
                _question_public(
                    question_id=question_id,
                    source_dataset=dataset,
                    source_path=source_path,
                    subject=str(row.get("domain") or "刑法"),
                    question_type=str(row.get("task_type") or ("subjective" if is_subjective else "objective")),
                    stem=stem,
                    options=row.get("options") if isinstance(row.get("options"), dict) else {},
                    knowledge_ids=[str(value) for value in row.get("knowledge_ids") or []],
                    ability_tags=[str(value) for value in row.get("target_abilities") or []],
                    difficulty=row.get("difficulty"),
                    phase_eligibility=[str(value) for value in row.get("phase_eligibility") or []],
                    publication_status=str(row.get("status") or "candidate_requires_legal_review"),
                    context_public=row.get("context_public") if isinstance(row.get("context_public"), dict) else {},
                )
            )
            private.append(
                _question_private(
                    question_id=question_id,
                    source_dataset=dataset,
                    source_path=source_path,
                    answer=row.get("answer_private"),
                    rationale=row.get("rationale_private"),
                    misconceptions=row.get("misconceptions_private"),
                    rubric=row.get("rubric_private"),
                    expected_points=row.get("expected_points_private"),
                    scoring_rule=row.get("scoring_rule"),
                )
            )

    for path, question_type in [
        (config.jecqa_single_path, "single_choice"),
        (config.jecqa_multiple_path, "multiple_choice"),
    ]:
        if not path.is_file():
            raise FileNotFoundError(path)
        source_path = f"CAIL2020/司法考试/{path.name}"
        for row in _read_jsonl(path):
            if normalize_text(str(row.get("subject") or "")) != "刑法":
                continue
            question_id = f"JECQA_{question_type.upper()}_{row['id']}"
            public.append(
                _question_public(
                    question_id=question_id,
                    source_dataset="CAIL2020_JECQA",
                    source_path=source_path,
                    subject="刑法",
                    question_type=question_type,
                    stem=str(row.get("statement") or ""),
                    options=row.get("option_list") if isinstance(row.get("option_list"), dict) else {},
                    publication_status="candidate_requires_legal_review",
                )
            )
            private.append(
                _question_private(
                    question_id=question_id,
                    source_dataset="CAIL2020_JECQA",
                    source_path=source_path,
                    answer=row.get("answer"),
                )
            )
    public.sort(key=lambda row: row["question_id"])
    private.sort(key=lambda row: row["question_id"])
    return public, private


def _contains_absolute_path(value: Any) -> bool:
    serialized = json.dumps(value, ensure_ascii=False)
    return bool(re.search(r"(?:[A-Za-z]:\\|[A-Za-z]:/|/home/|/Users/)", serialized))


def _validate_schemas(groups: Sequence[tuple[str, Sequence[dict[str, Any]]]]) -> list[str]:
    failures: list[str] = []
    for schema_name, rows in groups:
        schema = json.loads((SCHEMAS_ROOT / schema_name).read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        for index, row in enumerate(rows, 1):
            errors = sorted(validator.iter_errors(row), key=lambda item: list(item.path))
            if errors:
                failures.append(f"{schema_name}:{index}:{errors[0].message}")
                if len(failures) >= 20:
                    return failures
    return failures


def _build_audit(
    *,
    source_manifest: list[dict[str, Any]],
    canonical_documents: list[dict[str, Any]],
    legal_chunks: list[dict[str, Any]],
    case_parents: list[dict[str, Any]],
    textbook_chunks: list[dict[str, Any]],
    question_public: list[dict[str, Any]],
    question_private: list[dict[str, Any]],
    schema_errors: list[str],
) -> dict[str, Any]:
    public_keys = set().union(*(row.keys() for row in question_public)) if question_public else set()
    private_leak_keys = sorted(public_keys & PRIVATE_FIELD_NAMES)
    public_ids = [row["question_id"] for row in question_public]
    private_ids = [row["question_id"] for row in question_private]
    parent_by_id = {row["parent_id"]: row for row in case_parents}
    case_children = [row for row in legal_chunks if row["source_type"] == "case"]
    gates = {
        "source_accounting_exact": len(source_manifest)
        == len(canonical_documents) + sum(not row["is_canonical"] for row in source_manifest),
        "canonical_document_ids_unique": len({row["document_id"] for row in canonical_documents})
        == len(canonical_documents),
        "inventory_metadata_all_or_none": not any(
            row.get("inventory_metadata_present") for row in canonical_documents
        )
        or all(row.get("inventory_metadata_present") for row in canonical_documents),
        "legal_chunk_ids_unique": len({row["chunk_id"] for row in legal_chunks}) == len(legal_chunks),
        "case_parent_ids_unique": len(parent_by_id) == len(case_parents),
        "case_children_all_have_parent": bool(case_children)
        and all(row["parent_id"] in parent_by_id for row in case_children),
        "case_parent_child_document_match": all(
            parent_by_id[row["parent_id"]]["document_id"] == row["document_id"]
            and parent_by_id[row["parent_id"]]["content_sha256"] == row["parent_content_sha256"]
            for row in case_children
        ),
        "non_case_chunks_have_no_parent": all(
            not row["parent_id"] and row["retrieval_unit"] == "chunk"
            for row in legal_chunks
            if row["source_type"] != "case"
        ),
        "textbook_chunk_ids_unique": len({row["chunk_id"] for row in textbook_chunks})
        == len(textbook_chunks),
        "all_chunks_nonempty": all(row["content"].strip() and row["embed_text"].strip() for row in legal_chunks + textbook_chunks),
        "question_public_private_ids_match": public_ids == private_ids,
        "question_public_private_keys_absent": not private_leak_keys,
        "question_private_embedding_disabled": all(
            row["visibility"] == "private"
            and row["student_retrieval_allowed"] is False
            and row["embedding_enabled"] is False
            for row in question_private
        ),
        "absolute_paths_absent": not any(
            _contains_absolute_path(rows)
            for rows in (
                source_manifest,
                canonical_documents,
                legal_chunks,
                case_parents,
                textbook_chunks,
                question_public,
                question_private,
            )
        ),
        "model_network_calls_zero": True,
        "schema_validation_passed": not schema_errors,
    }
    return {
        "schema_version": "hybrid-rag-corpus-audit-v1",
        "gates": gates,
        "all_passed": all(gates.values()),
        "private_leak_keys": private_leak_keys,
        "schema_errors": schema_errors,
        "counts": {
            "physical_sources": len(source_manifest),
            "canonical_documents": len(canonical_documents),
            "duplicate_sources": sum(not row["is_canonical"] for row in source_manifest),
            "legal_chunks": len(legal_chunks),
            "case_parents": len(case_parents),
            "case_child_chunks": len(case_children),
            "textbook_chunks": len(textbook_chunks),
            "question_public": len(question_public),
            "question_private": len(question_private),
            "inventory_metadata_documents": sum(
                bool(row.get("inventory_metadata_present")) for row in canonical_documents
            ),
        },
        "execution": {
            "embedding_calls": 0,
            "reranker_calls": 0,
            "model_calls": 0,
            "network_calls": 0,
        },
        "evidence_boundary": (
            "canonical and chunk artifacts are retrieval candidates; they do not establish current legal validity, "
            "semantic entailment, teacher approval, or learning effects"
        ),
    }


def _manifest(
    *,
    config: BuildConfig,
    audit: dict[str, Any],
    outputs: dict[str, Path],
    legal_chunks: list[dict[str, Any]],
    case_parents: list[dict[str, Any]],
    textbook_chunks: list[dict[str, Any]],
    question_public: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "hybrid-rag-corpus-manifest-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "builder": BUILDER_VERSION,
        "snapshot_date": config.snapshot_date,
        "inventory": {
            "configured": bool(config.inventory_path),
            "file_sha256": _sha256_file(config.inventory_path)
            if config.inventory_path and config.inventory_path.is_file()
            else "",
            "matched_documents": audit["counts"]["inventory_metadata_documents"],
        },
        "chunking": {
            "target_chars": config.target_chunk_chars,
            "max_chars": config.max_chunk_chars,
            "overlap_chars": config.overlap_chars,
            "law_regulation_judicial": "article_first_then_length_fallback",
            "case": "document_to_semantic_parent_to_retrieval_child",
            "textbook": "chapter_section_then_length_fallback",
            "question": "one_question_one_public_record_and_one_private_record",
        },
        "retrieval_contract": {
            "sparse": "BM25F",
            "dense": "Qwen/Qwen3-Embedding-8B_pending_probe",
            "fusion": "RRF_pending_runtime",
            "reranker": "required_after_rrf_pending_probe",
            "exact_article_protection": True,
            "fallbacks": ["reranker_to_rrf", "embedding_to_bm25f"],
        },
        "counts": audit["counts"],
        "by_source_type": dict(Counter(row["source_type"] for row in legal_chunks)),
        "case_parent_section_types": dict(Counter(row["section_type"] for row in case_parents)),
        "textbook_by_subject": dict(Counter(row["subject"] for row in textbook_chunks)),
        "question_by_dataset": dict(Counter(row["source_dataset"] for row in question_public)),
        "outputs": {
            name: {
                "file": path.name,
                "sha256": _sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for name, path in outputs.items()
            if path.is_file()
        },
        "execution": audit["execution"],
        "audit_all_passed": audit["all_passed"],
        "evidence_boundary": audit["evidence_boundary"],
    }


def _public_audit_payload(manifest: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "hybrid-rag-corpus-public-audit-v1",
        "generated_at": manifest["generated_at"],
        "snapshot_date": manifest["snapshot_date"],
        "builder": manifest["builder"],
        "counts": manifest["counts"],
        "by_source_type": manifest["by_source_type"],
        "case_parent_section_types": manifest["case_parent_section_types"],
        "textbook_by_subject": manifest["textbook_by_subject"],
        "question_by_dataset": manifest["question_by_dataset"],
        "retrieval_contract": manifest["retrieval_contract"],
        "output_hashes": {name: row["sha256"] for name, row in manifest["outputs"].items()},
        "gates": audit["gates"],
        "all_passed": audit["all_passed"],
        "execution": audit["execution"],
        "evidence_boundary": audit["evidence_boundary"],
    }


def _public_audit_markdown(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    gates = payload["gates"]
    lines = [
        "# Hybrid RAG Corpus V1 机器审计",
        "",
        f"- 快照日期：`{payload['snapshot_date']}`",
        f"- 构建器：`{payload['builder']}`",
        f"- 物理候选源：**{counts['physical_sources']:,}**",
        f"- canonical文档：**{counts['canonical_documents']:,}**；重复源：**{counts['duplicate_sources']:,}**",
        f"- 法律/法规/司法/案例块：**{counts['legal_chunks']:,}**",
        f"- 案例语义父段/检索子块：**{counts['case_parents']:,} / {counts['case_child_chunks']:,}**",
        f"- 教材解释块：**{counts['textbook_chunks']:,}**",
        f"- 题目public/private：**{counts['question_public']:,} / {counts['question_private']:,}**",
        "",
        "## 检索契约",
        "",
        "`BM25F + Qwen3-Embedding-8B → RRF → Reranker → 权威/时效/Evidence门禁`。",
        "Reranker失败降级RRF；Embedding失败降级BM25F；明确条号命中不可被语义排序挤掉。",
        "",
        "## 确定性门禁",
        "",
    ]
    lines.extend(f"- [{'x' if passed else ' '}] `{name}`" for name, passed in gates.items())
    lines.extend(
        [
            "",
            "## 证据边界",
            "",
            payload["evidence_boundary"],
            "本阶段Embedding/Reranker/模型/网络调用均为0；该产物证明canonical、分块与答案隔离，不是混合检索效果。",
            "",
        ]
    )
    return "\n".join(lines)


def build_corpus(config: BuildConfig) -> tuple[dict[str, Any], dict[str, Any]]:
    if config.target_chunk_chars <= 0 or config.max_chunk_chars < config.target_chunk_chars:
        raise ValueError("invalid chunk-size configuration")
    if config.overlap_chars < 0 or config.overlap_chars >= config.target_chunk_chars:
        raise ValueError("invalid overlap configuration")
    output = config.output_dir
    output.mkdir(parents=True, exist_ok=True)
    source_manifest, canonical_documents, text_by_document = _load_source_candidates(config)
    legal_chunks: list[dict[str, Any]] = []
    case_parents: list[dict[str, Any]] = []
    for document in canonical_documents:
        document_chunks, document_parents = split_legal_document_with_parents(
                document,
                text_by_document[document["document_id"]],
                target_chars=config.target_chunk_chars,
                max_chars=config.max_chunk_chars,
                overlap_chars=config.overlap_chars,
        )
        legal_chunks.extend(document_chunks)
        case_parents.extend(document_parents)
    legal_chunks.sort(key=lambda row: (SOURCE_PRECEDENCE[row["source_type"]], row["source_path"], row["chunk_id"]))
    case_parents.sort(key=lambda row: (row["source_path"], row["section_index"], row["parent_id"]))
    textbook_chunks = _book_rows(config)
    question_public, question_private = _question_rows(config)

    outputs = {
        "source_manifest": output / "source_manifest.jsonl",
        "canonical_documents": output / "canonical_documents.jsonl",
        "legal_chunks": output / "legal_chunks.jsonl",
        "case_parents": output / "case_parents.jsonl",
        "textbook_chunks": output / "textbook_chunks.jsonl",
        "question_public": output / "question_public.jsonl",
        "question_private": output / "question_private.jsonl",
        "audit": output / "audit.json",
    }
    _write_jsonl(outputs["source_manifest"], source_manifest)
    _write_jsonl(outputs["canonical_documents"], canonical_documents)
    _write_jsonl(outputs["legal_chunks"], legal_chunks)
    _write_jsonl(outputs["case_parents"], case_parents)
    _write_jsonl(outputs["textbook_chunks"], textbook_chunks)
    _write_jsonl(outputs["question_public"], question_public)
    _write_jsonl(outputs["question_private"], question_private)
    schema_errors = _validate_schemas(
        [
            ("hybrid-rag-source-manifest-v1.schema.json", source_manifest),
            ("hybrid-rag-document-v1.schema.json", canonical_documents),
            ("hybrid-rag-chunk-v1.schema.json", legal_chunks),
            ("hybrid-rag-case-parent-v1.schema.json", case_parents),
            ("hybrid-rag-textbook-chunk-v1.schema.json", textbook_chunks),
            ("hybrid-rag-question-public-v1.schema.json", question_public),
            ("hybrid-rag-question-private-v1.schema.json", question_private),
        ]
    )
    audit = _build_audit(
        source_manifest=source_manifest,
        canonical_documents=canonical_documents,
        legal_chunks=legal_chunks,
        case_parents=case_parents,
        textbook_chunks=textbook_chunks,
        question_public=question_public,
        question_private=question_private,
        schema_errors=schema_errors,
    )
    _write_json(outputs["audit"], audit)
    manifest = _manifest(
        config=config,
        audit=audit,
        outputs=outputs,
        legal_chunks=legal_chunks,
        case_parents=case_parents,
        textbook_chunks=textbook_chunks,
        question_public=question_public,
    )
    _write_json(output / "manifest.json", manifest)
    public_payload = _public_audit_payload(manifest, audit)
    if config.public_audit_json:
        _write_json(config.public_audit_json, public_payload)
    if config.public_audit_md:
        config.public_audit_md.parent.mkdir(parents=True, exist_ok=True)
        config.public_audit_md.write_text(_public_audit_markdown(public_payload), encoding="utf-8")
    return manifest, audit


__all__ = [
    "BuildConfig",
    "PRIVATE_FIELD_NAMES",
    "build_corpus",
    "normalize_text",
    "split_legal_document",
    "split_legal_document_with_parents",
    "split_long_text",
]
