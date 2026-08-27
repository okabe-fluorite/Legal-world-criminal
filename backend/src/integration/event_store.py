from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def _payload_hash(event: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            event,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def persist_learning_event(
    event: dict[str, Any],
    *,
    session_factory: sessionmaker | None = None,
) -> dict[str, Any]:
    """Insert an immutable event once; report conflicts without overwriting."""

    if session_factory is None and not str(os.environ.get("DATABASE_URL") or "").strip():
        return {"status": "disabled", "payload_sha256": _payload_hash(event)}

    from src.core.database import create_session_factory, get_db_session
    from src.core.models import LearningEventRecord

    factory = session_factory or create_session_factory()
    event_id = str(event.get("event_id") or "").strip()
    user_id = str(event.get("student_id") or "").strip()
    if not event_id or not user_id:
        raise ValueError("event_id and student_id are required for event persistence")
    digest = _payload_hash(event)
    with get_db_session(factory) as session:
        existing = session.get(LearningEventRecord, event_id)
        if existing is not None:
            return {
                "status": "duplicate" if existing.payload_sha256 == digest else "conflict",
                "payload_sha256": digest,
                "stored_payload_sha256": existing.payload_sha256,
            }
        eligibility = event.get("evidence_eligibility") or {}
        session.add(
            LearningEventRecord(
                event_id=event_id,
                user_id=user_id,
                schema_version=str(event.get("schema_version") or ""),
                event_type=str(event.get("event_type") or "case_stage_assessment"),
                case_id=str(event.get("case_id") or ""),
                stage=str(event.get("stage") or ""),
                task_id=str(event.get("task_id") or ""),
                source_response_sha256=str(event.get("source_response_sha256") or ""),
                payload_sha256=digest,
                long_term_profile_eligible=bool(
                    not isinstance(eligibility, dict)
                    or eligibility.get("long_term_profile") is not False
                ),
                payload_json=event,
            )
        )
    return {"status": "inserted", "payload_sha256": digest}


def update_adaptive_delivery(
    event_id: str,
    result: dict[str, Any],
    *,
    session_factory: sessionmaker | None = None,
) -> None:
    if session_factory is None and not str(os.environ.get("DATABASE_URL") or "").strip():
        return
    from src.core.database import create_session_factory, get_db_session
    from src.core.models import (
        LearnerProfileRecord,
        LearningEventRecord,
        RecommendationRecord,
    )

    factory = session_factory or create_session_factory()
    with get_db_session(factory) as session:
        record = session.get(LearningEventRecord, event_id)
        if record is None:
            return
        record.adaptive_sync_status = str(result.get("status") or "error")
        record.adaptive_sync_error = str(result.get("error") or "")[:1000]
        response = result.get("response")
        record.adaptive_response_json = response if isinstance(response, dict) else None
        if result.get("status") != "sent" or not isinstance(response, dict):
            return

        profile = response.get("profile")
        if isinstance(profile, dict):
            profile_record = session.get(LearnerProfileRecord, record.user_id)
            if profile_record is None:
                profile_record = LearnerProfileRecord(
                    user_id=record.user_id,
                    schema_version=str(
                        profile.get("schema_version") or "edubrain-learner-profile-unknown"
                    )[:64],
                    source="edubrain_adaptive_service",
                    profile_json=profile,
                )
                session.add(profile_record)
            else:
                profile_record.schema_version = str(
                    profile.get("schema_version") or profile_record.schema_version
                )[:64]
                profile_record.source = "edubrain_adaptive_service"
                profile_record.profile_json = profile

        recommendations = response.get("recommendations")
        if isinstance(recommendations, list):
            recommendation_record = session.scalar(
                select(RecommendationRecord).where(
                    RecommendationRecord.source_event_id == record.event_id
                )
            )
            policy_version = str(response.get("policy_version") or "unspecified")[:64]
            if recommendation_record is None:
                session.add(
                    RecommendationRecord(
                        user_id=record.user_id,
                        source_event_id=record.event_id,
                        policy_version=policy_version,
                        status="active",
                        recommendation_json=response,
                    )
                )
            else:
                recommendation_record.policy_version = policy_version
                recommendation_record.status = "active"
                recommendation_record.recommendation_json = response
