from __future__ import annotations

import hashlib
import os
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests


def _text(value: Any) -> str:
    return str(value or "").strip()


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(_text(os.environ.get(name)))
    except ValueError:
        return default
    return value if value > 0 else default


def _endpoint(path_env: str, default_path: str) -> str:
    base = _text(os.environ.get("SIMLAW_ADAPTIVE_API_BASE_URL"))
    path = _text(os.environ.get(path_env)) or default_path
    if not base:
        return ""
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def get_adaptive_catalog() -> dict[str, Any]:
    base = _text(os.environ.get("SIMLAW_ADAPTIVE_API_BASE_URL"))
    parsed = urlsplit(base) if base else None
    safe_base = (
        f"{parsed.scheme}://{parsed.netloc}"
        if parsed and parsed.scheme and parsed.netloc
        else ""
    )
    return {
        "schema_version": "simlaw-adaptive-client-v1",
        "enabled": bool(base),
        "api_base": safe_base,
        "api_key_configured": bool(_text(os.environ.get("SIMLAW_ADAPTIVE_API_KEY"))),
        "events_path": _text(os.environ.get("SIMLAW_ADAPTIVE_EVENTS_PATH")) or "/events",
        "recommend_path": _text(os.environ.get("SIMLAW_ADAPTIVE_RECOMMEND_PATH")) or "/recommend",
        "attempts_path": _text(os.environ.get("SIMLAW_ADAPTIVE_ATTEMPTS_PATH")) or "/attempts",
        "confusions_path": _text(os.environ.get("SIMLAW_ADAPTIVE_CONFUSIONS_PATH")) or "/confusions",
        "timeout_seconds": _positive_int("SIMLAW_ADAPTIVE_TIMEOUT_SECONDS", 15),
    }


def _legacy_knowledge_id(name: str) -> str:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    return f"unmapped:{digest}"


def build_adaptive_event(event: dict[str, Any]) -> dict[str, Any]:
    """Convert a LegalWorld event to the shared adaptive event envelope.

    Knowledge labels without a teacher-approved ID are explicitly marked
    ``unmapped`` instead of silently pretending that free-form LLM text is a
    Q-matrix key.
    """

    verdicts = []
    for item in event.get("knowledge_verdicts") or []:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("knowledge_name") or item.get("kp"))
        knowledge_id = _text(item.get("knowledge_id"))
        if not name and not knowledge_id:
            continue
        verdicts.append(
            {
                "knowledge_id": knowledge_id or _legacy_knowledge_id(name),
                "knowledge_name": name,
                "normalization_status": "canonical" if knowledge_id else "unmapped",
                "status": _text(item.get("status")) or "partial",
                "reason": _text(item.get("reason")),
            }
        )

    capability_scores = {}
    for code, item in (event.get("capability_scores") or {}).items():
        if not isinstance(item, dict):
            continue
        capability_scores[str(code)] = {
            "score": item.get("score"),
            "weight": item.get("weight"),
            "source": _text(item.get("source")) or "judge",
            "unverified": bool(item.get("unverified")),
        }

    return {
        "schema_version": "edubrain-learning-event-v2",
        "event_id": _text(event.get("event_id")),
        "event_type": _text(event.get("event_type")) or "case_stage_assessment",
        "student_pseudonym": _text(event.get("student_id")),
        "course_id": _text(event.get("course_id")) or "undergraduate-criminal-law",
        "task_id": _text(event.get("task_id")),
        "case_id": _text(event.get("case_id")),
        "stage": _text(event.get("stage")),
        "source_response_sha256": _text(event.get("source_response_sha256")),
        "capability_scores": capability_scores,
        "knowledge_evidence": verdicts,
        "error_tags": [str(value) for value in (event.get("error_tags") or [])],
        "assist": event.get("assist") or {},
        "evidence_eligibility": event.get("evidence_eligibility") or {},
        "law_citations": event.get("law_citations") or [],
        "scored_at": _text(event.get("scored_at")),
        "source_schema_version": _text(event.get("schema_version")),
    }


