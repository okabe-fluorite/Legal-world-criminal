from __future__ import annotations

import os

from sqlalchemy.orm import Session

from .models import User, UserRoleRecord


VALID_USER_ROLES = {"student", "teacher", "admin"}


def _configured_emails(name: str) -> set[str]:
    raw = str(os.environ.get(name) or "")
    return {
        value.strip().lower()
        for value in raw.replace(";", ",").split(",")
        if value.strip()
    }


def resolve_user_role(*, session: Session, user: User) -> str:
    email = str(user.email or "").strip().lower()
    if email and email in _configured_emails("SIMLAW_ADMIN_EMAILS"):
        return "admin"
    if email and email in _configured_emails("SIMLAW_TEACHER_EMAILS"):
        return "teacher"
    record = session.get(UserRoleRecord, str(user.id))
    role = str(record.role if record else "student").strip().lower()
    return role if role in VALID_USER_ROLES else "student"


def grant_user_role(
    *,
    session: Session,
    user: User,
    role: str,
    granted_by: str,
) -> UserRoleRecord:
    normalized = str(role or "").strip().lower()
    if normalized not in VALID_USER_ROLES:
        raise ValueError(f"unsupported user role: {normalized}")
    record = session.get(UserRoleRecord, str(user.id))
    if record is None:
        record = UserRoleRecord(
            user_id=str(user.id),
            role=normalized,
            granted_by=str(granted_by or "system")[:128],
        )
        session.add(record)
    else:
        record.role = normalized
        record.granted_by = str(granted_by or "system")[:128]
    session.flush()
    return record


__all__ = ["VALID_USER_ROLES", "grant_user_role", "resolve_user_role"]
