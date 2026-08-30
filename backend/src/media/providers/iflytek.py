"""Secret-free iFlytek SDK integration catalog.

This module reserves provider/client boundaries learned from the Apache-2.0
``websdk-python`` reference. It intentionally does not vendor that SDK, call a
cloud API, or claim that credentials alone make a provider connected.
"""

from __future__ import annotations

import os
from typing import Any


def _present(*names: str) -> bool:
    return all(bool(str(os.getenv(name, "")).strip()) for name in names)


def build_iflytek_provider_catalog() -> dict[str, Any]:
    credentials_present = _present("XFYUN_APP_ID", "XFYUN_API_KEY", "XFYUN_API_SECRET")
    return {
        "provider_family": "iflytek_websdk_python_reference",
        "reference_license": "Apache-2.0",
        "credentials_present": credentials_present,
        "connection_status": "not_connected",
        "adapter_status": "contract_ready_sdk_not_vendored",
        "clients": {
            "speech_to_text": [
                "xfyunsdkspeech.IatClient",
                "xfyunsdkspeech.LfasrClient",
                "xfyunsdkspeech.RtasrClient",
            ],
            "text_to_speech": ["xfyunsdkspeech.TtsClient"],
            "ocr": ["xfyunsdkocr"],
            "auth_transport": ["xfyunsdkcore HMAC and HTTP client"],
        },
        "excluded_from_current_mainline": [
            "face recognition",
            "voice cloning",
            "Spark Agent",
            "full virtual human",
        ],
        "promotion_requirements": [
            "provider adapter implemented and integration-tested",
            "credential and service authorization verified without logging secrets",
            "AI disclosure retained",
            "ASR/OCR output requires rule or teacher gate before LearningEvent",
        ],
    }


__all__ = ["build_iflytek_provider_catalog"]
