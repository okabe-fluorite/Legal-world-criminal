"""Runtime model configuration helpers."""

from __future__ import annotations

import os
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from camel.models.base_model import BaseModelBackend


logger = logging.getLogger(__name__)


DEFAULT_RUNTIME_OPENAI_MODEL = "qwen3.5-flash"
_ENABLE_THINKING_MODEL_PREFIXES = ("qwen",)

MODEL_TASKS = (
    "agent",
    "teaching_judge",
    "citation_alignment",
    "response_assist",
    "learning_support",
    "document_assist",
    "closing_summary",
    "eval",
)

_FAILOVER_CIRCUITS: dict[str, float] = {}
_FAILOVER_LOCK = threading.RLock()
_TRANSIENT_MODEL_ERROR_HINTS = (
    "429",
    "rate limit",
    "usage limit",
    "5-hour",
    "5 hour",
    "too many requests",
    "502",
    "503",
    "504",
    "service unavailable",
    "temporarily unavailable",
    "timeout",
    "timed out",
    "connection error",
    "connection reset",
    "server disconnected",
    "error reading from server",
    "eof",
)


@dataclass(frozen=True)
class ModelEndpoint:
    """Resolved OpenAI-compatible endpoint for one product task.

    ``api_key`` is deliberately omitted from :meth:`safe_dict`; callers must
    never serialize the dataclass directly into an API response or log.
    """

    task: str
    provider: str
    model_name: str
    api_base_url: str
    api_key: str
    timeout_seconds: int

    def safe_dict(self) -> dict[str, Any]:
        parsed = urlsplit(self.api_base_url) if self.api_base_url else None
        safe_base = ""
        if parsed and parsed.scheme and parsed.netloc:
            safe_base = f"{parsed.scheme}://{parsed.netloc}"
        return {
            "task": self.task,
            "provider": self.provider,
            "model_name": self.model_name,
            "api_base": safe_base,
            "api_key_configured": bool(self.api_key),
            "timeout_seconds": self.timeout_seconds,
            "configured": bool(self.model_name and self.api_base_url),
        }


def _endpoint_configured(endpoint: ModelEndpoint | None) -> bool:
    return bool(
        endpoint
        and endpoint.model_name
        and endpoint.api_base_url
        and endpoint.api_key
    )


def _endpoint_circuit_key(endpoint: ModelEndpoint) -> str:
    parsed = urlsplit(endpoint.api_base_url)
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else endpoint.api_base_url


def _circuit_is_open(endpoint: ModelEndpoint) -> bool:
    key = _endpoint_circuit_key(endpoint)
    now = time.monotonic()
    with _FAILOVER_LOCK:
        until = _FAILOVER_CIRCUITS.get(key, 0.0)
        if until <= now:
            _FAILOVER_CIRCUITS.pop(key, None)
            return False
        return True


def _open_circuit(endpoint: ModelEndpoint, seconds: int) -> None:
    with _FAILOVER_LOCK:
        _FAILOVER_CIRCUITS[_endpoint_circuit_key(endpoint)] = (
            time.monotonic() + max(1, int(seconds))
        )


def reset_model_failover_circuits() -> None:
    """Clear process-local failover state (tests and explicit operator reset)."""

    with _FAILOVER_LOCK:
        _FAILOVER_CIRCUITS.clear()


def _is_transient_model_error(exc: Exception) -> bool:
    messages: list[str] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    for _ in range(5):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        messages.append(f"{type(current).__name__}: {current}".lower())
        current = current.__cause__ or current.__context__
    combined = "\n".join(messages)
    return any(hint in combined for hint in _TRANSIENT_MODEL_ERROR_HINTS)


