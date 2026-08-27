from __future__ import annotations

import os
import unittest

from src.core.auth import AuthError, get_jwt_secret
from src.core.database import Base, create_database_engine, create_session_factory, get_db_session
from src.core.models import HumanEvalRating, User
from src.core.user_service import InvalidAuthInputError, register_user
from src.human_eval.service import HumanEvalService
from ws_server import _extract_websocket_token, _require_debug_ui


class SecurityTests(unittest.TestCase):
    def test_short_jwt_secret_is_rejected(self) -> None:
        old = os.environ.get("JWT_SECRET")
        try:
            os.environ["JWT_SECRET"] = "too-short"
            with self.assertRaises(AuthError):
                get_jwt_secret()
        finally:
            if old is None:
                os.environ.pop("JWT_SECRET", None)
            else:
                os.environ["JWT_SECRET"] = old

    def test_registration_requires_email_shape_and_password_length(self) -> None:
        engine = create_database_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with get_db_session(factory) as session:
            with self.assertRaises(InvalidAuthInputError):
                register_user(session=session, email="not-an-email", password="long-enough")
            with self.assertRaises(InvalidAuthInputError):
                register_user(session=session, email="user@example.com", password="short")

    def test_human_eval_export_is_user_scoped(self) -> None:
        engine = create_database_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with get_db_session(factory) as session:
            user_a = User(id="user-a", email="a@example.com")
            user_b = User(id="user-b", email="b@example.com")
            session.add_all([user_a, user_b])
            session.flush()
            session.add_all(
                [
                    HumanEvalRating(
                        case_id=1,
                        case_key="case_1",
                        rater_id="rater-a",
                        user_id=user_a.id,
                        status="draft",
                        payload_json={},
                    ),
                    HumanEvalRating(
                        case_id=2,
                        case_key="case_2",
                        rater_id="rater-b",
                        user_id=user_b.id,
                        status="draft",
                        payload_json={},
                    ),
                ]
            )
        with get_db_session(factory) as session:
            user_a = session.get(User, "user-a")
            body = HumanEvalService().export_csv(session=session, user=user_a)
        self.assertIn("rater-a", body)
        self.assertNotIn("rater-b", body)

    def test_debug_api_is_disabled_by_default(self) -> None:
        previous = os.environ.pop("SIMLAW_ENABLE_DEBUG_UI", None)
        try:
            with self.assertRaises(Exception) as raised:
                _require_debug_ui()
            self.assertEqual(getattr(raised.exception, "status_code", None), 404)
        finally:
            if previous is not None:
                os.environ["SIMLAW_ENABLE_DEBUG_UI"] = previous

    def test_websocket_token_uses_subprotocol_and_query_is_off_by_default(self) -> None:
        class FakeWebSocket:
            headers = {"sec-websocket-protocol": "simlaw-auth, signed.jwt.token"}
            query_params = {"token": "leaked-query-token"}

        previous = os.environ.pop("SIMLAW_ALLOW_WS_QUERY_TOKEN", None)
        try:
            self.assertEqual(
                _extract_websocket_token(FakeWebSocket()),
                ("signed.jwt.token", "simlaw-auth"),
            )
            FakeWebSocket.headers = {}
            self.assertEqual(_extract_websocket_token(FakeWebSocket()), ("", None))
        finally:
            if previous is not None:
                os.environ["SIMLAW_ALLOW_WS_QUERY_TOKEN"] = previous


if __name__ == "__main__":
    unittest.main()
