from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from sqlalchemy.orm import sessionmaker

from .adaptive_client import publish_learning_event
from .event_store import persist_learning_event, update_adaptive_delivery

logger = logging.getLogger(__name__)


def deliver_learning_event(event: dict[str, Any]) -> dict[str, Any]:
    """Persist once, then deliver to the optional adaptive service."""

    try:
        store = persist_learning_event(event)
    except Exception as exc:
        logger.warning("LearningEvent database persistence failed: %s", exc)
        store = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    if store.get("status") in {"conflict", "error"}:
        delivery = {
            "status": "not_sent",
            "response": None,
            "error": f"local event store rejected payload: {store.get('status')}",
        }
    else:
        delivery = publish_learning_event(event)
    try:
        update_adaptive_delivery(str(event.get("event_id") or ""), delivery)
    except Exception as exc:
        logger.warning("LearningEvent delivery status persistence failed: %s", exc)
    return {"store": store, "adaptive": delivery}


def persist_adaptive_submission(
    user_id: str,
    delivery: dict[str, Any],
    *,
    session_factory: sessionmaker | None = None,
) -> dict[str, Any]:
    """Persist a TaskAttempt/confusion event and its derived snapshots.

    Correct answers and rationales may be returned to the student as feedback,
    but are deliberately omitted from the backend's adaptive response snapshot.
    """

    if delivery.get("status") != "sent" or not isinstance(delivery.get("response"), dict):
        return {"status": "not_persisted", "reason": "adaptive_submission_not_sent"}
    response = delivery["response"]
    event = response.get("learning_event")
    if not isinstance(event, dict):
        return {"status": "not_persisted", "reason": "learning_event_missing"}
    returned_user = str(
        event.get("student_pseudonym") or event.get("student_id") or ""
    ).strip()
    if returned_user != str(user_id):
        return {"status": "conflict", "reason": "adaptive_student_identity_mismatch"}

    local_event = deepcopy(event)
    local_event["student_id"] = str(user_id)
    try:
        store = persist_learning_event(local_event, session_factory=session_factory)
    except Exception as exc:
        logger.warning("Adaptive submission event persistence failed: %s", exc)
        return {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}
    if store.get("status") == "conflict":
        return store

    snapshot = {
        key: response[key]
        for key in ("profile", "recommendations", "policy_version")
        if key in response
    }
    try:
        update_adaptive_delivery(
            str(local_event.get("event_id") or ""),
            {"status": "sent", "response": snapshot, "error": ""},
            session_factory=session_factory,
        )
    except Exception as exc:
        logger.warning("Adaptive submission snapshot persistence failed: %s", exc)
        return {**store, "snapshot_status": "error", "snapshot_error": str(exc)[:500]}
    return {**store, "snapshot_status": "stored"}
