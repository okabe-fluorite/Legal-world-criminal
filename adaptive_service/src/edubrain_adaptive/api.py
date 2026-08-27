from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, model_validator

from .service import AdaptiveService
from .store import AdaptiveStore


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("SIMLAW_ADAPTIVE_DATA_DIR") or ROOT / "data").resolve()
DB_PATH = Path(
    os.environ.get("SIMLAW_ADAPTIVE_DB_PATH") or ROOT / "runtime" / "adaptive.db"
).resolve()

app = FastAPI(title="EduBrain Criminal-Law Adaptive Service", version="0.1.0")


class RecommendRequest(BaseModel):
    student_pseudonym: str = Field(min_length=1, max_length=128)
    course_id: str = "undergraduate-criminal-law"
    context: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=10, ge=1, le=30)


class TaskAttemptRequest(BaseModel):
    schema_version: Literal["criminal-law-task-attempt-v1"] = "criminal-law-task-attempt-v1"
    attempt_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    student_pseudonym: str = Field(min_length=1, max_length=128)
    course_id: str = Field(default="undergraduate-criminal-law", min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    content_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    phase: Literal["prestudy", "review"]
    selected_options: list[str] = Field(min_length=1, max_length=10)
    submitted_at: str = Field(min_length=10, max_length=64)
    response_time_ms: int = Field(default=0, ge=0, le=86_400_000)
    confidence: int | None = Field(default=None, ge=1, le=5)
    hint_count: int = Field(default=0, ge=0, le=20)
    answer_revealed_before_submit: bool = False

    @model_validator(mode="after")
    def require_unique_options(self) -> "TaskAttemptRequest":
        normalized = [str(value).strip().upper() for value in self.selected_options]
        if len(normalized) != len(set(normalized)):
            raise ValueError("selected_options must be unique")
        return self


class ConfusionRequest(BaseModel):
    schema_version: Literal["criminal-law-confusion-annotation-v1"] = "criminal-law-confusion-annotation-v1"
    annotation_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    student_pseudonym: str = Field(min_length=1, max_length=128)
    course_id: str = Field(default="undergraduate-criminal-law", min_length=1, max_length=128)
    phase: Literal["prestudy", "review"]
    task_id: str = Field(default="", max_length=128)
    knowledge_id: str = Field(default="", max_length=128)
    confusion_type: Literal[
        "concept_boundary", "rule_understanding", "fact_application", "evidence_use", "other"
    ] = "other"
    note: str = Field(min_length=1, max_length=2000)
    request_help: bool = True
    submitted_at: str = Field(min_length=10, max_length=64)

    @model_validator(mode="after")
    def require_task_or_knowledge(self) -> "ConfusionRequest":
        if not self.task_id.strip() and not self.knowledge_id.strip():
            raise ValueError("task_id or knowledge_id is required")
        return self


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    expected = str(os.environ.get("SIMLAW_ADAPTIVE_API_KEY") or "").strip()
    if not expected:
        return
    provided = str(authorization or "").strip()
    if provided != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid adaptive service credential")


@lru_cache(maxsize=1)
def get_service() -> AdaptiveService:
    return AdaptiveService(data_dir=DATA_DIR, store=AdaptiveStore(DB_PATH))


@app.get("/health")
def health() -> dict[str, Any]:
    service = get_service()
    return {
        "status": "ok",
        "items": len(service.approved),
        "knowledge_points": len(service.nodes),
        "governed_contracts": service.uses_governed_contracts,
        "database": str(DB_PATH),
    }


@app.post("/events", dependencies=[Depends(require_api_key)])
def ingest_event(event: dict[str, Any]) -> dict[str, Any]:
    try:
        return get_service().ingest(event)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/attempts", dependencies=[Depends(require_api_key)])
def submit_attempt(payload: TaskAttemptRequest) -> dict[str, Any]:
    try:
        result = get_service().submit_attempt(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result.get("attempt_status") == "conflict":
        raise HTTPException(status_code=409, detail=result)
    return result


@app.post("/confusions", dependencies=[Depends(require_api_key)])
def annotate_confusion(payload: ConfusionRequest) -> dict[str, Any]:
    try:
        result = get_service().annotate_confusion(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result.get("annotation_status") == "conflict":
        raise HTTPException(status_code=409, detail=result)
    return result


@app.post("/recommend", dependencies=[Depends(require_api_key)])
def recommend(payload: RecommendRequest) -> dict[str, Any]:
    service = get_service()
    return {
        "schema_version": "edubrain-recommendation-response-v1",
        "profile": service.profile(payload.student_pseudonym),
        "recommendations": service.recommendations(
            payload.student_pseudonym,
            limit=payload.limit,
            context=payload.context,
        ),
        "policy_version": "hybrid-case-evidence-cold-start-v1",
    }


@app.get("/profiles/{student_id}", dependencies=[Depends(require_api_key)])
def profile(student_id: str) -> dict[str, Any]:
    return get_service().profile(student_id)
