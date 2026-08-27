from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("legalworld_local_start", REPO_ROOT / "start.py")
assert SPEC and SPEC.loader
START = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(START)


class LocalStartTests(unittest.TestCase):
    def test_grouped_file_maps_opencode_primary_and_official_fallback(self) -> None:
        content = """
api_key=primary-secret
baseurl=https://opencode.ai/zen/go/v1
model=deepseek-v4-flash

api_key=embedding-secret
baseurl=https://api.siliconflow.ai/v1/embeddings
model=Qwen/Qwen3-Embedding-8B

api_key=fallback-secret
baseurl=https://api.deepseek.com
model=deepseek-v4-flash-vision-exp
""".strip()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "models.env.example"
            path.write_text(content, encoding="utf-8")
            env: dict[str, str] = {}
            START.apply_grouped_model_config(env, path)
        self.assertEqual(env["OPENAI_API_KEY"], "primary-secret")
        self.assertEqual(env["OPENAI_MODEL_NAME"], "deepseek-v4-flash")
        self.assertEqual(env["SIMLAW_FALLBACK_MODEL_API_KEY"], "fallback-secret")
        self.assertEqual(
            env["SIMLAW_FALLBACK_MODEL_API_BASE_URL"], "https://api.deepseek.com"
        )
        self.assertNotIn("embedding-secret", repr(env))

    def test_explicit_environment_keeps_precedence(self) -> None:
        content = """
api_key=file-primary
baseurl=https://opencode.ai/v1
model=file-model
""".strip()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "models.env"
            path.write_text(content, encoding="utf-8")
            env = {"OPENAI_API_KEY": "explicit-primary"}
            START.apply_grouped_model_config(env, path)
        self.assertEqual(env["OPENAI_API_KEY"], "explicit-primary")
        self.assertEqual(env["OPENAI_MODEL_NAME"], "file-model")


if __name__ == "__main__":
    unittest.main()
