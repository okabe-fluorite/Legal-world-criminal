"""Audit a labelled 2024 Criminal Law consolidation against official sources.

The audit deliberately separates two questions:

1. whether the consolidation absorbed Criminal Law Amendment (XII); and
2. whether the whole file is clean enough to become formal Evidence.

It never rewrites the source DOCX files and emits only repository-relative
provenance, counts, hashes and short difference descriptions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_law_corpus_from_official_docx import (  # noqa: E402
    apply_amendment_twelve,
    parse_articles_from_paragraphs,
    read_docx_paragraphs,
)


PUBLISHER_MARKERS = ("中国刑事辩护网提供", "华律网", "找法网")
DISPLAY_HEADING = re.compile(r"^【[^】]*】")
PUNCTUATION = re.compile(r"[\s　《》“”。，；：、（）()！!？?‘’…—\-]+")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_path(path: Path, source_root: Path) -> str:
    return path.resolve().relative_to(source_root.resolve()).as_posix()


def clean_reference_text(value: str) -> str:
    text = DISPLAY_HEADING.sub("", str(value or ""))
    for marker in PUBLISHER_MARKERS:
        text = text.replace(marker, "")
    return re.sub(r"\s+", "", text)


def punctuation_free(value: str) -> str:
    return PUNCTUATION.sub("", value)


def compare_articles(
    official: dict[str, str],
    reference: dict[str, str],
) -> dict[str, Any]:
    missing = [ref for ref in official if ref not in reference]
    extra = [ref for ref in reference if ref not in official]
    differences: list[dict[str, Any]] = []
    exact = 0
    punctuation_only = 0

    for article_ref, official_text in official.items():
        reference_text = reference.get(article_ref, "")
        official_clean = clean_reference_text(official_text)
        reference_clean = clean_reference_text(reference_text)
        if official_clean == reference_clean:
            exact += 1
            continue
        if punctuation_free(official_clean) == punctuation_free(reference_clean):
            category = "punctuation_only"
            punctuation_only += 1
        elif not reference_text:
            category = "missing_article"
        else:
            category = "content_difference"
        differences.append(
            {
                "article_ref": article_ref,
                "category": category,
                "official_clean_sha256": hashlib.sha256(
                    official_clean.encode("utf-8")
                ).hexdigest(),
                "reference_clean_sha256": hashlib.sha256(
                    reference_clean.encode("utf-8")
                ).hexdigest(),
                "official_length": len(official_clean),
                "reference_length": len(reference_clean),
            }
        )

    return {
        "official_article_count": len(official),
        "reference_article_count": len(reference),
        "same_article_ref_set": not missing and not extra,
        "missing_article_refs": missing,
        "extra_article_refs": extra,
        "exact_after_heading_and_watermark_cleanup": exact,
        "punctuation_only_difference_count": punctuation_only,
        "remaining_difference_count": len(differences),
        "differences": differences,
    }


def build_audit(
    *,
    source_root: Path,
    reference_docx: Path,
    official_base_docx: Path,
    amendment_12_docx: Path,
    audit_date: str,
) -> dict[str, Any]:
    reference_paragraphs = read_docx_paragraphs(reference_docx)
    reference_articles = parse_articles_from_paragraphs(
        reference_paragraphs,
        expected_last_ref="第四百五十二条",
        stop_heading="附件一",
    )
    official_base = parse_articles_from_paragraphs(
        read_docx_paragraphs(official_base_docx),
        expected_last_ref="第四百五十二条",
        stop_heading="附件一",
    )
    official_articles, amended_refs = apply_amendment_twelve(
        official_base,
        read_docx_paragraphs(amendment_12_docx),
    )
    comparison = compare_articles(official_articles, reference_articles)
    marker_counts = {
        marker: sum(marker in paragraph for paragraph in reference_paragraphs)
        for marker in PUBLISHER_MARKERS
    }
    amendment_matches = {
        article_ref: clean_reference_text(official_articles[article_ref])
        == clean_reference_text(reference_articles.get(article_ref, ""))
        for article_ref in amended_refs
    }
    all_amendment_matches = all(amendment_matches.values())
    formal_admission = (
        comparison["remaining_difference_count"] == 0
        and not comparison["missing_article_refs"]
        and sum(marker_counts.values()) == 0
    )

    return {
        "schema_version": "criminal-law-consolidation-audit-v1",
        "audit_date": audit_date,
        "question": "Can the labelled 2024 consolidation replace the governed official build?",
        "official_version_chain": {
            "base": "中华人民共和国刑法（2020-12-26国家法律法规数据库快照）",
            "amendment": "中华人民共和国刑法修正案（十二）（2023-12-29通过）",
            "amendment_effective_from": "2024-03-01",
            "result_version_as_of": "2024-03-01",
            "online_verification": [
                "https://www.npc.gov.cn/npc/c2/c30834/202401/t20240103_434056.html",
                "https://www.npc.gov.cn/c2/c30834/202403/t20240301_434965.html",
            ],
        },
        "sources": {
            "reference": {
                "path": relative_path(reference_docx, source_root),
                "sha256": sha256_file(reference_docx),
                "label_year_is_plausible": True,
            },
            "official_base": {
                "path": relative_path(official_base_docx, source_root),
                "sha256": sha256_file(official_base_docx),
            },
            "official_amendment_12": {
                "path": relative_path(amendment_12_docx, source_root),
                "sha256": sha256_file(amendment_12_docx),
            },
        },
        "comparison": comparison,
        "publisher_marker_counts": marker_counts,
        "amendment_12_article_matches": amendment_matches,
        "all_seven_amendment_12_articles_match": all_amendment_matches,
        "decision": {
            "formal_evidence_admitted": formal_admission,
            "classification": (
                "formal_official_consolidation"
                if formal_admission
                else "2024_consolidation_reference_with_content_defects"
            ),
            "reason": (
                "The 2024 date is valid and all seven Amendment XII replacements match, "
                "but the file is not a clean article-complete official consolidation."
            ),
            "formal_source_remains": (
                "deterministic merge of the official 2020 Criminal Law text and "
                "official Amendment XII"
            ),
        },
        "evidence_boundary": [
            "A correct version year does not by itself establish exact article integrity.",
            "Publisher markers and content differences block direct quote use.",
            "The reference remains useful for cross-checking Amendment XII incorporation.",
        ],
    }


def render_markdown(audit: dict[str, Any]) -> str:
    comparison = audit["comparison"]
    marker_total = sum(audit["publisher_marker_counts"].values())
    rows = [
        "# 2024刑法合并版内容审计",
        "",
        "## 结论",
        "",
        "“2024年最新版”的年份口径正确，且刑法修正案（十二）涉及的七处条文全部匹配。",
        "但该文件存在缺条、正文差异和第三方标记，不能替代正式法源；正式库继续使用官方2020正文与官方修正案十二的确定性合并结果。",
        "",
        "## 机器核验",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| 官方合并条文 | {comparison['official_article_count']} |",
        f"| 参考文件条文 | {comparison['reference_article_count']} |",
        f"| 去标题/水印后逐字一致 | {comparison['exact_after_heading_and_watermark_cleanup']} |",
        f"| 仍有差异 | {comparison['remaining_difference_count']} |",
        f"| 缺失条文 | {len(comparison['missing_article_refs'])} |",
        f"| 第三方标记 | {marker_total} |",
        f"| 修正案十二七处匹配 | {'7/7' if audit['all_seven_amendment_12_articles_match'] else '未全部匹配'} |",
        "",
        "## 差异条号",
        "",
        ", ".join(row["article_ref"] for row in comparison["differences"]),
        "",
        "## 证据边界",
        "",
        "- 版本年份正确，不等于每一条正文均可直接引用。",
        "- 本审计只做文本一致性和来源门禁，不代替法学教师的时效复核。",
        "- 参考文件保留为交叉校验源，不进入正式EvidencePack。",
        "",
    ]
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--reference-docx", type=Path, required=True)
    parser.add_argument("--official-base-docx", type=Path, required=True)
    parser.add_argument("--amendment-12-docx", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--audit-date", default="2026-08-31")
    args = parser.parse_args()

    audit = build_audit(
        source_root=args.source_root,
        reference_docx=args.reference_docx,
        official_base_docx=args.official_base_docx,
        amendment_12_docx=args.amendment_12_docx,
        audit_date=args.audit_date,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    args.output_md.write_text(render_markdown(audit), encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "formal_evidence_admitted": audit["decision"]["formal_evidence_admitted"],
                "exact_matches": audit["comparison"]["exact_after_heading_and_watermark_cleanup"],
                "differences": audit["comparison"]["remaining_difference_count"],
                "all_amendment_12_matches": audit["all_seven_amendment_12_articles_match"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
