from __future__ import annotations

import hashlib
import io
import json
import os
import re
import wave
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from src.core.models import MediaAssetRecord, MediaJobRecord, User
from .providers import (
    IflytekSpeechProvider,
    ProviderUnavailableError,
    build_iflytek_provider_catalog,
)


MAX_ASSET_BYTES = 15 * 1024 * 1024
JOB_STATUSES = (
    "not_connected",
    "queued",
    "running",
    "succeeded",
    "failed",
    "needs_review",
)

PURPOSE_TYPES = {
    "transcription": {
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/mp4",
        "audio/webm",
        "audio/ogg",
    },
    "visual_context": {"image/jpeg", "image/png", "image/webp"},
    "avatar_source": {"image/jpeg", "image/png", "image/webp"},
}

CONTENT_EXTENSIONS = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

JOB_CAPABILITY = {
    "transcription": "speech_to_text",
    "visual_analysis": "vision_understanding",
    "speech_synthesis": "text_to_speech",
    "avatar_render": "digital_human",
}


class MediaNotFoundError(RuntimeError):
    pass


class MediaConflictError(RuntimeError):
    pass


class MediaValidationError(RuntimeError):
    pass


def _canonical_sha256(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalized_content_type(value: str) -> str:
    return str(value or "").split(";", 1)[0].strip().lower()


def _safe_original_name(value: str) -> str:
    name = Path(str(value or "upload")).name
    name = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "_", name).strip("._")
    return name[:200] or "upload"


def _env_present(*names: str) -> bool:
    return all(bool(str(os.getenv(name, "")).strip()) for name in names)


