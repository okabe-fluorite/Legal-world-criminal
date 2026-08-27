from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid_string() -> str:
    return str(uuid4())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_string)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    credential: Mapped["UserCredential | None"] = relationship(back_populates="user", uselist=False)
    sandbox: Mapped["Sandbox | None"] = relationship(back_populates="user", uselist=False)
    human_eval_ratings: Mapped[list["HumanEvalRating"]] = relationship(back_populates="user")
    human_eval_assignments: Mapped[list["HumanEvalAssignment"]] = relationship(back_populates="user")


class UserCredential(Base):
    __tablename__ = "user_credentials"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="credential")


class Sandbox(Base):
    __tablename__ = "sandboxes"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_sandboxes_user_id"),
        UniqueConstraint("sandbox_key", name="uq_sandboxes_sandbox_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_string)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    sandbox_key: Mapped[str] = mapped_column(String(64), nullable=False, default=lambda: uuid4().hex)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    storage_root: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="sandbox")
    runtime_snapshot: Mapped["SandboxRuntimeSnapshot | None"] = relationship(
        back_populates="sandbox",
        uselist=False,
    )


class SandboxRuntimeSnapshot(Base):
    __tablename__ = "sandbox_runtime_snapshots"

    sandbox_id: Mapped[str] = mapped_column(String(36), ForeignKey("sandboxes.id"), primary_key=True)
    simulation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    active_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clients_connected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_checkpoint_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    sandbox: Mapped[Sandbox] = relationship(back_populates="runtime_snapshot")


class HumanEvalRating(Base):
    __tablename__ = "human_eval_ratings"
    __table_args__ = (
        UniqueConstraint("case_id", "rater_id", name="uq_human_eval_case_rater"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_string)
    case_id: Mapped[int] = mapped_column(Integer, nullable=False)
    case_key: Mapped[str] = mapped_column(String(64), nullable=False)
    rater_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="human_eval_ratings")


class HumanEvalAssignment(Base):
    __tablename__ = "human_eval_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "batch_number", name="uq_human_eval_assignment_user_batch"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_string)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    batch_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    case_ids_json: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="human_eval_assignments")


class LearningEventRecord(Base):
    """Immutable, idempotent teaching/adaptive event envelope."""

    __tablename__ = "learning_events"

    event_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_response_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    long_term_profile_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    adaptive_sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    adaptive_sync_error: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    adaptive_response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LearnerProfileRecord(Base):
    """Latest profile snapshot returned by the adaptive service."""

    __tablename__ = "learner_profiles"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="adaptive_service")
    profile_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class RecommendationRecord(Base):
    """Versioned recommendation emitted after a learning event."""

    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("source_event_id", name="uq_recommendations_source_event"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_string)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    source_event_id: Mapped[str | None] = mapped_column(
        String(96), ForeignKey("learning_events.event_id"), nullable=True, index=True
    )
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    recommendation_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
