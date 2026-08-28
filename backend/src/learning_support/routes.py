from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.models import User

from .service import (
    LearningSupportConflictError,
    LearningSupportNotFoundError,
    LearningSupportPermissionError,
    LearningSupportService,
)


class SessionCreateBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    knowledge_id: str = Field(default="", max_length=128)
    task_id: str = Field(default="", max_length=128)
    phase: Literal["prestudy", "review"]
    confusion_type: Literal[
        "concept_boundary", "rule_understanding", "fact_application", "evidence_use", "other"
    ]
    confusion_note: str = Field(min_length=1, max_length=2000)


class SessionResponseBody(BaseModel):
    student_response: str = Field(min_length=1, max_length=5000)


def create_learning_support_router(
    *,
    current_user_dependency: Callable[..., User],
    session_dependency: Callable[..., Any],
    service: LearningSupportService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/learning-support", tags=["learning-support"])
    runtime = service or LearningSupportService()

    def call(action):
        try:
            return action()
        except LearningSupportNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except LearningSupportPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LearningSupportConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/sessions")
    async def create_session(
        body: SessionCreateBody,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(
            lambda: runtime.create_session(
                session=session,
                user=current_user,
                **body.model_dump(),
            )
        )

    @router.get("/sessions/{session_id}")
    async def get_session(
        session_id: str,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(
            lambda: runtime.get_session(
                session=session, user=current_user, session_id=session_id
            )
        )

    @router.post("/sessions/{session_id}/respond")
    async def respond(
        session_id: str,
        body: SessionResponseBody,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(
            lambda: runtime.respond(
                session=session,
                user=current_user,
                session_id=session_id,
                student_response=body.student_response,
            )
        )

    return router


__all__ = ["create_learning_support_router"]
