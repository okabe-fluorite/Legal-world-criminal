from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src.utils.model_config import (
    FailoverModelBackend,
    MODEL_TASKS,
    ModelEndpoint,
    build_camel_model,
    build_model_catalog,
    reset_model_failover_circuits,
    resolve_fallback_model_endpoint,
    resolve_model_endpoint,
)


MODEL_ENV_KEYS = {
    "OPENAI_API_KEY",
    "OPENAI_API_BASE_URL",
    "OPENAI_MODEL_NAME",
    "SIMLAW_SMALL_MODEL_API_KEY",
    "SIMLAW_SMALL_MODEL_API_BASE_URL",
    "SIMLAW_SMALL_MODEL_NAME",
    "SIMLAW_SMALL_MODEL_TASKS",
    "SIMLAW_SMALL_MODEL_TIMEOUT_SECONDS",
    "SIMLAW_MODEL_TEACHING_JUDGE_NAME",
    "SIMLAW_MODEL_TEACHING_JUDGE_API_BASE_URL",
    "SIMLAW_MODEL_TEACHING_JUDGE_API_KEY",
    "SIMLAW_MODEL_TEACHING_JUDGE_TIMEOUT_SECONDS",
    "SIMLAW_FALLBACK_MODEL_API_KEY",
    "SIMLAW_FALLBACK_MODEL_API_BASE_URL",
    "SIMLAW_FALLBACK_MODEL_NAME",
    "SIMLAW_FALLBACK_MODEL_TIMEOUT_SECONDS",
    "SIMLAW_FALLBACK_CIRCUIT_SECONDS",
}


