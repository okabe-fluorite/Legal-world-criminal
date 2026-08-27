from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.tools.legal import (
    render_document_drafting_payload_for_output_dir,
    render_judgment_document_payload_for_output_dir,
)


class DocumentOutputIsolationTests(unittest.TestCase):
    def test_all_criminal_pdfs_stay_inside_explicit_case_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            payloads = [
                render_document_drafting_payload_for_output_dir(
                    document_type="DS",
                    document_text="辩护词\n依法提出辩护意见。",
                    case_output_dir=root,
                ),
                render_judgment_document_payload_for_output_dir(
                    document_type="CR",
                    document_text="刑事一审判决书\n经审理，依法判决。",
                    case_output_dir=root,
                ),
                render_judgment_document_payload_for_output_dir(
                    document_type="CRA",
                    document_text="刑事二审判决书\n经审理，依法裁判。",
                    case_output_dir=root,
                ),
            ]
            for payload in payloads:
                pdf = Path(payload["pdf_path"]).resolve()
                self.assertTrue(pdf.is_file())
                self.assertEqual(pdf.parent, root)
                self.assertGreater(pdf.stat().st_size, 100)


if __name__ == "__main__":
    unittest.main()
