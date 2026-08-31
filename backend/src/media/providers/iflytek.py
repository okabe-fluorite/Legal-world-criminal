"""iFlytek streaming IAT/TTS adapter with secret-safe failure handling."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from email.utils import formatdate
from typing import Any
from urllib.parse import urlencode, urlsplit

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from .base import ProviderUnavailableError


IAT_URL = "wss://iat-api.xfyun.cn/v2/iat"
TTS_URL = "wss://tts-api.xfyun.cn/v2/tts"


def _present(*names: str) -> bool:
    return all(bool(str(os.getenv(name, "")).strip()) for name in names)


def _signed_url(url: str, api_key: str, api_secret: str) -> str:
    parsed = urlsplit(url)
    date = formatdate(timeval=None, localtime=False, usegmt=True)
    signature_origin = (
        f"host: {parsed.netloc}\n"
        f"date: {date}\n"
        f"GET {parsed.path} HTTP/1.1"
    )
    signature = base64.b64encode(
        hmac.new(
            api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
    ).decode("ascii")
    authorization_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(
        authorization_origin.encode("utf-8")
    ).decode("ascii")
    return f"{url}?{urlencode({'authorization': authorization, 'date': date, 'host': parsed.netloc})}"


def _provider_error(operation: str, exc: BaseException) -> ProviderUnavailableError:
    # WebSocket exceptions may embed the signed URL. Never propagate their text.
    return ProviderUnavailableError(
        f"iflytek_{operation}_failed:{type(exc).__name__}"
    )


@dataclass(frozen=True)
class IflytekAudioResult:
    audio: bytes
    content_type: str
    sample_rate: int
    provider_sid: str


@dataclass(frozen=True)
class IflytekTranscriptionResult:
    transcript: str
    provider_sid: str
    segments: tuple[dict[str, Any], ...]


class IflytekSpeechProvider:
    provider_id = "iflytek_websocket"

    def __init__(
        self,
        *,
        app_id: str,
        api_key: str,
        api_secret: str,
        iat_url: str = IAT_URL,
        tts_url: str = TTS_URL,
        open_timeout: float = 15.0,
        receive_timeout: float = 30.0,
    ) -> None:
        if not all(value.strip() for value in (app_id, api_key, api_secret)):
            raise ProviderUnavailableError("iflytek_credentials_missing")
        self.app_id = app_id.strip()
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip()
        self.iat_url = iat_url
        self.tts_url = tts_url
        self.open_timeout = open_timeout
        self.receive_timeout = receive_timeout

    @classmethod
    def from_environment(cls) -> "IflytekSpeechProvider":
        return cls(
            app_id=str(os.getenv("XFYUN_APP_ID", "")),
            api_key=str(os.getenv("XFYUN_API_KEY", "")),
            api_secret=str(os.getenv("XFYUN_API_SECRET", "")),
            iat_url=str(os.getenv("XFYUN_IAT_URL", IAT_URL)),
            tts_url=str(os.getenv("XFYUN_TTS_URL", TTS_URL)),
        )

    def synthesize(
        self,
        *,
        text: str,
        voice: str = "xiaoyan",
        audio_format: str = "wav",
    ) -> IflytekAudioResult:
        normalized_format = audio_format.strip().lower()
        if normalized_format not in {"wav", "mp3"}:
            raise ProviderUnavailableError("iflytek_tts_format_unsupported")
        aue = "raw" if normalized_format == "wav" else "lame"
        payload = {
            "common": {"app_id": self.app_id},
            "business": {
                "aue": aue,
                "auf": "audio/L16;rate=16000",
                "vcn": voice,
                "speed": 50,
                "volume": 50,
                "pitch": 50,
                "tte": "UTF8",
            },
            "data": {
                "status": 2,
                "text": base64.b64encode(text.encode("utf-8")).decode("ascii"),
            },
        }
        chunks = bytearray()
        provider_sid = ""
        try:
            with connect(
                _signed_url(self.tts_url, self.api_key, self.api_secret),
                open_timeout=self.open_timeout,
                close_timeout=5,
            ) as websocket:
                websocket.send(json.dumps(payload, ensure_ascii=False))
                while True:
                    message = json.loads(websocket.recv(timeout=self.receive_timeout))
                    code = int(message.get("code") or 0)
                    if code:
                        raise ProviderUnavailableError(f"iflytek_tts_api_error:{code}")
                    provider_sid = str(message.get("sid") or provider_sid)
                    data = dict(message.get("data") or {})
                    encoded = str(data.get("audio") or "")
                    if encoded:
                        chunks.extend(base64.b64decode(encoded))
                    if int(data.get("status", -1)) == 2:
                        break
        except ProviderUnavailableError:
            raise
        except (WebSocketException, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise _provider_error("tts", exc) from None
        if not chunks:
            raise ProviderUnavailableError("iflytek_tts_empty_audio")
        return IflytekAudioResult(
            audio=bytes(chunks),
            content_type="audio/wav" if normalized_format == "wav" else "audio/mpeg",
            sample_rate=16000,
            provider_sid=provider_sid,
        )

    def transcribe(
        self,
        *,
        audio: bytes,
        language: str = "zh_cn",
        encoding: str = "raw",
        sample_rate: int = 16000,
    ) -> IflytekTranscriptionResult:
        if not audio:
            raise ProviderUnavailableError("iflytek_iat_empty_audio")
        if encoding not in {"raw", "lame"}:
            raise ProviderUnavailableError("iflytek_iat_encoding_unsupported")
        segments: dict[int, dict[str, Any]] = {}
        provider_sid = ""
        try:
            with connect(
                _signed_url(self.iat_url, self.api_key, self.api_secret),
                open_timeout=self.open_timeout,
                close_timeout=5,
            ) as websocket:
                frame_size = 1280
                for index in range(0, len(audio), frame_size):
                    frame = audio[index : index + frame_size]
                    status = 0 if index == 0 else 1
                    payload: dict[str, Any] = {
                        "data": {
                            "status": status,
                            "format": f"audio/L16;rate={sample_rate}",
                            "encoding": encoding,
                            "audio": base64.b64encode(frame).decode("ascii"),
                        }
                    }
                    if index == 0:
                        payload["common"] = {"app_id": self.app_id}
                        payload["business"] = {
                            "language": language,
                            "domain": "iat",
                            "accent": "mandarin",
                            "vad_eos": 5000,
                            "ptt": 1,
                        }
                    websocket.send(json.dumps(payload, ensure_ascii=False))
                    time.sleep(0.04)
                websocket.send(json.dumps({"data": {"status": 2}}))
                while True:
                    message = json.loads(websocket.recv(timeout=self.receive_timeout))
                    code = int(message.get("code") or 0)
                    if code:
                        raise ProviderUnavailableError(f"iflytek_iat_api_error:{code}")
                    provider_sid = str(message.get("sid") or provider_sid)
                    data = dict(message.get("data") or {})
                    result = dict(data.get("result") or {})
                    if result:
                        text = "".join(
                            str((word.get("cw") or [{}])[0].get("w") or "")
                            for word in result.get("ws") or []
                        )
                        sn = int(result.get("sn") or len(segments))
                        segments[sn] = {
                            "sn": sn,
                            "text": text,
                            "final": bool(result.get("ls")),
                        }
                    if int(data.get("status", -1)) == 2:
                        break
        except ProviderUnavailableError:
            raise
        except (WebSocketException, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise _provider_error("iat", exc) from None
        ordered = tuple(segments[key] for key in sorted(segments))
        transcript = "".join(str(row["text"]) for row in ordered).strip()
        if not transcript:
            raise ProviderUnavailableError("iflytek_iat_empty_transcript")
        return IflytekTranscriptionResult(
            transcript=transcript,
            provider_sid=provider_sid,
            segments=ordered,
        )


def build_iflytek_provider_catalog(*, verified: bool = False) -> dict[str, Any]:
    credentials_present = _present("XFYUN_APP_ID", "XFYUN_API_KEY", "XFYUN_API_SECRET")
    return {
        "provider_family": "iflytek_websocket_api",
        "reference_license": "Apache-2.0 reference SDK; adapter is project code",
        "credentials_present": credentials_present,
        "connection_status": "available" if credentials_present and verified else "not_connected",
        "adapter_status": "implemented_real_call_required",
        "clients": {
            "speech_to_text": ["streaming_iat_v2"],
            "text_to_speech": ["online_tts_v2"],
            "auth_transport": ["HMAC-SHA256 WebSocket URL signing"],
        },
        "excluded_from_current_mainline": ["full virtual human"],
        "promotion_requirements": [
            "real TTS audio generated",
            "real IAT transcript generated",
            "credential and service authorization verified without logging secrets",
            "AI disclosure retained",
            "ASR output requires rule or teacher gate before LearningEvent",
        ],
    }


__all__ = [
    "IflytekAudioResult",
    "IflytekSpeechProvider",
    "IflytekTranscriptionResult",
    "build_iflytek_provider_catalog",
]