def publish_learning_event(
    event: dict[str, Any],
    *,
    post: Any = requests.post,
) -> dict[str, Any]:
    url = _endpoint("SIMLAW_ADAPTIVE_EVENTS_PATH", "/events")
    if not url:
        return {"status": "disabled", "response": None, "error": ""}

    headers = {"Content-Type": "application/json"}
    api_key = _text(os.environ.get("SIMLAW_ADAPTIVE_API_KEY"))
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        response = post(
            url,
            json=build_adaptive_event(event),
            headers=headers,
            timeout=_positive_int("SIMLAW_ADAPTIVE_TIMEOUT_SECONDS", 15),
        )
        response.raise_for_status()
        payload = response.json() if response.content else {}
        return {
            "status": "sent",
            "response": payload if isinstance(payload, dict) else {"data": payload},
            "error": "",
        }
    except Exception as exc:
        return {
            "status": "error",
            "response": None,
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
        }


def request_recommendations(
    student_id: str,
    *,
    context: dict[str, Any] | None = None,
    post: Any = requests.post,
) -> dict[str, Any]:
    url = _endpoint("SIMLAW_ADAPTIVE_RECOMMEND_PATH", "/recommend")
    if not url:
        return {"status": "disabled", "response": None, "error": ""}
    headers = {"Content-Type": "application/json"}
    api_key = _text(os.environ.get("SIMLAW_ADAPTIVE_API_KEY"))
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "schema_version": "edubrain-recommend-request-v1",
        "student_pseudonym": _text(student_id),
        "course_id": "undergraduate-criminal-law",
        "context": dict(context or {}),
    }
    try:
        response = post(
            url,
            json=payload,
            headers=headers,
            timeout=_positive_int("SIMLAW_ADAPTIVE_TIMEOUT_SECONDS", 15),
        )
        response.raise_for_status()
        body = response.json() if response.content else {}
        return {
            "status": "sent",
            "response": body if isinstance(body, dict) else {"data": body},
            "error": "",
        }
    except Exception as exc:
        return {
            "status": "error",
            "response": None,
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
        }


def _submit_student_payload(
    *,
    path_env: str,
    default_path: str,
    student_id: str,
    payload: dict[str, Any],
    post: Any,
) -> dict[str, Any]:
    url = _endpoint(path_env, default_path)
    if not url:
        return {"status": "disabled", "response": None, "error": ""}
    headers = {"Content-Type": "application/json"}
    api_key = _text(os.environ.get("SIMLAW_ADAPTIVE_API_KEY"))
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = dict(payload or {})
    # Authenticated backend identity is authoritative. Never trust a browser
    # supplied pseudonym or allow one student to submit evidence for another.
    body["student_pseudonym"] = _text(student_id)
    body.setdefault("course_id", "undergraduate-criminal-law")
    try:
        response = post(
            url,
            json=body,
            headers=headers,
            timeout=_positive_int("SIMLAW_ADAPTIVE_TIMEOUT_SECONDS", 15),
        )
        status_code = int(getattr(response, "status_code", 200) or 200)
        if status_code >= 400:
            try:
                rejected = response.json() if response.content else {}
            except Exception:
                rejected = {}
            return {
                "status": "rejected",
                "upstream_status": status_code,
                "response": rejected if isinstance(rejected, dict) else {"data": rejected},
                "error": "adaptive service rejected the submission",
            }
        response.raise_for_status()
        result = response.json() if response.content else {}
        return {
            "status": "sent",
            "response": result if isinstance(result, dict) else {"data": result},
            "error": "",
        }
    except Exception as exc:
        return {
            "status": "error",
            "response": None,
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
        }


def submit_task_attempt(
    student_id: str,
    payload: dict[str, Any],
    *,
    post: Any = requests.post,
) -> dict[str, Any]:
    return _submit_student_payload(
        path_env="SIMLAW_ADAPTIVE_ATTEMPTS_PATH",
        default_path="/attempts",
        student_id=student_id,
        payload=payload,
        post=post,
    )


def submit_confusion_annotation(
    student_id: str,
    payload: dict[str, Any],
    *,
    post: Any = requests.post,
) -> dict[str, Any]:
    return _submit_student_payload(
        path_env="SIMLAW_ADAPTIVE_CONFUSIONS_PATH",
        default_path="/confusions",
        student_id=student_id,
        payload=payload,
        post=post,
    )
