from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ProviderUnavailableError(RuntimeError):
    """Raised when a selected media provider is not configured or healthy."""


@dataclass(frozen=True)
class MediaProviderResult:
    status: str
    provider_job_id: str = ""
    payload: dict[str, Any] | None = None


class MediaProvider(Protocol):
    """Small contract implemented by future XFYun/local/Azure adapters."""

    provider_id: str
    job_types: frozenset[str]

    def configured(self) -> bool: ...

    def submit(self, *, job_type: str, payload: dict[str, Any]) -> MediaProviderResult: ...

    def poll(self, *, provider_job_id: str) -> MediaProviderResult: ...