class FakeBackend:
    model_type = "primary-model"
    model_config_dict: dict = {}
    token_counter = object()
    stream = False

    def __init__(self, *, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def run(self, *args, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result

    async def arun(self, *args, **kwargs):
        return self.run(*args, **kwargs)


class ModelRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_model_failover_circuits()
        self.original = {key: os.environ.get(key) for key in MODEL_ENV_KEYS}
        for key in MODEL_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ.update(
            {
                "OPENAI_API_KEY": "primary-secret",
                "OPENAI_API_BASE_URL": "https://primary.example/v1",
                "OPENAI_MODEL_NAME": "primary-model",
            }
        )

    def tearDown(self) -> None:
        reset_model_failover_circuits()
        for key in MODEL_ENV_KEYS:
            os.environ.pop(key, None)
        for key, value in self.original.items():
            if value is not None:
                os.environ[key] = value

    def test_small_model_routes_only_selected_tasks(self) -> None:
        os.environ.update(
            {
                "SIMLAW_SMALL_MODEL_API_KEY": "small-secret",
                "SIMLAW_SMALL_MODEL_API_BASE_URL": "http://127.0.0.1:8001/v1",
                "SIMLAW_SMALL_MODEL_NAME": "law-tutor-7b-lora",
                "SIMLAW_SMALL_MODEL_TASKS": "teaching_judge,response_assist",
            }
        )
        judge = resolve_model_endpoint("teaching_judge")
        agent = resolve_model_endpoint("agent")
        self.assertEqual(judge.provider, "fine_tuned_small_model")
        self.assertEqual(judge.model_name, "law-tutor-7b-lora")
        self.assertEqual(judge.api_key, "small-secret")
        self.assertEqual(agent.provider, "primary")
        self.assertEqual(agent.model_name, "primary-model")

    def test_task_override_has_highest_environment_precedence(self) -> None:
        os.environ.update(
            {
                "SIMLAW_SMALL_MODEL_NAME": "generic-small",
                "SIMLAW_SMALL_MODEL_TASKS": "*",
                "SIMLAW_MODEL_TEACHING_JUDGE_NAME": "judge-specialist",
                "SIMLAW_MODEL_TEACHING_JUDGE_API_BASE_URL": "https://judge.example/private/v1",
                "SIMLAW_MODEL_TEACHING_JUDGE_API_KEY": "judge-secret",
                "SIMLAW_MODEL_TEACHING_JUDGE_TIMEOUT_SECONDS": "75",
            }
        )
        endpoint = resolve_model_endpoint("teaching_judge")
        self.assertEqual(endpoint.provider, "task_override")
        self.assertEqual(endpoint.model_name, "judge-specialist")
        self.assertEqual(endpoint.timeout_seconds, 75)

    def test_safe_catalog_never_serializes_api_keys_or_url_paths(self) -> None:
        os.environ.update(
            {
                "SIMLAW_SMALL_MODEL_API_KEY": "do-not-expose",
                "SIMLAW_SMALL_MODEL_API_BASE_URL": "https://small.example/secret/path/v1",
                "SIMLAW_SMALL_MODEL_NAME": "small-model",
                "SIMLAW_SMALL_MODEL_TASKS": "eval",
            }
        )
        catalog = build_model_catalog()
        serialized = repr(catalog)
        self.assertNotIn("do-not-expose", serialized)
        self.assertNotIn("secret/path", serialized)
        self.assertEqual({row["task"] for row in catalog["routes"]}, set(MODEL_TASKS))

    def test_camel_factory_receives_selected_endpoint(self) -> None:
        os.environ.update(
            {
                "SIMLAW_SMALL_MODEL_API_KEY": "small-secret",
                "SIMLAW_SMALL_MODEL_API_BASE_URL": "http://localhost:9000/v1",
                "SIMLAW_SMALL_MODEL_NAME": "fine-tuned-law-model",
                "SIMLAW_SMALL_MODEL_TASKS": "document_assist",
            }
        )
        with patch("camel.models.ModelFactory.create", return_value="model") as create:
            model, endpoint = build_camel_model(
                "document_assist",
                temperature=0.2,
                max_tokens=1024,
            )
        self.assertEqual(model, "model")
        self.assertEqual(endpoint.provider, "fine_tuned_small_model")
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["model_type"], "fine-tuned-law-model")
        self.assertEqual(kwargs["url"], "http://localhost:9000/v1")
        self.assertEqual(kwargs["api_key"], "small-secret")
        self.assertEqual(kwargs["timeout"], 180)
        self.assertEqual(kwargs["model_config_dict"]["max_tokens"], 1024)

    def test_transient_failure_uses_fallback_and_opens_shared_circuit(self) -> None:
        primary = FakeBackend(error=RuntimeError("429 5-hour usage limit reached"))
        fallback = FakeBackend(result="fallback-result")
        primary_endpoint = ModelEndpoint(
            task="agent",
            provider="primary",
            model_name="primary-model",
            api_base_url="https://primary.example/v1",
            api_key="primary-secret",
            timeout_seconds=20,
        )
        fallback_endpoint = ModelEndpoint(
            task="agent",
            provider="automatic_fallback",
            model_name="fallback-model",
            api_base_url="https://fallback.example/v1",
            api_key="fallback-secret",
            timeout_seconds=20,
        )
        backend = FailoverModelBackend(
            primary=primary,
            fallback=fallback,
            primary_endpoint=primary_endpoint,
            fallback_endpoint=fallback_endpoint,
            circuit_seconds=60,
        )
        self.assertEqual(backend._run([]), "fallback-result")
        self.assertEqual(backend._run([]), "fallback-result")
        self.assertEqual(primary.calls, 1)
        self.assertEqual(fallback.calls, 2)

    def test_non_transient_configuration_error_does_not_fallback(self) -> None:
        primary = FakeBackend(error=RuntimeError("401 invalid API key"))
        fallback = FakeBackend(result="must-not-run")
        backend = FailoverModelBackend(
            primary=primary,
            fallback=fallback,
            primary_endpoint=ModelEndpoint(
                "agent", "primary", "primary-model", "https://primary.example/v1", "x", 20
            ),
            fallback_endpoint=ModelEndpoint(
                "agent", "automatic_fallback", "fallback-model", "https://fallback.example/v1", "y", 20
            ),
            circuit_seconds=60,
        )
        with self.assertRaisesRegex(RuntimeError, "401"):
            backend._run([])
        self.assertEqual(fallback.calls, 0)

    def test_fallback_catalog_is_secret_free(self) -> None:
        os.environ.update(
            {
                "SIMLAW_FALLBACK_MODEL_API_KEY": "official-secret",
                "SIMLAW_FALLBACK_MODEL_API_BASE_URL": "https://api.deepseek.com/private/v1",
                "SIMLAW_FALLBACK_MODEL_NAME": "deepseek-chat",
            }
        )
        endpoint = resolve_fallback_model_endpoint("agent")
        self.assertEqual(endpoint.api_key, "official-secret")
        catalog = build_model_catalog()
        serialized = repr(catalog)
        self.assertNotIn("official-secret", serialized)
        self.assertNotIn("private/v1", serialized)
        self.assertEqual(catalog["failover"]["mode"], "automatic_transient_errors_only")

    def test_unknown_task_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_model_endpoint("unknown-task")


if __name__ == "__main__":
    unittest.main()
