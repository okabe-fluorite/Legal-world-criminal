from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.models import User

from .service import (
    TeacherConflictError,
    TeacherObjectNotFoundError,
    TeacherPermissionError,
    TeacherService,
)


class ClassCreateBody(BaseModel):
    course_id: str = Field(default="undergraduate-criminal-law", min_length=1, max_length=128)
    name: str = Field(min_length=2, max_length=128)
    term: str = Field(min_length=2, max_length=64)


class EnrollmentBody(BaseModel):
    student_email: str = Field(min_length=5, max_length=255)


class ContentReviewBody(BaseModel):
    review_id: str = Field(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    object_type: Literal["case_bundle", "knowledge_card", "task_item"]
    object_id: str = Field(min_length=1, max_length=128)
    object_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: Literal["approve", "request_revision", "reject"]
    note: str = Field(default="", max_length=2000)


def create_teacher_router(
    *,
    current_user_dependency: Callable[..., User],
    session_dependency: Callable[..., Any],
    service: TeacherService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/teacher", tags=["teacher"])
    runtime = service or TeacherService()

    def call(action):
        try:
            return action()
        except TeacherPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except TeacherObjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except TeacherConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def mutate(session: Session, action):
        result = call(action)
        # Yield-dependency cleanup may commit after the response becomes
        # visible. Commit mutation endpoints before returning so immediate
        # list/analytics requests cannot race the write transaction.
        session.commit()
        return result

    @router.get("/overview")
    async def overview(
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(lambda: runtime.list_classes(session=session, teacher=current_user))

    @router.post("/classes")
    async def create_class(
        body: ClassCreateBody,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return mutate(
            session,
            lambda: runtime.create_class(
                session=session,
                teacher=current_user,
                course_id=body.course_id,
                name=body.name,
                term=body.term,
            )
        )

    @router.post("/classes/{class_id}/enrollments")
    async def enroll_student(
        class_id: str,
        body: EnrollmentBody,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return mutate(
            session,
            lambda: runtime.enroll_student(
                session=session,
                teacher=current_user,
                class_id=class_id,
                student_email=body.student_email,
            )
        )

    @router.get("/classes/{class_id}/analytics")
    async def class_analytics(
        class_id: str,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(
            lambda: runtime.class_analytics(
                session=session, teacher=current_user, class_id=class_id
            )
        )

    @router.get("/reviews/catalog")
    async def review_catalog(
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(lambda: runtime.review_catalog(session=session, teacher=current_user))

    @router.get("/case-bundles/{case_id}")
    async def teacher_case_bundle(
        case_id: str,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(
            lambda: runtime.teacher_case_bundle(
                session=session, teacher=current_user, case_id=case_id
            )
        )

    @router.post("/reviews")
    async def submit_review(
        body: ContentReviewBody,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return mutate(
            session,
            lambda: runtime.submit_review(
                session=session,
                teacher=current_user,
                **body.model_dump(),
            )
        )

    @router.get("/reviews/audit")
    async def review_audit(
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(lambda: runtime.review_audit(session=session, teacher=current_user))

    return router


__all__ = ["create_teacher_router"]
