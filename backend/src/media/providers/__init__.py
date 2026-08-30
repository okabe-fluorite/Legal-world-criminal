"""Provider contracts for ASR, TTS, vision and avatar adapters."""

from .base import MediaProvider, MediaProviderResult, ProviderUnavailableError
from .iflytek import build_iflytek_provider_catalog

__all__ = [
    "MediaProvider",
    "MediaProviderResult",
    "ProviderUnavailableError",
    "build_iflytek_provider_catalog",
]
