"""Provider contracts for ASR, TTS, vision and avatar adapters."""

from .base import MediaProvider, MediaProviderResult, ProviderUnavailableError

__all__ = ["MediaProvider", "MediaProviderResult", "ProviderUnavailableError"]