class FailoverModelBackend(BaseModelBackend):
    """Prefer one CAMEL backend and fail over only for transient outages.

    The circuit is shared by all wrappers pointing at the same primary host,
    so one 429 does not make every newly activated Agent repeat the primary
    backend's internal retries.
    """

    def __init__(
        self,
        *,
        primary: Any,
        fallback: Any,
        primary_endpoint: ModelEndpoint,
        fallback_endpoint: ModelEndpoint,
        circuit_seconds: int,
    ) -> None:
        super().__init__(
            model_type=primary.model_type,
            model_config_dict=dict(getattr(primary, "model_config_dict", {}) or {}),
            token_counter=primary.token_counter,
            timeout=primary_endpoint.timeout_seconds,
        )
        self.primary = primary
        self.fallback = fallback
        self.primary_endpoint = primary_endpoint
        self.fallback_endpoint = fallback_endpoint
        self.circuit_seconds = max(1, int(circuit_seconds))

    @property
    def token_counter(self) -> Any:
        return self.primary.token_counter

    @property
    def stream(self) -> bool:
        return bool(getattr(self.primary, "stream", False))

    def _fallback_warning(self, exc: Exception | None = None) -> None:
        logger.warning(
            "Model primary unavailable; using configured fallback: "
            "task=%s primary_host=%s fallback_host=%s reason=%s",
            self.primary_endpoint.task,
            self.primary_endpoint.safe_dict()["api_base"],
            self.fallback_endpoint.safe_dict()["api_base"],
            type(exc).__name__ if exc is not None else "circuit_open",
        )

    def _run(self, messages: list[Any], response_format: Any = None, tools: Any = None) -> Any:
        if _circuit_is_open(self.primary_endpoint):
            self._fallback_warning()
            return self.fallback.run(messages, response_format=response_format, tools=tools)
        try:
            return self.primary.run(messages, response_format=response_format, tools=tools)
        except Exception as exc:
            if not _is_transient_model_error(exc):
                raise
            _open_circuit(self.primary_endpoint, self.circuit_seconds)
            self._fallback_warning(exc)
            return self.fallback.run(messages, response_format=response_format, tools=tools)

    async def _arun(
        self, messages: list[Any], response_format: Any = None, tools: Any = None
    ) -> Any:
        if _circuit_is_open(self.primary_endpoint):
            self._fallback_warning()
            return await self.fallback.arun(
                messages, response_format=response_format, tools=tools
            )
        try:
            return await self.primary.arun(
                messages, response_format=response_format, tools=tools
            )
        except Exception as exc:
            if not _is_transient_model_error(exc):
                raise
            _open_circuit(self.primary_endpoint, self.circuit_seconds)
            self._fallback_warning(exc)
            return await self.fallback.arun(
                messages, response_format=response_format, tools=tools
            )


def _normalize_model_name(value: Any) -> str:
    return str(value or "").strip()


def _normalize_task(task: Any) -> str:
    normalized = _normalize_model_name(task).lower().replace("-", "_")
    if normalized not in MODEL_TASKS:
        raise ValueError(f"unknown model task: {task!r}; expected one of {MODEL_TASKS}")
    return normalized


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(_normalize_model_name(os.environ.get(name)))
    except ValueError:
        return default
    return value if value > 0 else default


def _csv_env(name: str) -> set[str]:
    values = set()
    for raw in _normalize_model_name(os.environ.get(name)).split(","):
        value = raw.strip().lower().replace("-", "_")
        if value:
            values.add(value)
    return values


def _task_env_prefix(task: str) -> str:
    return f"SIMLAW_MODEL_{task.upper()}"


def resolve_model_endpoint(
    task: str,
    *,
    explicit_model: Any = None,
    explicit_api_base_url: Any = None,
    explicit_api_key: Any = None,
) -> ModelEndpoint:
    """Resolve a task-specific model endpoint with safe fallback.

    Precedence:

    1. explicit caller values;
    2. ``SIMLAW_MODEL_<TASK>_*`` task override;
    3. fine-tuned small-model endpoint when ``task`` is listed in
       ``SIMLAW_SMALL_MODEL_TASKS`` (or the list contains ``*``);
    4. the existing ``OPENAI_*`` primary endpoint.

    The small endpoint is OpenAI-compatible, so it works with local vLLM,
    SGLang, Ollama gateways, Xinference, or a hosted fine-tuned model without
    changing business code.
    """

    normalized_task = _normalize_task(task)
    prefix = _task_env_prefix(normalized_task)
    task_model = _normalize_model_name(os.environ.get(f"{prefix}_NAME"))
    task_base = _normalize_model_name(os.environ.get(f"{prefix}_API_BASE_URL"))
    task_key = _normalize_model_name(os.environ.get(f"{prefix}_API_KEY"))

    small_tasks = _csv_env("SIMLAW_SMALL_MODEL_TASKS")
    small_enabled = normalized_task in small_tasks or "*" in small_tasks
    small_model = _normalize_model_name(os.environ.get("SIMLAW_SMALL_MODEL_NAME"))
    use_small = small_enabled and bool(small_model)

    primary_model = resolve_openai_chat_model()
    primary_base = _normalize_model_name(os.environ.get("OPENAI_API_BASE_URL"))
    primary_key = _normalize_model_name(os.environ.get("OPENAI_API_KEY"))

    if task_model:
        provider = "task_override"
        model_name = task_model
        api_base_url = task_base or primary_base
        api_key = task_key or primary_key
        timeout = _positive_int_env(f"{prefix}_TIMEOUT_SECONDS", 180)
    elif use_small:
        provider = "fine_tuned_small_model"
        model_name = small_model
        api_base_url = _normalize_model_name(
            os.environ.get("SIMLAW_SMALL_MODEL_API_BASE_URL")
        ) or primary_base
        api_key = _normalize_model_name(
            os.environ.get("SIMLAW_SMALL_MODEL_API_KEY")
        )
        timeout = _positive_int_env("SIMLAW_SMALL_MODEL_TIMEOUT_SECONDS", 180)
    else:
        provider = "primary"
        model_name = primary_model
        api_base_url = primary_base
        api_key = primary_key
        timeout = _positive_int_env("SIMLAW_MODEL_TIMEOUT_SECONDS", 180)

    return ModelEndpoint(
        task=normalized_task,
        provider=provider,
        model_name=_normalize_model_name(explicit_model) or model_name,
        api_base_url=_normalize_model_name(explicit_api_base_url) or api_base_url,
        api_key=_normalize_model_name(explicit_api_key) or api_key,
        timeout_seconds=timeout,
    )


