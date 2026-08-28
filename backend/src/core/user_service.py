from __future__ import annotations

import re
import time

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .auth import hash_password, verify_password
from .models import User, UserCredential


class UserAlreadyExistsError(RuntimeError):
    """Raised when registering an email that already exists."""


class InvalidCredentialsError(RuntimeError):
    """Raised when email or password is invalid."""


class InvalidAuthInputError(RuntimeError):
    """Raised when auth payload is structurally invalid."""


class UserNotFoundError(RuntimeError):
    """Raised when a user cannot be found for the provided identity."""


_SQLITE_BEGIN_RETRY_DELAYS = (0.02, 0.05, 0.1, 0.2, 0.4, 0.8, 1.2, 1.6)


def _begin_sqlite_immediate(session: Session) -> None:
    last_error: OperationalError | None = None
    for attempt, delay in enumerate((0.0, *_SQLITE_BEGIN_RETRY_DELAYS)):
        if delay:
            time.sleep(delay)
        try:
            session.execute(text("BEGIN IMMEDIATE"))
            return
        except OperationalError as exc:
            if "database is locked" not in str(exc).lower():
                raise
            last_error = exc
            session.rollback()
            if attempt >= len(_SQLITE_BEGIN_RETRY_DELAYS):
                break
    if last_error is not None:
        raise last_error


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _validate_auth_input(*, email: str, password: str) -> str:
    normalized_email = _normalize_email(email)
    if not normalized_email or not str(password or "").strip():
        raise InvalidAuthInputError("email and password are required")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized_email):
        raise InvalidAuthInputError("email format is invalid")
    if len(str(password)) < 8:
        raise InvalidAuthInputError("password must contain at least 8 characters")
    return normalized_email


def register_user(*, session: Session, email: str, password: str) -> User:
    normalized_email = _validate_auth_input(email=email, password=password)
    # Password hashing is deliberately completed before acquiring a database
    # writer lock. SQLite registrations use BEGIN IMMEDIATE so concurrent
    # classroom logins wait for a short write transaction instead of both
    # upgrading read transactions and failing with SQLITE_BUSY.
    password_digest = hash_password(password)
    bind = session.get_bind()
    if bind.dialect.name == "sqlite" and not session.in_transaction():
        _begin_sqlite_immediate(session)
    existing_user = session.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    if existing_user is not None:
        raise UserAlreadyExistsError("email already exists")

    user = User(email=normalized_email)
    session.add(user)
    session.flush()

    credential = UserCredential(user_id=user.id, password_hash=password_digest)
    session.add(credential)
    session.flush()
    session.refresh(user)
    return user


def authenticate_user(*, session: Session, email: str, password: str) -> User:
    normalized_email = _validate_auth_input(email=email, password=password)
    user = session.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    if user is None:
        raise InvalidCredentialsError("invalid email or password")

    credential = session.execute(
        select(UserCredential).where(UserCredential.user_id == user.id)
    ).scalar_one_or_none()
    if credential is None or not verify_password(password, credential.password_hash):
        raise InvalidCredentialsError("invalid email or password")
    return user


def get_user_by_id(*, session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise UserNotFoundError("user not found")
    return user


def ensure_user_with_password(*, session: Session, email: str, password: str) -> User:
    """Ensure a user exists with the provided credentials (idempotent)."""
    normalized_email = _validate_auth_input(email=email, password=password)
    user = session.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    if user is None:
        return register_user(session=session, email=normalized_email, password=password)

    credential = session.execute(
        select(UserCredential).where(UserCredential.user_id == user.id)
    ).scalar_one_or_none()
    if credential is None:
        credential = UserCredential(user_id=user.id, password_hash=hash_password(password))
        session.add(credential)
    else:
        credential.password_hash = hash_password(password)
    session.flush()
    session.refresh(user)
    return user
