from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:20].upper()
    return f"{prefix}_{digest}"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not an object")
            result.append(value)
    return result


def _spread(rows: Sequence[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if count < 0 or len(rows) < count:
        raise ValueError(f"insufficient rows: need={count} have={len(rows)}")
    if count == 0:
        return []
    if count == 1:
        return [rows[0]]
    indexes = [round(index * (len(rows) - 1) / (count - 1)) for index in range(count)]
    return [rows[index] for index in indexes]


def _unique_documents(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("document_id") or row.get("source_path") or row.get("chunk_id"))
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _short_clause(value: str, limit: int = 64) -> str:
    text = re.sub(r"\s+", "", str(value or "")).strip("，。；：")
    for delimiter in ("。", "；", "！", "？"):
        if delimiter in text:
            text = text.split(delimiter, 1)[0]
            break
    return text[:limit]


def _qrel(
    *,
    query_type: str,
    query: str,
    target_tier: str,
    positive_ids: Sequence[str],
    positive_parent_ids: Sequence[str] = (),
    candidate_grade: int = 2,
    notes: str,
) -> dict[str, Any]:
    return {
        "schema_version": "hybrid-rag-qrel-v1",
        "query_id": _stable_id("QREL", query_type, query, "|".join(positive_ids)),
        "query_type": query_type,
        "query": query,
        "target_tier": target_tier,
        "positive_ids": list(positive_ids),
        "positive_parent_ids": list(positive_parent_ids),
        "candidate_grade": candidate_grade,
        "relevance_scale": {"0": "不相关", "1": "部分相关", "2": "直接相关"},
        "review_status": "candidate_requires_teacher_review",
        "is_gold": False,
        "reviewer": None,
        "review_notes": notes,
    }


def build_qrels(
    *,
    legal_chunks: Sequence[dict[str, Any]],
    case_parents: Sequence[dict[str, Any]],
    textbook_chunks: Sequence[dict[str, Any]],
    question_public: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source_type in ("law", "regulation"):
        candidates = _unique_documents(
            row for row in legal_chunks if row.get("source_type") == source_type and row.get("article_ref")
        )
        for row in _spread(candidates, 12):
            result.append(
                _qrel(
                    query_type="exact_article",
                    query=f"请查找《{row['title']}》{row['article_ref']}的原文。",
                    target_tier="legal_authority",
                    positive_ids=[row["chunk_id"]],
                    notes="精确法名和条号候选；教师需确认版本与时效。",
                )
            )

    judicial = _unique_documents(
        row for row in legal_chunks if row.get("source_type") == "judicial_interpretation"
    )
    for row in _spread(judicial, 16):
        clause = _short_clause(row["content"], 34)
        result.append(
            _qrel(
                query_type="judicial_rule",
                query=f"“{row['title']}”中与“{clause}”相关的规定是什么？",
                target_tier="legal_authority",
                positive_ids=[row["chunk_id"]],
                notes="司法文件候选，需教师确认文件类型、效力和查询自然度。",
            )
        )

    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for row in legal_chunks:
        if row.get("source_type") == "case" and row.get("parent_id"):
            children_by_parent[str(row["parent_id"])].append(str(row["chunk_id"]))
    case_candidates = [
        row for row in case_parents if row.get("section_type") in {"summary", "facts", "rule_reasoning"}
    ]
    case_candidates = _unique_documents(case_candidates)
    for row in _spread(case_candidates, 20):
        result.append(
            _qrel(
                query_type="case_rule",
                query=f"在“{row['title']}”中，{_short_clause(row['content'], 48)}涉及什么案件事实或裁判规则？",
                target_tier="legal_authority",
                positive_ids=children_by_parent[row["parent_id"]],
                positive_parent_ids=[row["parent_id"]],
                notes="案例父子段候选；命中子块后应回填该语义父段。",
            )
        )

    primary_books = [row for row in textbook_chunks if row.get("subject") in {"刑法", "刑事诉讼法"}]
    primary_books = _unique_documents(
        {**row, "document_id": f"{row['source_path']}::{row['section_title']}"} for row in primary_books
    )
    for row in _spread(primary_books, 20):
        result.append(
            _qrel(
                query_type="textbook_explanation",
                query=f"请用教材解释{row['subject']}中的“{row['section_title']}”。",
                target_tier="textbook_explanation",
                positive_ids=[row["chunk_id"]],
                notes="教材解释候选，不能覆盖或替代现行法。",
            )
        )

    question_candidates = sorted(question_public, key=lambda row: row["question_id"])
    for row in _spread(question_candidates, 20):
        result.append(
            _qrel(
                query_type="similar_question",
                query=f"查找考查内容相近的练习：{_short_clause(row['stem'], 90)}",
                target_tier="question_teaching_public",
                positive_ids=[row["question_id"]],
                notes="相似题候选；答案和解析不进入学生检索。",
            )
        )

    for index in range(1, 21):
        result.append(
            _qrel(
                query_type="no_answer",
                query=f"请查找《不存在的测试法{index}》第九百九十九条的现行规定。",
                target_tier="legal_authority",
                positive_ids=[],
                candidate_grade=0,
                notes="无答案/越界候选，用于评估误召回与可靠弃权。",
            )
        )
    if len(result) != 120 or len({row["query_id"] for row in result}) != 120:
        raise ValueError("qrel quota or identifier uniqueness failed")
    return result


def build_nli_pairs(legal_chunks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        row
        for row in legal_chunks
        if row.get("source_type") in {"law", "regulation", "judicial_interpretation"}
        and len(_short_clause(row.get("content", ""), 80)) >= 12
    ]
    candidates = _unique_documents(candidates)
    selected = _spread(candidates, 120)
    result: list[dict[str, Any]] = []
    for index, row in enumerate(selected[:60]):
        clause = _short_clause(row["content"], 72)
        result.append(
            {
                "schema_version": "hybrid-rag-nli-label-v1",
                "pair_id": _stable_id("NLI", "entailment", row["chunk_id"], clause),
                "pair_type": "exact_fragment_entailment",
                "premise_source_id": row["chunk_id"],
                "premise_source_type": row["source_type"],
                "premise_title": row["title"],
                "premise_article_ref": row.get("article_ref", ""),
                "premise": row["content"],
                "hypothesis": clause,
                "candidate_label": "entailment",
                "gold_label": None,
                "review_status": "candidate_requires_teacher_review",
                "reviewer": None,
                "review_notes": "逐字片段正例候选；确认是否构成完整主张蕴含。",
            }
        )
    for row in selected[60:120]:
        clause = _short_clause(row["content"], 52)
        result.append(
            {
                "schema_version": "hybrid-rag-nli-label-v1",
                "pair_id": _stable_id("NLI", "contradiction", row["chunk_id"], clause),
                "pair_type": "explicit_presence_contradiction",
                "premise_source_id": row["chunk_id"],
                "premise_source_type": row["source_type"],
                "premise_title": row["title"],
                "premise_article_ref": row.get("article_ref", ""),
                "premise": row["content"],
                "hypothesis": f"该来源没有出现或规定“{clause}”。",
                "candidate_label": "contradiction",
                "gold_label": None,
                "review_status": "candidate_requires_teacher_review",
                "reviewer": None,
                "review_notes": "显式否认原文存在的反例候选；教师确认措辞和逻辑关系。",
            }
        )
    neutral_sources = _spread(list(reversed(candidates)), 60)
    for premise_row, hypothesis_row in zip(selected[:60], neutral_sources, strict=True):
        clause = _short_clause(hypothesis_row["content"], 72)
        result.append(
            {
                "schema_version": "hybrid-rag-nli-label-v1",
                "pair_id": _stable_id("NLI", "neutral", premise_row["chunk_id"], hypothesis_row["chunk_id"]),
                "pair_type": "cross_document_neutral_candidate",
                "premise_source_id": premise_row["chunk_id"],
                "premise_source_type": premise_row["source_type"],
                "premise_title": premise_row["title"],
                "premise_article_ref": premise_row.get("article_ref", ""),
                "premise": premise_row["content"],
                "hypothesis": clause,
                "candidate_label": "neutral",
                "gold_label": None,
                "review_status": "candidate_requires_teacher_review",
                "reviewer": None,
                "review_notes": f"跨来源中性候选，另一来源为“{hypothesis_row['title']}”；教师需排除潜在蕴含或冲突。",
            }
        )
    if len(result) != 180 or len({row["pair_id"] for row in result}) != 180:
        raise ValueError("NLI quota or identifier uniqueness failed")
    return result


def build_eval_templates(corpus_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    legal_chunks = _read_jsonl(corpus_dir / "legal_chunks.jsonl")
    case_parents = _read_jsonl(corpus_dir / "case_parents.jsonl")
    textbook_chunks = _read_jsonl(corpus_dir / "textbook_chunks.jsonl")
    question_public = _read_jsonl(corpus_dir / "question_public.jsonl")
    return (
        build_qrels(
            legal_chunks=legal_chunks,
            case_parents=case_parents,
            textbook_chunks=textbook_chunks,
            question_public=question_public,
        ),
        build_nli_pairs(legal_chunks),
    )


__all__ = ["build_eval_templates", "build_nli_pairs", "build_qrels"]