def resolve_fallback_model_endpoint(task: str) -> ModelEndpoint:
    """Resolve the automatic transient-error fallback for one task."""

    normalized_task = _normalize_task(task)
    prefix = _task_env_prefix(normalized_task)
    task_model = _normalize_model_name(os.environ.get(f"{prefix}_FALLBACK_NAME"))
    task_base = _normalize_model_name(
        os.environ.get(f"{prefix}_FALLBACK_API_BASE_URL")
    )
    task_key = _normalize_model_name(os.environ.get(f"{prefix}_FALLBACK_API_KEY"))
    global_model = _normalize_model_name(os.environ.get("SIMLAW_FALLBACK_MODEL_NAME"))
    global_base = _normalize_model_name(
        os.environ.get("SIMLAW_FALLBACK_MODEL_API_BASE_URL")
    )
    global_key = _normalize_model_name(
        os.environ.get("SIMLAW_FALLBACK_MODEL_API_KEY")
    )
    use_task = bool(task_model or task_base or task_key)
    return ModelEndpoint(
        task=normalized_task,
        provider="task_fallback" if use_task else "automatic_fallback",
        model_name=task_model or global_model,
        api_base_url=task_base or global_base,
        api_key=task_key or global_key,
        timeout_seconds=_positive_int_env(
            f"{prefix}_FALLBACK_TIMEOUT_SECONDS" if use_task else "SIMLAW_FALLBACK_MODEL_TIMEOUT_SECONDS",
            180,
        ),
    )


def _create_camel_endpoint_model(
    endpoint: ModelEndpoint,
    *,
    model_platform: Any,
    temperature: float | None,
    max_tokens: int | None,
) -> Any:
    from camel.models import ModelFactory

    kwargs: dict[str, Any] = {
        "model_platform": model_platform,
        "model_type": endpoint.model_name,
        "model_config_dict": build_runtime_openai_chat_config(
            model_name=endpoint.model_name,
            temperature=temperature,
            max_tokens=max_tokens,
        ),
        "timeout": endpoint.timeout_seconds,
    }
    if endpoint.api_key:
        kwargs["api_key"] = endpoint.api_key
    if endpoint.api_base_url:
        kwargs["url"] = endpoint.api_base_url
    return ModelFactory.create(**kwargs)


