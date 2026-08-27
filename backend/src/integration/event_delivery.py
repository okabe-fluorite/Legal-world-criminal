from __future__ import annotations

import logging
from typing import Any

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
