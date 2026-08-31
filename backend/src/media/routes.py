from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from src.core.models import User
from .service import (
    MAX_ASSET_BYTES,
    MediaConflictError,
    MediaNotFoundError,
    MediaService,
    MediaValidationError,
)


JOB_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$"


class TranscriptionBody(BaseModel):
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    asset_id: str = Field(min_length=1, max_length=96)
    language: str = Field(default="zh_cn", min_length=2, max_length=32)
    hotwords: list[str] = Field(default_factory=list, max_length=100)
    provider: str = Field(default="auto", min_length=1, max_length=64)


class VisualAnalysisBody(BaseModel):
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    asset_id: str = Field(min_length=1, max_length=96)
    task: Literal["ocr", "argument_map_seed", "case_material_summary"] = "ocr"
    provider: str = Field(default="auto", min_length=1, max_length=64)


class SpeechSynthesisBody(BaseModel):
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    text: str = Field(min_length=1, max_length=2000)
    voice: str = Field(default="standard_zh", min_length=1, max_length=128)
    audio_format: Literal["mp3", "wav", "opus"] = "mp3"
    provider: str = Field(default="auto", min_length=1, max_length=64)
    ai_generated_disclosure: bool = True

    @model_validator(mode="after")
    def validate_disclosure(self):
        if not self.ai_generated_disclosure:
            raise ValueError("synthetic speech must keep an AI-generated disclosure")
        return self


class AvatarRenderBody(BaseModel):
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    script: str = Field(min_length=1, max_length=2000)
    avatar_id: str = Field(default="standard_presenter", min_length=1, max_length=128)
    voice: str = Field(default="standard_zh", min_length=1, max_length=128)
    provider: str = Field(default="auto", min_length=1, max_length=64)
    ai_generated_disclosure: bool = True
    likeness_consent_confirmed: bool = False

    @model_validator(mode="after")
    def validate_safety(self):
        if not self.ai_generated_disclosure:
            raise ValueError("avatar output must keep an AI-generated disclosure")
        if self.avatar_id != "standard_presenter" and not self.likeness_consent_confirmed:
            raise ValueError("custom avatar requires confirmed likeness consent")
        return self


