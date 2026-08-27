"""Build governed criminal-law JSONL from official DOCX download artifacts.

The consolidated third-party file named "2024 latest" is intentionally not
used because it contains publisher contamination. Instead this builder parses
the official 2020 Criminal Law text, applies the seven exact changes in the
official Criminal Law Amendment (XII), and parses the official 2018 Criminal
Procedure Law text. The original DOCX files remain read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from docx import Document


ARTICLE_START = re.compile(
    r"^(第[一二三四五六七八九十百千万零〇两\d]+条"
    r"(?:之[一二三四五六七八九十百千万零〇两\d]+)?)\s+(.*)$"
)
STRUCTURE_HEADING = re.compile(
    r"^(?:第[一二三四五六七八九十百千万零〇两\d]+(?:编|章|节)(?:\s.*)?|附\s*则)$"
)
AMENDMENT_ITEM = re.compile(r"^([一二三四五六七八九十]+)、")
PORTAL_URL = "https://flk.npc.gov.cn/"
PROHIBITED_TEXT = ("中国刑事辩护网", "华律网", "找法网")

AMENDMENT_TWELVE_RULES = {
    "一": ("第一百六十五条", "full"),
    "二": ("第一百六十六条", "full"),
    "三": ("第一百六十九条", "full"),
    "四": ("第三百八十七条", "first_paragraph"),
    "五": ("第三百九十条", "full"),
    "六": ("第三百九十一条", "first_paragraph"),
    "七": ("第三百九十三条", "full"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_docx_paragraphs(path: Path) -> list[str]:
    return [paragraph.text.strip() for paragraph in Document(path).paragraphs]


def parse_articles_from_paragraphs(
    paragraphs: Iterable[str],
    *,
    expected_last_ref: str,
    stop_heading: str | None = None,
) -> OrderedDict[str, str]:
    articles: OrderedDict[str, list[str]] = OrderedDict()
    current_ref = ""
    started = False

    for raw in paragraphs:
        text = str(raw or "").strip()
        if not text:
            continue
        if started and stop_heading and text == stop_heading:
            break
        if STRUCTURE_HEADING.fullmatch(text):
            continue

        match = ARTICLE_START.match(text)
        if match and (started or match.group(1) == "第一条"):
            article_ref, first_text = match.groups()
            if article_ref in articles:
                raise ValueError(f"duplicate article header: {article_ref}")
            articles[article_ref] = [first_text.strip()] if first_text.strip() else []
            current_ref = article_ref
            started = True
            continue

        if started and current_ref:
            articles[current_ref].append(text)

    if not articles:
        raise ValueError("no articles found")
    if next(reversed(articles)) != expected_last_ref:
        raise ValueError(
            f"unexpected last article: {next(reversed(articles))}; expected {expected_last_ref}"
        )
    return OrderedDict(
        (article_ref, "\n".join(parts).strip())
        for article_ref, parts in articles.items()
    )


def _split_amendment_items(paragraphs: Iterable[str]) -> dict[str, list[str]]:
    items: dict[str, list[str]] = {}
    current = ""
    for raw in paragraphs:
        text = str(raw or "").strip()
        if not text:
            continue
        match = AMENDMENT_ITEM.match(text)
        if match:
            current = match.group(1)
            items[current] = [text]
        elif current:
            items[current].append(text)
    return items


def _quoted_replacement(lines: list[str]) -> str:
    if not lines:
        raise ValueError("empty amendment block")
    first = re.sub(r"^.*?修改为：“", "", lines[0], count=1)
    if first == lines[0]:
        raise ValueError(f"amendment block has no replacement marker: {lines[0]}")
    output = [first.lstrip("“")]
    output.extend(line.lstrip("“") for line in lines[1:])
    output[-1] = output[-1].rstrip("”")
    return "\n".join(output).strip()


def apply_amendment_twelve(
    base_articles: OrderedDict[str, str],
    amendment_paragraphs: Iterable[str],
) -> tuple[OrderedDict[str, str], list[str]]:
    items = _split_amendment_items(amendment_paragraphs)
    result = OrderedDict(base_articles)
    changed: list[str] = []

    for item_label, (article_ref, mode) in AMENDMENT_TWELVE_RULES.items():
        if article_ref not in result:
            raise ValueError(f"amendment target missing from base law: {article_ref}")
        if item_label not in items:
            raise ValueError(f"amendment item missing: {item_label}")
        replacement = _quoted_replacement(items[item_label])
        if mode == "full":
            result[article_ref] = replacement
        elif mode == "first_paragraph":
            existing = result[article_ref].splitlines()
            if not existing:
                raise ValueError(f"empty base article: {article_ref}")
            result[article_ref] = "\n".join([replacement, *existing[1:]]).strip()
        else:
            raise ValueError(f"unknown amendment mode: {mode}")
        changed.append(article_ref)

    expected = {rule[0] for rule in AMENDMENT_TWELVE_RULES.values()}
    if set(changed) != expected:
        raise ValueError("amendment XII did not change the expected seven articles")
    return result, changed


def _relative_source_path(path: Path, source_root: Path) -> str:
    try:
        return path.resolve().relative_to(source_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _bundle_sha256(artifacts: list[dict[str, Any]]) -> str:
    body = json.dumps(artifacts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def build_records(
    articles: OrderedDict[str, str],
    *,
    document_id: str,
    source_title: str,
    category: str,
    effective_date: str,
    version_as_of: str,
    snapshot_id: str,
    source_bundle_sha256: str,
    amended_refs: set[str] | None = None,
) -> list[dict[str, Any]]:
    amended = amended_refs or set()
    records = []
    for article_ref, content in articles.items():
        if not content:
            raise ValueError(f"empty article content: {document_id}:{article_ref}")
        for phrase in PROHIBITED_TEXT:
            if phrase in content:
                raise ValueError(f"prohibited publisher text in {document_id}:{article_ref}: {phrase}")
        records.append(
            {
                "schema_version": "simlaw-law-article-v2",
                "document_id": f"{document_id}:{article_ref}",
                "source_title": source_title,
                "category": category,
                "article_ref": article_ref,
                "title": article_ref,
                "content": content,
                "effective_date": effective_date,
                "version_as_of": version_as_of,
                "effective_status": "effective_as_of_download_snapshot",
                "source_url": PORTAL_URL,
                "source_url_scope": "official_portal_only",
                "source_snapshot_id": snapshot_id,
                "source_bundle_sha256": source_bundle_sha256,
                "article_modified_by": (
                    "中华人民共和国刑法修正案（十二）" if article_ref in amended else ""
                ),
            }
        )
    return records


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    return sha256_file(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--criminal-law-docx", type=Path, required=True)
    parser.add_argument("--amendment-12-docx", type=Path, required=True)
    parser.add_argument("--criminal-procedure-docx", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--download-snapshot-date", default="2026-02-26")
    parser.add_argument("--quarantined-consolidation", type=Path)
    args = parser.parse_args()

    source_paths = [
        args.criminal_law_docx,
        args.amendment_12_docx,
        args.criminal_procedure_docx,
    ]
    for path in source_paths:
        if not path.is_file():
            raise FileNotFoundError(path)

    criminal_base = parse_articles_from_paragraphs(
        read_docx_paragraphs(args.criminal_law_docx),
        expected_last_ref="第四百五十二条",
        stop_heading="附件一",
    )
    criminal_law, amended_refs = apply_amendment_twelve(
        criminal_base, read_docx_paragraphs(args.amendment_12_docx)
    )
    procedure_law = parse_articles_from_paragraphs(
        read_docx_paragraphs(args.criminal_procedure_docx),
        expected_last_ref="第三百零八条",
    )
    if len(criminal_law) != 505:
        raise ValueError(f"criminal law article count must be 505, got {len(criminal_law)}")
    if "第二百条" not in criminal_law:
        raise ValueError("official Criminal Law article 200 is missing")
    if len(procedure_law) != 308:
        raise ValueError(f"criminal procedure article count must be 308, got {len(procedure_law)}")

    criminal_artifacts = [
        {
            "role": "official_consolidated_base",
            "path": _relative_source_path(args.criminal_law_docx, args.source_root),
            "sha256": sha256_file(args.criminal_law_docx),
            "promulgated_date": "2020-12-26",
        },
        {
            "role": "official_amendment",
            "path": _relative_source_path(args.amendment_12_docx, args.source_root),
            "sha256": sha256_file(args.amendment_12_docx),
            "promulgated_date": "2023-12-29",
            "effective_date": "2024-03-01",
        },
    ]
    procedure_artifacts = [
        {
            "role": "official_consolidated_text",
            "path": _relative_source_path(args.criminal_procedure_docx, args.source_root),
            "sha256": sha256_file(args.criminal_procedure_docx),
            "promulgated_date": "2018-10-26",
        }
    ]
    criminal_bundle = _bundle_sha256(criminal_artifacts)
    procedure_bundle = _bundle_sha256(procedure_artifacts)
    criminal_rows = build_records(
        criminal_law,
        document_id="xingfa",
        source_title="中华人民共和国刑法",
        category="刑法",
        effective_date="根据《中华人民共和国刑法修正案（十二）》修正，修正内容自2024年3月1日起施行",
        version_as_of="2024-03-01",
        snapshot_id=f"npc-flk-{args.download_snapshot_date}-xingfa-amendment-12",
        source_bundle_sha256=criminal_bundle,
        amended_refs=set(amended_refs),
    )
    procedure_rows = build_records(
        procedure_law,
        document_id="xingsufa",
        source_title="中华人民共和国刑事诉讼法",
        category="刑事诉讼法",
        effective_date="根据2018年10月26日第三次修正",
        version_as_of="2018-10-26",
        snapshot_id=f"npc-flk-{args.download_snapshot_date}-xingsufa",
        source_bundle_sha256=procedure_bundle,
    )

    output_dir = args.output_dir.resolve()
    output_hashes = {
        "xingfa.jsonl": write_jsonl(output_dir / "xingfa.jsonl", criminal_rows),
        "xingsufa.jsonl": write_jsonl(output_dir / "xingsufa.jsonl", procedure_rows),
    }
    quarantine: list[dict[str, Any]] = []
    if args.quarantined_consolidation:
        quarantine_path = args.quarantined_consolidation
        quarantine.append(
            {
                "path": _relative_source_path(quarantine_path, args.source_root),
                "sha256": sha256_file(quarantine_path),
                "reason": "contains third-party publisher contamination; not used as legal authority",
            }
        )
    manifest = {
        "schema_version": "simlaw-law-corpus-manifest-v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "builder": Path(__file__).name,
        "source_portal_url": PORTAL_URL,
        "source_item_url_status": "not_preserved_in_download_artifacts",
        "download_snapshot_date": args.download_snapshot_date,
        "documents": {
            "xingfa": {
                "article_count": len(criminal_rows),
                "version_as_of": "2024-03-01",
                "amended_article_refs": amended_refs,
                "source_bundle_sha256": criminal_bundle,
                "source_artifacts": criminal_artifacts,
            },
            "xingsufa": {
                "article_count": len(procedure_rows),
                "version_as_of": "2018-10-26",
                "source_bundle_sha256": procedure_bundle,
                "source_artifacts": procedure_artifacts,
            },
        },
        "quarantined_sources": quarantine,
        "outputs": output_hashes,
        "warnings": [
            "portal URL identifies the official source system; exact item URLs were not preserved",
            "validity must be rechecked against the official portal before each real classroom term",
        ],
    }
    manifest_path = output_dir / "law_corpus_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "criminal_law_articles": len(criminal_rows),
                "criminal_procedure_articles": len(procedure_rows),
                "amended_articles": amended_refs,
                "output_dir": str(output_dir),
                "manifest_sha256": sha256_file(manifest_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
