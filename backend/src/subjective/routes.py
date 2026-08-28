from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.models import User
from .service import (
    SubjectiveConflictError,
    SubjectiveNotFoundError,
    SubjectivePermissionError,
    SubjectiveTaskService,
)


class AttemptBody(BaseModel):
    attempt_id: str = Field(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    task_id: str = Field(min_length=1, max_length=128)
    task_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    phase: Literal["prestudy", "review"]
    response_text: str = Field(min_length=40, max_length=5000)
    confidence: int | None = Field(default=None, ge=1, le=5)


class ReviewBody(BaseModel):
    review_id: str = Field(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    attempt_id: str = Field(min_length=1, max_length=96)
    decision: Literal["approve", "request_revision", "reject"]
    teacher_score: float | None = Field(default=None, ge=0, le=1)
    knowledge_status: str = Field(default="", max_length=32)
    feedback: str = Field(default="", max_length=3000)
    error_tags: list[str] = Field(default_factory=list, max_length=20)


def create_subjective_router(
    *,
    current_user_dependency: Callable[..., User],
    session_dependency: Callable[..., Any],
    service: SubjectiveTaskService | None = None,
) -> APIRouter:
    router = APIRouter(tags=["subjective-tasks"])
    runtime = service or SubjectiveTaskService()

    def call(action):
        try:
            return action()
        except SubjectiveNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SubjectivePermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except SubjectiveConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/api/subjective-tasks/catalog")
    async def catalog(
        phase: Literal["prestudy", "review"] | None = None,
        current_user: User = Depends(current_user_dependency),
    ):
        _ = current_user
        return runtime.catalog(phase=phase)

    @router.get("/api/subjective-tasks/{task_id}")
    async def task(task_id: str, current_user: User = Depends(current_user_dependency)):
        _ = current_user
        row = runtime.get_public_task(task_id)
        if row is None:
            raise HTTPException(status_code=404, detail="subjective task not found")
        return row

    @router.post("/api/subjective-attempts")
    async def submit_attempt(
        body: AttemptBody,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(lambda: runtime.submit_attempt(session=session, user=current_user, **body.model_dump()))

    @router.get("/api/subjective-attempts/{attempt_id}")
    async def get_attempt(
        attempt_id: str,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(lambda: runtime.get_attempt(session=session, user=current_user, attempt_id=attempt_id))

    @router.get("/api/teacher/subjective-attempts")
    async def teacher_queue(
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(lambda: runtime.teacher_queue(session=session, teacher=current_user))

    @router.post("/api/teacher/subjective-reviews")
    async def teacher_review(
        body: ReviewBody,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(lambda: runtime.review_attempt(session=session, teacher=current_user, **body.model_dump()))

    return router


__all__ = ["create_subjective_router"]