def create_media_router(
    *,
    current_user_dependency: Callable[..., User],
    session_dependency: Callable[..., Any],
    storage_root_provider: Callable[[Session, User], Path],
    service: MediaService | None = None,
) -> APIRouter:
    router = APIRouter(tags=["multimodal-media"])
    runtime = service or MediaService()

    def call(action):
        try:
            return action()
        except MediaNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except MediaConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except MediaValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def mutate(session: Session, action):
        result = call(action)
        # FastAPI yield-dependency cleanup may run after the response body is
        # ready. Commit before returning so an immediate follow-up request can
        # resolve the newly created asset/job deterministically.
        session.commit()
        return result

    @router.get("/api/media/capabilities")
    async def capabilities(current_user: User = Depends(current_user_dependency)):
        _ = current_user
        return runtime.capabilities()

    @router.post("/api/multimodal/assets")
    async def upload_asset(
        purpose: Literal["transcription", "visual_context", "avatar_source"] = Form(...),
        file: UploadFile = File(...),
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        data = await file.read(MAX_ASSET_BYTES + 1)
        return mutate(
            session,
            lambda: runtime.create_asset(
                session=session,
                user=current_user,
                storage_root=storage_root_provider(session, current_user),
                purpose=purpose,
                filename=file.filename or "upload",
                content_type=file.content_type or "application/octet-stream",
                data=data,
            )
        )

    @router.get("/api/multimodal/assets/{asset_id}")
    async def asset(
        asset_id: str,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(lambda: runtime.get_asset(session=session, user=current_user, asset_id=asset_id))

    @router.get("/api/multimodal/assets/{asset_id}/content")
    async def asset_content(
        asset_id: str,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        path, content_type, filename = call(
            lambda: runtime.get_asset_content(
                session=session,
                user=current_user,
                storage_root=storage_root_provider(session, current_user),
                asset_id=asset_id,
            )
        )
        return FileResponse(path, media_type=content_type, filename=filename)

    @router.post("/api/multimodal/transcriptions")
    async def transcribe(
        body: TranscriptionBody,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        payload = body.model_dump()
        return mutate(
            session,
            lambda: runtime.submit_job(
                session=session,
                user=current_user,
                job_id=body.job_id,
                job_type="transcription",
                asset_id=body.asset_id,
                provider=body.provider,
                request_payload=payload,
                request_summary={
                    "asset_id": body.asset_id,
                    "language": body.language,
                    "hotword_count": len(body.hotwords),
                },
                storage_root=storage_root_provider(session, current_user),
            )
        )

    @router.get("/api/multimodal/transcriptions/{job_id}")
    async def transcription_job(
        job_id: str,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(
            lambda: runtime.get_job(
                session=session, user=current_user, job_id=job_id, expected_type="transcription"
            )
        )

    @router.post("/api/multimodal/visual-analyses")
    async def analyze_visual(
        body: VisualAnalysisBody,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        payload = body.model_dump()
        return mutate(
            session,
            lambda: runtime.submit_job(
                session=session,
                user=current_user,
                job_id=body.job_id,
                job_type="visual_analysis",
                asset_id=body.asset_id,
                provider=body.provider,
                request_payload=payload,
                request_summary={"asset_id": body.asset_id, "task": body.task},
            )
        )

    @router.get("/api/multimodal/visual-analyses/{job_id}")
    async def visual_job(
        job_id: str,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(
            lambda: runtime.get_job(
                session=session,
                user=current_user,
                job_id=job_id,
                expected_type="visual_analysis",
            )
        )

    @router.post("/api/speech/synthesis")
    async def synthesize_speech(
        body: SpeechSynthesisBody,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        payload = body.model_dump()
        return mutate(
            session,
            lambda: runtime.submit_job(
                session=session,
                user=current_user,
                job_id=body.job_id,
                job_type="speech_synthesis",
                provider=body.provider,
                request_payload=payload,
                request_summary={
                    "text_sha256": _text_sha256(body.text),
                    "text_length": len(body.text),
                    "voice": body.voice,
                    "audio_format": body.audio_format,
                    "ai_generated_disclosure": True,
                },
                storage_root=storage_root_provider(session, current_user),
            )
        )

    @router.get("/api/speech/jobs/{job_id}")
    async def speech_job(
        job_id: str,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(
            lambda: runtime.get_job(
                session=session,
                user=current_user,
                job_id=job_id,
                expected_type="speech_synthesis",
            )
        )

    @router.post("/api/avatar/renders")
    async def render_avatar(
        body: AvatarRenderBody,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        payload = body.model_dump()
        return mutate(
            session,
            lambda: runtime.submit_job(
                session=session,
                user=current_user,
                job_id=body.job_id,
                job_type="avatar_render",
                provider=body.provider,
                request_payload=payload,
                request_summary={
                    "script_sha256": _text_sha256(body.script),
                    "script_length": len(body.script),
                    "avatar_id": body.avatar_id,
                    "voice": body.voice,
                    "ai_generated_disclosure": True,
                    "likeness_consent_confirmed": body.likeness_consent_confirmed,
                },
            )
        )

    @router.get("/api/avatar/renders/{job_id}")
    async def avatar_job(
        job_id: str,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(
            lambda: runtime.get_job(
                session=session,
                user=current_user,
                job_id=job_id,
                expected_type="avatar_render",
            )
        )

    @router.get("/api/media/jobs/{job_id}")
    async def media_job(
        job_id: str,
        current_user: User = Depends(current_user_dependency),
        session: Session = Depends(session_dependency),
    ):
        return call(lambda: runtime.get_job(session=session, user=current_user, job_id=job_id))

    return router


def _text_sha256(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = ["create_media_router"]
