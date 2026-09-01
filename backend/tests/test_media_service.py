from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from src.core.database import Base, create_database_engine, create_session_factory, get_db_session
from src.core.models import LearningEventRecord, MediaAssetRecord, MediaJobRecord, User
from src.media.routes import create_media_router
from src.media.providers import (
    IflytekAudioResult,
    IflytekTranscriptionResult,
    ProviderUnavailableError,
)
from src.media.service import (
    MediaConflictError,
    MediaNotFoundError,
    MediaService,
    MediaValidationError,
)


class MediaServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = create_database_engine(
            f"sqlite+pysqlite:///{(self.root / 'media.db').as_posix()}"
        )
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)
        with get_db_session(self.factory) as session:
            session.add_all(
                [
                    User(id="media-user-1", email="media-1@example.com"),
                    User(id="media-user-2", email="media-2@example.com"),
                ]
            )
        self.service = MediaService()

    def tearDown(self) -> None:
        self.engine.dispose()
        self.temp.cleanup()

    def _asset(self) -> dict:
        with get_db_session(self.factory) as session:
            user = session.get(User, "media-user-1")
            return self.service.create_asset(
                session=session,
                user=user,
                storage_root=self.root / user.id,
                purpose="transcription",
                filename="../../课堂录音.wav",
                content_type="audio/wav",
                data=b"RIFF" + b"\x00" * 128,
            )

    def test_capabilities_are_secret_free_and_truthful(self) -> None:
        previous = {
            name: os.environ.get(name)
            for name in ("XFYUN_APP_ID", "XFYUN_API_KEY", "XFYUN_API_SECRET")
        }
        try:
            os.environ["XFYUN_APP_ID"] = "secret-app-id"
            os.environ["XFYUN_API_KEY"] = "secret-api-key"
            os.environ["XFYUN_API_SECRET"] = "secret-api-secret"
            payload = self.service.capabilities()
            serialized = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("secret-app-id", serialized)
            self.assertNotIn("secret-api-key", serialized)
            self.assertNotIn("secret-api-secret", serialized)
            rows = {row["capability_id"]: row for row in payload["capabilities"]}
            self.assertEqual(rows["private_asset_upload"]["implementation_status"], "implemented")
            self.assertEqual(rows["speech_to_text"]["connection_status"], "configured_not_verified")
            self.assertEqual(rows["speech_to_text"]["endpoint"], "WS /ws/realtime-voice")
            self.assertIn("realtime_pcm_primary", rows["speech_to_text"]["modes"])
            self.assertEqual(rows["digital_human"]["priority"], "P2")
            self.assertFalse(payload["evidence_boundary"]["learning_event_created"])
            self.service.mark_verified("speech_to_text", "unknown")
            verified_rows = {
                row["capability_id"]: row
                for row in self.service.capabilities()["capabilities"]
            }
            self.assertEqual(verified_rows["speech_to_text"]["connection_status"], "available")
            self.assertEqual(verified_rows["text_to_speech"]["connection_status"], "configured_not_verified")
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_asset_is_private_hashed_and_path_is_not_exposed(self) -> None:
        asset = self._asset()
        self.assertEqual(asset["original_name"], "课堂录音.wav")
        self.assertEqual(asset["storage_scope"], "private_user_sandbox")
        self.assertNotIn(str(self.root), json.dumps(asset, ensure_ascii=False))
        with get_db_session(self.factory) as session:
            row = session.get(MediaAssetRecord, asset["asset_id"])
            self.assertTrue((self.root / "media-user-1" / row.storage_key).is_file())
            other = session.get(User, "media-user-2")
            with self.assertRaises(MediaNotFoundError):
                self.service.get_asset(session=session, user=other, asset_id=asset["asset_id"])

    def test_job_idempotency_and_evidence_isolation(self) -> None:
        asset = self._asset()
        request = {
            "job_id": "transcription-demo-1",
            "asset_id": asset["asset_id"],
            "language": "zh_cn",
            "hotwords": ["罪刑法定"],
            "provider": "auto",
        }
        with get_db_session(self.factory) as session:
            user = session.get(User, "media-user-1")
            inserted = self.service.submit_job(
                session=session,
                user=user,
                job_id=request["job_id"],
                job_type="transcription",
                asset_id=asset["asset_id"],
                provider="auto",
                request_payload=request,
                request_summary={"asset_id": asset["asset_id"], "language": "zh_cn"},
            )
            duplicate = self.service.submit_job(
                session=session,
                user=user,
                job_id=request["job_id"],
                job_type="transcription",
                asset_id=asset["asset_id"],
                provider="auto",
                request_payload=request,
                request_summary={"asset_id": asset["asset_id"], "language": "zh_cn"},
            )
            self.assertEqual(inserted["job_status"], "inserted")
            self.assertEqual(duplicate["job_status"], "duplicate")
            self.assertEqual(inserted["status"], "not_connected")
            self.assertFalse(inserted["evidence_eligibility"]["long_term_profile"])
            with self.assertRaises(MediaConflictError):
                self.service.submit_job(
                    session=session,
                    user=user,
                    job_id=request["job_id"],
                    job_type="transcription",
                    asset_id=asset["asset_id"],
                    provider="auto",
                    request_payload={**request, "language": "en_us"},
                    request_summary={"asset_id": asset["asset_id"], "language": "en_us"},
                )
            other = session.get(User, "media-user-2")
            with self.assertRaises(MediaNotFoundError):
                self.service.get_job(session=session, user=other, job_id=request["job_id"])
        with get_db_session(self.factory) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(MediaJobRecord)), 1)
            self.assertEqual(session.scalar(select(func.count()).select_from(LearningEventRecord)), 0)

    def test_invalid_content_type_is_rejected(self) -> None:
        with get_db_session(self.factory) as session:
            user = session.get(User, "media-user-1")
            with self.assertRaises(MediaValidationError):
                self.service.create_asset(
                    session=session,
                    user=user,
                    storage_root=self.root / user.id,
                    purpose="visual_context",
                    filename="payload.exe",
                    content_type="application/octet-stream",
                    data=b"not-an-image",
                )

    def test_fastapi_contracts_upload_and_return_not_connected(self) -> None:
        def session_dependency():
            with get_db_session(self.factory) as session:
                yield session

        def current_user(
            x_media_user: str = Header(default="media-user-1"),
            session=Depends(session_dependency),
        ) -> User:
            user = session.get(User, x_media_user)
            if user is None:
                raise HTTPException(status_code=401, detail="unknown test user")
            return user

        app = FastAPI()
        app.include_router(
            create_media_router(
                current_user_dependency=current_user,
                session_dependency=session_dependency,
                storage_root_provider=lambda _session, user: self.root / str(user.id),
                service=self.service,
            )
        )
        with patch.dict(
            os.environ,
            {"XFYUN_APP_ID": "", "XFYUN_API_KEY": "", "XFYUN_API_SECRET": ""},
            clear=False,
        ), TestClient(app) as client:
            capabilities = client.get("/api/media/capabilities")
            self.assertEqual(capabilities.status_code, 200)
            upload = client.post(
                "/api/multimodal/assets",
                data={"purpose": "transcription"},
                files={"file": ("lesson.wav", b"RIFF" + b"\x00" * 128, "audio/wav")},
            )
            self.assertEqual(upload.status_code, 200, upload.text)
            asset_id = upload.json()["asset_id"]
            job = client.post(
                "/api/multimodal/transcriptions",
                json={
                    "job_id": "route-transcription-1",
                    "asset_id": asset_id,
                    "language": "zh_cn",
                    "provider": "auto",
                },
            )
            self.assertEqual(job.status_code, 200, job.text)
            self.assertEqual(job.json()["status"], "not_connected")
            self.assertEqual(
                client.get("/api/multimodal/transcriptions/route-transcription-1").status_code,
                200,
            )
            self.assertEqual(
                client.get(
                    f"/api/multimodal/assets/{asset_id}",
                    headers={"X-Media-User": "media-user-2"},
                ).status_code,
                404,
            )
            unsafe_tts = client.post(
                "/api/speech/synthesis",
                json={
                    "job_id": "unsafe-tts",
                    "text": "本段为合成语音。",
                    "ai_generated_disclosure": False,
                },
            )
            self.assertEqual(unsafe_tts.status_code, 422)
            unsafe_avatar = client.post(
                "/api/avatar/renders",
                json={
                    "job_id": "unsafe-avatar",
                    "script": "本段为数字人播报。",
                    "avatar_id": "custom-teacher",
                    "likeness_consent_confirmed": False,
                },
            )
            self.assertEqual(unsafe_avatar.status_code, 422)

    def test_verified_iflytek_tts_and_asr_create_private_outputs_without_learning_event(self) -> None:
        phrase = "罪刑法定原则要求法无明文规定不为罪。"

        class FakeIflytek:
            provider_id = "iflytek_websocket"

            def synthesize(self, *, text: str, voice: str, audio_format: str):
                self.assertions = (text, voice, audio_format)
                return IflytekAudioResult(
                    audio=b"\x00\x00" * 3200,
                    content_type="audio/wav",
                    sample_rate=16000,
                    provider_sid="tts-safe-sid",
                )

            def transcribe(
                self,
                *,
                audio: bytes,
                language: str,
                encoding: str,
                sample_rate: int,
            ):
                if not audio or language != "zh_cn" or encoding != "raw" or sample_rate != 16000:
                    raise AssertionError("unexpected IAT request")
                return IflytekTranscriptionResult(
                    transcript=phrase,
                    provider_sid="iat-safe-sid",
                    segments=({"sn": 0, "text": phrase, "final": True},),
                )

        service = MediaService(iflytek_provider=FakeIflytek())

        def session_dependency():
            with get_db_session(self.factory) as session:
                yield session

        def current_user(
            x_media_user: str = Header(default="media-user-1"),
            session=Depends(session_dependency),
        ) -> User:
            user = session.get(User, x_media_user)
            if user is None:
                raise HTTPException(status_code=401, detail="unknown test user")
            return user

        app = FastAPI()
        app.include_router(
            create_media_router(
                current_user_dependency=current_user,
                session_dependency=session_dependency,
                storage_root_provider=lambda _session, user: self.root / str(user.id),
                service=service,
            )
        )
        with TestClient(app) as client:
            tts = client.post(
                "/api/speech/synthesis",
                json={
                    "job_id": "verified-tts",
                    "text": phrase,
                    "voice": "standard_zh",
                    "audio_format": "wav",
                    "provider": "xfyun_online_tts",
                    "ai_generated_disclosure": True,
                },
            )
            self.assertEqual(tts.status_code, 200, tts.text)
            self.assertEqual(tts.json()["status"], "succeeded")
            asset_id = tts.json()["result"]["output_asset_id"]
            audio = client.get(f"/api/multimodal/assets/{asset_id}/content")
            self.assertEqual(audio.status_code, 200)
            self.assertTrue(audio.content.startswith(b"RIFF"))
            self.assertEqual(
                client.get(
                    f"/api/multimodal/assets/{asset_id}/content",
                    headers={"X-Media-User": "media-user-2"},
                ).status_code,
                404,
            )
            iat = client.post(
                "/api/multimodal/transcriptions",
                json={
                    "job_id": "verified-iat",
                    "asset_id": asset_id,
                    "language": "zh_cn",
                    "provider": "xfyun_streaming_asr",
                },
            )
            self.assertEqual(iat.status_code, 200, iat.text)
            self.assertEqual(iat.json()["status"], "needs_review")
            self.assertEqual(iat.json()["result"]["transcript"], phrase)
            capabilities = {
                row["capability_id"]: row
                for row in client.get("/api/media/capabilities").json()["capabilities"]
            }
            self.assertEqual(capabilities["speech_to_text"]["connection_status"], "available")
            self.assertEqual(capabilities["text_to_speech"]["connection_status"], "available")
        with get_db_session(self.factory) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(MediaJobRecord)), 2)
            self.assertEqual(session.scalar(select(func.count()).select_from(LearningEventRecord)), 0)

    def test_iflytek_failure_is_sanitized(self) -> None:
        class FailingIflytek:
            provider_id = "iflytek_websocket"

            def synthesize(self, **_kwargs):
                raise ProviderUnavailableError("iflytek_tts_failed:SignedUrlWithSecret")

        service = MediaService(iflytek_provider=FailingIflytek())
        with get_db_session(self.factory) as session:
            user = session.get(User, "media-user-1")
            result = service.submit_job(
                session=session,
                user=user,
                job_id="failed-tts",
                job_type="speech_synthesis",
                provider="xfyun_online_tts",
                storage_root=self.root / user.id,
                request_payload={
                    "text": "测试",
                    "voice": "standard_zh",
                    "audio_format": "wav",
                },
                request_summary={"text_sha256": "safe"},
            )
            serialized = json.dumps(result, ensure_ascii=False)
            self.assertEqual(result["status"], "failed")
            self.assertNotIn("SignedUrlWithSecret", serialized)


if __name__ == "__main__":
    unittest.main()
