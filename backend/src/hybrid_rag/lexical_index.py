"""SQLite FTS5 BM25F-style index for Hybrid RAG collections."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Sequence

from .vector_index import IndexRecord


_TOKEN_RUN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


def tokenize_for_fts(value: str) -> str:
    tokens: list[str] = []
    for match in _TOKEN_RUN_RE.finditer(str(value or "").lower()):
        token = match.group(0)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            for size in (2, 3):
                tokens.extend(token[index : index + size] for index in range(max(0, len(token) - size + 1)))
        else:
            tokens.append(token)
    return " ".join(dict.fromkeys(token for token in tokens if token))


def build_lexical_index(records: Sequence[IndexRecord], output_path: Path) -> None:
    if output_path.is_file():
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary)
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute(
            "CREATE VIRTUAL TABLE docs USING fts5("
            "retrieval_id UNINDEXED, doc_index UNINDEXED, title, article_ref, section_title, content)"
        )
        rows = []
        for index, record in enumerate(records):
            metadata = record.metadata
            rows.append(
                (
                    record.retrieval_id,
                    index,
                    tokenize_for_fts(str(metadata.get("title") or metadata.get("subject") or "")),
                    tokenize_for_fts(str(metadata.get("article_ref") or "")),
                    tokenize_for_fts(str(metadata.get("section_title") or metadata.get("chapter_title") or "")),
                    tokenize_for_fts(record.text),
                )
            )
            if len(rows) >= 500:
                connection.executemany("INSERT INTO docs VALUES (?, ?, ?, ?, ?, ?)", rows)
                rows.clear()
        if rows:
            connection.executemany("INSERT INTO docs VALUES (?, ?, ?, ?, ?, ?)", rows)
        connection.commit()
    finally:
        connection.close()
    os.replace(temporary, output_path)


def lexical_search(index_path: Path, query: str, *, limit: int = 50) -> list[tuple[int, float]]:
    terms = tokenize_for_fts(query).split()
    if not terms:
        return []
    expression = " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms[:128])
    connection = sqlite3.connect(f"file:{index_path.as_posix()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT doc_index, bm25(docs, 0.0, 0.0, 3.0, 8.0, 2.0, 1.0) AS rank "
            "FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT ?",
            (expression, max(1, int(limit))),
        ).fetchall()
    finally:
        connection.close()
    return [(int(row[0]), float(-row[1])) for row in rows]


__all__ = ["build_lexical_index", "lexical_search", "tokenize_for_fts"]
