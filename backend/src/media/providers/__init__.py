"""Provider contracts for ASR, TTS, vision and avatar adapters."""

from .base import MediaProvider, MediaProviderResult, ProviderUnavailableError
from .iflytek import (
    IflytekAudioResult,
    IflytekSpeechProvider,
    IflytekTranscriptionResult,
    build_iflytek_provider_catalog,
)

__all__ = [
    "MediaProvider",
    "MediaProviderResult",
    "ProviderUnavailableError",
    "IflytekAudioResult",
    "IflytekSpeechProvider",
    "IflytekTranscriptionResult",
    "build_iflytek_provider_catalog",
]
