from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

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
