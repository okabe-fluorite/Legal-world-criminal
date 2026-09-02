from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from src.hybrid_rag.siliconflow import EmbeddingResult  # noqa: E402
from src.hybrid_rag.vector_index import IndexRecord, build_vector_index  # noqa: E402


class HybridRagVectorIndexTests(unittest.TestCase):
    def test_builds_normalized_float16_index_and_reuses_manifest(self) -> None:
        calls = []

        def embed(texts):
            calls.append(list(texts))
            vectors = [[float(index + 1), 1.0] for index, _ in enumerate(texts)]
            return EmbeddingResult(
                vectors=vectors,
                model="test-model",
                host="test.local",
                latency_ms=2.5,
                prompt_tokens=len(texts),
                total_tokens=len(texts),
            )

        records = [
            IndexRecord(retrieval_id=f"R{index}", text=f"文本{index}", metadata={"kind": "test"})
            for index in range(5)
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "index"
            manifest = build_vector_index(
                collection_name="test",
                records=records,
                output_dir=output,
                embed_batch=embed,
                model_name="test-model",
                vector_dim=2,
                batch_size=2,
                workers=2,
            )
            vectors = np.load(output / "embeddings.float16.npy").astype(np.float32)
            metadata = [json.loads(line) for line in (output / "metadata.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(vectors.shape, (5, 2))
            self.assertTrue(np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-3))
            self.assertEqual(manifest["record_count"], 5)
            self.assertEqual(manifest["lexical_file"], "lexical.sqlite")
            self.assertTrue((output / "lexical.sqlite").is_file())
            self.assertEqual([row["retrieval_id"] for row in metadata], [f"R{index}" for index in range(5)])
            before = len(calls)
            reused = build_vector_index(
                collection_name="test",
                records=records,
                output_dir=output,
                embed_batch=embed,
                model_name="test-model",
                vector_dim=2,
                batch_size=2,
                workers=2,
            )
            self.assertEqual(reused["status"], "ready")
            self.assertEqual(len(calls), before)


if __name__ == "__main__":
    unittest.main()
