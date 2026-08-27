from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .service import get_knowledge_service


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class KnowledgeSearchBody(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    task_type: str = Field(default="课程检索", max_length=128)
    top_k: int = Field(default=5, ge=1, le=10)
    knowledge_ids: list[str] = Field(default_factory=list, max_length=20)
    key_judgments: list[str] = Field(default_factory=list, max_length=10)


class CitationItem(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    article_ref: str = Field(min_length=1, max_length=64)
    quote: str = Field(default="", max_length=5000)
    claim: str = Field(default="", max_length=5000)


class CitationAuditBody(BaseModel):
    citations: list[CitationItem] = Field(min_length=1, max_length=50)


@router.get("/catalog")
def catalog() -> dict[str, Any]:
    return get_knowledge_service().catalog()


@router.get("/tasks/{task_id}")
def task(task_id: str) -> dict[str, Any]:
    row = get_knowledge_service().get_public_task(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="task item not found")
    return row


@router.post("/search")
def search(body: KnowledgeSearchBody) -> dict[str, Any]:
    try:
        return get_knowledge_service().search(**body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/audit-citations")
def audit_citations(body: CitationAuditBody) -> dict[str, Any]:
    return get_knowledge_service().audit_citations(
        [citation.model_dump() for citation in body.citations]
    )


__all__ = ["router"]