class MediaService:
    """Persist private media metadata and honest provider job states.

    iFlytek IAT/TTS is executed synchronously for short classroom clips. Cloud
    output remains private and cannot create a LearningEvent without review.
    """

    schema_version = "simlaw-media-v1"

    def __init__(self, *, iflytek_provider: IflytekSpeechProvider | None = None) -> None:
        self._iflytek_provider_override = iflytek_provider
        self._verified_capabilities: set[str] = set()

    def _iflytek_provider(self) -> IflytekSpeechProvider | None:
        if self._iflytek_provider_override is not None:
            return self._iflytek_provider_override
        try:
            return IflytekSpeechProvider.from_environment()
        except ProviderUnavailableError:
            return None

    def capabilities(self) -> dict[str, Any]:
        xfyun_credentials = self._iflytek_provider_override is not None or _env_present(
            "XFYUN_APP_ID", "XFYUN_API_KEY", "XFYUN_API_SECRET"
        )
        xfyun_reference = build_iflytek_provider_catalog(
            verified=bool(self._verified_capabilities)
        )
        azure_credentials = _env_present("AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION")
        local_asr_slot = bool(str(os.getenv("SIMLAW_FASTER_WHISPER_MODEL", "")).strip())
        return {
            "schema_version": "simlaw-media-capabilities-v1",
            "provider_reference_catalog": {"iflytek": xfyun_reference},
            "job_statuses": list(JOB_STATUSES),
            "capabilities": [
                {
                    "capability_id": "private_asset_upload",
                    "priority": "P1",
                    "implementation_status": "implemented",
                    "connection_status": "available",
                    "endpoint": "POST /api/multimodal/assets",
                    "modes": ["audio", "image"],
                    "limits": {"max_bytes": MAX_ASSET_BYTES},
                },
                {
                    "capability_id": "speech_to_text",
                    "priority": "P1",
                    "implementation_status": "implemented",
                    "connection_status": (
                        "available"
                        if "speech_to_text" in self._verified_capabilities
                        else "not_connected"
                    ),
                    "endpoint": "POST /api/multimodal/transcriptions",
                    "provider_options": [
                        {
                            "provider_id": "xfyun_streaming_asr",
                            "credentials_present": xfyun_credentials,
                            "adapter_status": "implemented_real_call_required",
                        },
                        {
                            "provider_id": "faster_whisper_local",
                            "model_slot_present": local_asr_slot,
                            "adapter_status": "not_implemented",
                        },
                    ],
                },
                {
                    "capability_id": "vision_understanding",
                    "priority": "P1",
                    "implementation_status": "interface_reserved",
                    "connection_status": "not_connected",
                    "endpoint": "POST /api/multimodal/visual-analyses",
                    "provider_options": [],
                },
                {
                    "capability_id": "text_to_speech",
                    "priority": "P1",
                    "implementation_status": "implemented",
                    "connection_status": (
                        "available"
                        if "text_to_speech" in self._verified_capabilities
                        else "not_connected"
                    ),
                    "endpoint": "POST /api/speech/synthesis",
                    "client_fallback": {
                        "provider_id": "browser_speech_synthesis",
                        "status": "client_capability_check_required",
                        "downloadable_asset": False,
                    },
                    "provider_options": [
                        {
                            "provider_id": "xfyun_online_tts",
                            "credentials_present": xfyun_credentials,
                            "adapter_status": "implemented_real_call_required",
                        }
                    ],
                },
                {
                    "capability_id": "digital_human",
                    "priority": "P2",
                    "implementation_status": "interface_reserved",
                    "connection_status": "not_connected",
                    "endpoint": "POST /api/avatar/renders",
                    "provider_options": [
                        {
                            "provider_id": "xfyun_virtual_human",
                            "credentials_present": xfyun_credentials,
                            "authorization_present": _env_present(
                                "XFYUN_AVATAR_ID", "XFYUN_AVATAR_VCN"
                            ),
                            "adapter_status": "not_implemented",
                        },
                        {
                            "provider_id": "azure_speech_avatar",
                            "credentials_present": azure_credentials,
                            "adapter_status": "not_implemented",
                        },
                    ],
                },
            ],
            "evidence_boundary": {
                "learning_event_created": False,
                "long_term_profile_eligible": False,
                "formal_grading_eligible": False,
                "promotion_rule": "rule_or_teacher_review_required",
            },
            "privacy": {
                "assets": "private_user_sandbox",
                "absolute_paths_returned": False,
                "provider_keys_returned": False,
                "raw_media_committed_to_git": False,
            },
        }

    def create_asset(
        self,
        *,
        session: Session,
        user: User,
        storage_root: Path,
        purpose: str,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> dict[str, Any]:
        normalized_purpose = str(purpose or "").strip().lower()
        normalized_type = _normalized_content_type(content_type)
        if normalized_purpose not in PURPOSE_TYPES:
            raise MediaValidationError("unsupported media purpose")
        if normalized_type not in PURPOSE_TYPES[normalized_purpose]:
            raise MediaValidationError("content type is not allowed for this purpose")
        if not data:
            raise MediaValidationError("media asset is empty")
        if len(data) > MAX_ASSET_BYTES:
            raise MediaValidationError(f"media asset exceeds {MAX_ASSET_BYTES} bytes")

        asset_id = f"asset_{uuid4().hex}"
        extension = CONTENT_EXTENSIONS[normalized_type]
        storage_key = PurePosixPath("media", "assets", f"{asset_id}{extension}").as_posix()
        root = Path(storage_root).resolve()
        target = (root / Path(storage_key)).resolve()
        if not target.is_relative_to(root):
            raise MediaValidationError("invalid media storage path")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

        row = MediaAssetRecord(
            asset_id=asset_id,
            user_id=str(user.id),
            purpose=normalized_purpose,
            media_type=normalized_type.split("/", 1)[0],
            content_type=normalized_type,
            original_name=_safe_original_name(filename),
            size_bytes=len(data),
            content_sha256=hashlib.sha256(data).hexdigest(),
            storage_key=storage_key,
            status="active",
        )
        session.add(row)
        session.flush()
        return self._serialize_asset(row)

    def get_asset(self, *, session: Session, user: User, asset_id: str) -> dict[str, Any]:
        row = session.get(MediaAssetRecord, str(asset_id))
        if row is None or row.user_id != str(user.id):
            raise MediaNotFoundError("media asset not found")
        return self._serialize_asset(row)

    def get_asset_content(
        self,
        *,
        session: Session,
        user: User,
        storage_root: Path,
        asset_id: str,
    ) -> tuple[Path, str, str]:
        row = session.get(MediaAssetRecord, str(asset_id))
        if row is None or row.user_id != str(user.id):
            raise MediaNotFoundError("media asset not found")
        target = self._asset_path(storage_root=storage_root, storage_key=row.storage_key)
        if not target.is_file():
            raise MediaNotFoundError("media asset content not found")
        return target, row.content_type, row.original_name

    @staticmethod
    def _asset_path(*, storage_root: Path, storage_key: str) -> Path:
        root = Path(storage_root).resolve()
        target = (root / Path(storage_key)).resolve()
        if not target.is_relative_to(root):
            raise MediaValidationError("invalid media storage path")
        return target

    @staticmethod
    def _pcm_to_wav(pcm: bytes, *, sample_rate: int) -> bytes:
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm)
        return output.getvalue()

    @staticmethod
    def _transcription_audio(path: Path, content_type: str) -> tuple[bytes, str, int]:
        data = path.read_bytes()
        if content_type in {"audio/wav", "audio/x-wav"}:
            try:
                with wave.open(io.BytesIO(data), "rb") as wav:
                    if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                        raise MediaValidationError(
                            "iFlytek IAT requires mono 16-bit WAV audio"
                        )
                    sample_rate = wav.getframerate()
                    if sample_rate not in {8000, 16000}:
                        raise MediaValidationError(
                            "iFlytek IAT requires 8kHz or 16kHz WAV audio"
                        )
                    return wav.readframes(wav.getnframes()), "raw", sample_rate
            except wave.Error as exc:
                raise MediaValidationError("invalid WAV audio") from exc
        if content_type in {"audio/mpeg", "audio/mp3"}:
            return data, "lame", 16000
        raise MediaValidationError("iFlytek IAT currently supports WAV or MP3")

    def _store_generated_asset(
        self,
        *,
        session: Session,
        user: User,
        storage_root: Path,
        data: bytes,
        content_type: str,
        filename: str,
    ) -> MediaAssetRecord:
        asset_id = f"asset_{uuid4().hex}"
        extension = CONTENT_EXTENSIONS[content_type]
        storage_key = PurePosixPath(
            "media", "generated", f"{asset_id}{extension}"
        ).as_posix()
        target = self._asset_path(storage_root=storage_root, storage_key=storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        row = MediaAssetRecord(
            asset_id=asset_id,
            user_id=str(user.id),
            purpose="speech_output",
            media_type="audio",
            content_type=content_type,
            original_name=_safe_original_name(filename),
            size_bytes=len(data),
            content_sha256=hashlib.sha256(data).hexdigest(),
            storage_key=storage_key,
            status="active",
        )
        session.add(row)
        session.flush()
        return row

    def submit_job(
        self,
        *,
        session: Session,
        user: User,
        job_id: str,
        job_type: str,
        request_payload: dict[str, Any],
        request_summary: dict[str, Any],
        asset_id: str | None = None,
        provider: str = "auto",
        storage_root: Path | None = None,
    ) -> dict[str, Any]:
        normalized_job_type = str(job_type or "").strip().lower()
        if normalized_job_type not in JOB_CAPABILITY:
            raise MediaValidationError("unsupported media job type")
        normalized_job_id = str(job_id or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}", normalized_job_id):
            raise MediaValidationError("invalid media job id")
        normalized_provider = str(provider or "auto").strip().lower() or "auto"
        if asset_id:
            asset = session.get(MediaAssetRecord, str(asset_id))
            if asset is None or asset.user_id != str(user.id):
                raise MediaNotFoundError("media asset not found")

        payload_sha = _canonical_sha256(
            {
                "job_type": normalized_job_type,
                "asset_id": asset_id or "",
                "provider": normalized_provider,
                "payload": request_payload,
            }
        )
        existing = session.get(MediaJobRecord, normalized_job_id)
        if existing is not None:
            if existing.user_id != str(user.id):
                raise MediaNotFoundError("media job not found")
            if existing.request_sha256 != payload_sha:
                raise MediaConflictError("media job id already exists with a different request")
            result = self._serialize_job(existing)
            result["job_status"] = "duplicate"
            return result

        row = MediaJobRecord(
            job_id=normalized_job_id,
            user_id=str(user.id),
            job_type=normalized_job_type,
            asset_id=str(asset_id) if asset_id else None,
            provider_requested=normalized_provider,
            provider_resolved="none",
            status="not_connected",
            request_sha256=payload_sha,
            request_summary_json=dict(request_summary),
            result_json=None,
            error_code="provider_not_connected",
            error_message=(
                "No verified media provider adapter is connected. "
                "The request was recorded without generating synthetic output."
            ),
        )
        session.add(row)
        session.flush()
        if normalized_job_type in {"transcription", "speech_synthesis"}:
            self._execute_iflytek_job(
                session=session,
                user=user,
                row=row,
                request_payload=request_payload,
                asset=asset if asset_id else None,
                storage_root=storage_root,
            )
        result = self._serialize_job(row)
        result["job_status"] = "inserted"
        return result

    def _execute_iflytek_job(
        self,
        *,
        session: Session,
        user: User,
        row: MediaJobRecord,
        request_payload: dict[str, Any],
        asset: MediaAssetRecord | None,
        storage_root: Path | None,
    ) -> None:
        accepted = {
            "auto",
            "xfyun",
            "iflytek_websocket",
            "xfyun_streaming_asr",
            "xfyun_online_tts",
        }
        if row.provider_requested not in accepted or storage_root is None:
            return
        provider = self._iflytek_provider()
        if provider is None:
            return
        row.provider_resolved = provider.provider_id
        row.status = "running"
        row.error_code = ""
        row.error_message = ""
        try:
            if row.job_type == "speech_synthesis":
                requested_format = str(request_payload.get("audio_format") or "mp3")
                requested_voice = str(request_payload.get("voice") or "standard_zh")
                voice = (
                    str(os.getenv("XFYUN_TTS_VOICE", "xiaoyan"))
                    if requested_voice == "standard_zh"
                    else requested_voice
                )
                response = provider.synthesize(
                    text=str(request_payload.get("text") or ""),
                    voice=voice,
                    audio_format=requested_format,
                )
                audio = response.audio
                content_type = response.content_type
                if requested_format == "wav":
                    audio = self._pcm_to_wav(audio, sample_rate=response.sample_rate)
                generated = self._store_generated_asset(
                    session=session,
                    user=user,
                    storage_root=storage_root,
                    data=audio,
                    content_type=content_type,
                    filename=f"{row.job_id}.{CONTENT_EXTENSIONS[content_type].lstrip('.')}",
                )
                row.asset_id = generated.asset_id
                row.status = "succeeded"
                row.result_json = {
                    "output_asset_id": generated.asset_id,
                    "content_type": generated.content_type,
                    "size_bytes": generated.size_bytes,
                    "content_sha256": generated.content_sha256,
                    "content_url": f"/api/multimodal/assets/{generated.asset_id}/content",
                    "provider_sid": response.provider_sid,
                    "ai_generated_disclosure": True,
                }
                self._verified_capabilities.add("text_to_speech")
            else:
                if asset is None:
                    raise MediaValidationError("transcription requires an audio asset")
                source = self._asset_path(
                    storage_root=storage_root, storage_key=asset.storage_key
                )
                audio, encoding, sample_rate = self._transcription_audio(
                    source, asset.content_type
                )
                response = provider.transcribe(
                    audio=audio,
                    language=str(request_payload.get("language") or "zh_cn"),
                    encoding=encoding,
                    sample_rate=sample_rate,
                )
                row.status = "needs_review"
                row.result_json = {
                    "transcript": response.transcript,
                    "transcript_sha256": hashlib.sha256(
                        response.transcript.encode("utf-8")
                    ).hexdigest(),
                    "segments": list(response.segments),
                    "provider_sid": response.provider_sid,
                    "human_review_required": True,
                }
                self._verified_capabilities.add("speech_to_text")
        except MediaValidationError:
            raise
        except ProviderUnavailableError as exc:
            error_code = str(exc).split(":", 1)[0]
            row.status = "failed"
            row.error_code = error_code
            row.error_message = "iFlytek request failed without exposing credentials"
        session.flush()

    def get_job(
        self,
        *,
        session: Session,
        user: User,
        job_id: str,
        expected_type: str | None = None,
    ) -> dict[str, Any]:
        row = session.get(MediaJobRecord, str(job_id))
        if row is None or row.user_id != str(user.id):
            raise MediaNotFoundError("media job not found")
        if expected_type and row.job_type != expected_type:
            raise MediaNotFoundError("media job not found")
        return self._serialize_job(row)

    @staticmethod
    def _serialize_asset(row: MediaAssetRecord) -> dict[str, Any]:
        return {
            "schema_version": "simlaw-media-asset-v1",
            "asset_id": row.asset_id,
            "purpose": row.purpose,
            "media_type": row.media_type,
            "content_type": row.content_type,
            "original_name": row.original_name,
            "size_bytes": row.size_bytes,
            "content_sha256": row.content_sha256,
            "storage_scope": "private_user_sandbox",
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _serialize_job(row: MediaJobRecord) -> dict[str, Any]:
        return {
            "schema_version": "simlaw-media-job-v1",
            "job_id": row.job_id,
            "job_type": row.job_type,
            "asset_id": row.asset_id,
            "provider_requested": row.provider_requested,
            "provider_resolved": row.provider_resolved,
            "status": row.status,
            "request_summary": dict(row.request_summary_json or {}),
            "result": row.result_json,
            "error": (
                {"code": row.error_code, "message": row.error_message}
                if row.error_code
                else None
            ),
            "evidence_eligibility": {
                "learning_event_created": False,
                "long_term_profile": False,
                "formal_grading": False,
                "reason": "media_interaction_requires_rule_or_teacher_review",
            },
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }


__all__ = [
    "JOB_STATUSES",
    "MAX_ASSET_BYTES",
    "MediaConflictError",
    "MediaNotFoundError",
    "MediaService",
    "MediaValidationError",
]
