from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for entry in (ROOT, BACKEND):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))
ASSET_DIR = ROOT / "frontend" / "src" / "assets" / "tutor"


class LightweightTutorTests(unittest.TestCase):
    def test_four_final_assets_match_manifest_and_are_webp(self) -> None:
        manifest = json.loads((ASSET_DIR / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["states"]), 4)
        self.assertEqual(manifest["canvas"], {"width": 768, "height": 960, "pixel_format": "yuva420p"})
        for row in manifest["states"]:
            path = ASSET_DIR / row["file"]
            self.assertTrue(path.is_file())
            self.assertEqual(path.stat().st_size, row["bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])
            payload = path.read_bytes()
            self.assertEqual(payload[:4], b"RIFF")
            self.assertEqual(payload[8:12], b"WEBP")

    def test_component_disclosure_contexts_and_browser_speech_are_explicit(self) -> None:
        component = (ROOT / "frontend" / "src" / "components" / "AITutor.vue").read_text(
            encoding="utf-8"
        )
        self.assertIn("AI助教·形成性反馈", component)
        self.assertIn('type TutorContext = "support" | "evidence" | "path"', component)
        self.assertIn("window.speechSynthesis", component)
        self.assertIn("prefers-reduced-motion", component)
        self.assertNotIn("Live2D", component)

    def test_iflytek_reference_catalog_is_secret_free_and_honest(self) -> None:
        from src.media.providers import build_iflytek_provider_catalog

        with patch.dict(
            os.environ,
            {
                "XFYUN_APP_ID": "test-app",
                "XFYUN_API_KEY": "test-secret-key",
                "XFYUN_API_SECRET": "test-secret-value",
            },
            clear=False,
        ):
            catalog = build_iflytek_provider_catalog()
        serialized = json.dumps(catalog, ensure_ascii=False)
        self.assertTrue(catalog["credentials_present"])
        self.assertEqual(catalog["connection_status"], "not_connected")
        self.assertEqual(catalog["adapter_status"], "implemented_real_call_required")
        self.assertIn("online_tts_v2", serialized)
        self.assertIn("streaming_iat_v2", serialized)
        self.assertNotIn("test-secret-key", serialized)
        self.assertNotIn("test-secret-value", serialized)


if __name__ == "__main__":
    unittest.main()
