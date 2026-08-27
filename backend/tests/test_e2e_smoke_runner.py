from __future__ import annotations

import unittest

from scripts.run_player_e2e_smoke import _stage_response
from src.tools.legal.document_drafting_support import extract_document_body


class E2ESmokeRunnerTests(unittest.TestCase):
    def test_ds_response_is_a_complete_extractable_defense_document(self) -> None:
        response = _stage_response("DS", "请提交完整辩护词")
        body = extract_document_body(
            response,
            document_title="辩护词",
            end_marker="【起草结束】",
        )
        self.assertTrue(body.startswith("辩护词"))
        self.assertIn("《中华人民共和国刑法》第十四条、第十五条", body)
        self.assertNotIn("【起草结束】", body)


if __name__ == "__main__":
    unittest.main()
