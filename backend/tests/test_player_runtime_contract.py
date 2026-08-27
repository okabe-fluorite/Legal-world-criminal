from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.player_lawyer import routes


class PlayerRuntimeContractTests(unittest.TestCase):
    def test_disabled_player_mode_returns_empty_runtime_without_gateway(self) -> None:
        previous_status = routes._status_provider
        previous_gateway = routes._gateway_provider
        routes.set_status_provider(
            lambda _request: {"player_mode": "off", "enabled": False}
        )

        def fail_if_called(_request):
            raise AssertionError("disabled runtime must not resolve a player gateway")

        routes.set_gateway_provider(fail_if_called)
        app = FastAPI()
        app.include_router(routes.router)
        try:
            with TestClient(app) as client:
                response = client.get("/api/sandbox/player-lawyer/runtime")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json(),
                {"player_mode": "off", "enabled": False, "pending": [], "count": 0},
            )
        finally:
            routes._status_provider = previous_status
            routes._gateway_provider = previous_gateway


if __name__ == "__main__":
    unittest.main()