def build_camel_model(
    task: str,
    *,
    explicit_model: Any = None,
    explicit_api_base_url: Any = None,
    explicit_api_key: Any = None,
    model_platform: Any = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> tuple[Any, ModelEndpoint]:
    """Create a CAMEL model from the unified task router."""

    from camel.types import ModelPlatformType

    endpoint = resolve_model_endpoint(
        task,
        explicit_model=explicit_model,
        explicit_api_base_url=explicit_api_base_url,
        explicit_api_key=explicit_api_key,
    )
    platform = model_platform or ModelPlatformType.OPENAI
    primary = _create_camel_endpoint_model(
        endpoint,
        model_platform=platform,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    fallback_endpoint = resolve_fallback_model_endpoint(endpoint.task)
    if not _endpoint_configured(fallback_endpoint):
        return primary, endpoint
    if (
        fallback_endpoint.model_name == endpoint.model_name
        and fallback_endpoint.api_base_url.rstrip("/") == endpoint.api_base_url.rstrip("/")
    ):
        return primary, endpoint
    fallback = _create_camel_endpoint_model(
        fallback_endpoint,
        model_platform=platform,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (
        FailoverModelBackend(
            primary=primary,
            fallback=fallback,
            primary_endpoint=endpoint,
            fallback_endpoint=fallback_endpoint,
            circuit_seconds=_positive_int_env(
                "SIMLAW_FALLBACK_CIRCUIT_SECONDS", 900
            ),
        ),
        endpoint,
    )


def build_model_catalog() -> dict[str, Any]:
    """Return a secret-free model routing catalog for diagnostics."""

    small_tasks = sorted(_csv_env("SIMLAW_SMALL_MODEL_TASKS"))
    fallback_routes = []
    for task in MODEL_TASKS:
        endpoint = resolve_fallback_model_endpoint(task)
        row = endpoint.safe_dict()
        row["circuit_open"] = (
            _circuit_is_open(resolve_model_endpoint(task))
            if _endpoint_configured(endpoint)
            else False
        )
        fallback_routes.append(row)
    return {
        "schema_version": "simlaw-model-routing-v1",
        "small_model_enabled": bool(
            _normalize_model_name(os.environ.get("SIMLAW_SMALL_MODEL_NAME"))
            and small_tasks
        ),
        "small_model_tasks": small_tasks,
        "routes": [resolve_model_endpoint(task).safe_dict() for task in MODEL_TASKS],
        "failover": {
            "mode": "automatic_transient_errors_only",
            "circuit_seconds": _positive_int_env(
                "SIMLAW_FALLBACK_CIRCUIT_SECONDS", 900
            ),
            "routes": fallback_routes,
        },
    }


def _supports_enable_thinking_toggle(model_name: Any) -> bool:
    """Return whether the model family accepts Qwen-style enable_thinking."""
    normalized = _normalize_model_name(model_name).lower()
    if not normalized:
        return False
    return normalized.startswith(_ENABLE_THINKING_MODEL_PREFIXES)


def resolve_openai_chat_model(
    explicit_model: Any = None,
    *,
    env_var: str = "OPENAI_MODEL_NAME",
    default_model: str = DEFAULT_RUNTIME_OPENAI_MODEL,
) -> str:
    """Resolve the runtime chat model with explicit override precedence.

    Order:
    1. explicit fallback passed by caller
    2. environment variable
    3. repository runtime default
    """
    explicit = _normalize_model_name(explicit_model)
    if explicit:
        return explicit

    env_model = _normalize_model_name(os.environ.get(env_var))
    if env_model:
        return env_model

    return _normalize_model_name(default_model) or DEFAULT_RUNTIME_OPENAI_MODEL


def build_runtime_openai_chat_config(
    *,
    model_name: Any = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Build runtime chat config for OpenAI-compatible backends.

    Only inject provider-specific reasoning toggles for model families that
    are known to accept them. This avoids passing non-standard parameters
    like ``enable_thinking`` to models such as ``gpt-5-mini``.
    """
    config: dict[str, Any] = {}
    if temperature is not None:
        config["temperature"] = temperature
    if max_tokens is not None:
        config["max_tokens"] = max_tokens
    if _supports_enable_thinking_toggle(model_name):
        config["extra_body"] = {"enable_thinking": False}
    return config


# ──────────────────────────────────────────────────────────────────────────
# Per-agent resolvers — agent attr → env → repo default. Used by
# BaseAgent.activate() to wire the ChatAgent.
# ──────────────────────────────────────────────────────────────────────────


def _attr(agent: Any, name: str) -> str:
    return _normalize_model_name(getattr(agent, name, None))


def _resolve_agent_model_type(agent: Any, fallback: Any = None) -> str:
    explicit = _attr(agent, "model_type") or _normalize_model_name(fallback)
    return resolve_openai_chat_model(explicit_model=explicit)


def _resolve_agent_api_base_url(agent: Any) -> str:
    return (
        _attr(agent, "api_base_url")
        or _normalize_model_name(os.environ.get("OPENAI_API_BASE_URL"))
    )


def _resolve_agent_api_key(agent: Any) -> str:
    return (
        _attr(agent, "api_key")
        or _normalize_model_name(os.environ.get("OPENAI_API_KEY"))
    )
