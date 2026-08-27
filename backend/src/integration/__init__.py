"""Cross-module integration adapters."""

from .adaptive_client import (
    build_adaptive_event,
    get_adaptive_catalog,
    publish_learning_event,
    request_recommendations,
    submit_confusion_annotation,
    submit_task_attempt,
)
from .event_delivery import deliver_learning_event, persist_adaptive_submission

__all__ = [
    "build_adaptive_event",
    "deliver_learning_event",
    "get_adaptive_catalog",
    "publish_learning_event",
    "request_recommendations",
    "submit_confusion_annotation",
    "submit_task_attempt",
    "persist_adaptive_submission",
]
