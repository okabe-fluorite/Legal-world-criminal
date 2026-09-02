from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from src.hybrid_rag.siliconflow import SiliconFlowClient, normalize_endpoint  # noqa: E402


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class SiliconFlowClientTests(unittest.TestCase):
    def test_endpoint_normalization_accepts_root_or_full_url(self) -> None:
        self.assertEqual(
            normalize_endpoint("https://api.siliconflow.ai/v1/embeddings", "embeddings"),
            "https://api.siliconflow.ai/v1/embeddings",
        )
        self.assertEqual(
            normalize_endpoint("https://api.siliconflow.com/v1", "rerank"),
            "https://api.siliconflow.com/v1/rerank",
        )

    def test_embedding_reorders_by_index_and_requests_dimensions(self) -> None:
        calls = []

        def post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(
                200,
                {
                    "model": "embedding-model",
                    "data": [
                        {"index": 1, "embedding": [2.0, 0.0]},
                        {"index": 0, "embedding": [1.0, 0.0]},
                    ],
                    "usage": {"prompt_tokens": 4, "total_tokens": 4},
                },
            )

        client = SiliconFlowClient(
            api_key="secret",
            embedding_url="https://configured.invalid/v1/embeddings",
            embedding_model="embedding-model",
            reranker_url="https://configured.invalid/v1/rerank",
            reranker_model="reranker-model",
            post=post,
        )
        result = client.embed(["甲", "乙"], dimensions=2)
        self.assertEqual(result.vectors, [[1.0, 0.0], [2.0, 0.0]])
        self.assertEqual(calls[0][1]["json"]["dimensions"], 2)
        self.assertEqual(calls[0][1]["json"]["encoding_format"], "float")

    def test_reranker_validates_indices_and_returns_score_order(self) -> None:
        def post(url, **kwargs):
            return FakeResponse(
                200,
                {
                    "results": [
                        {"index": 0, "relevance_score": 0.2},
                        {"index": 1, "relevance_score": 0.9},
                    ],
                    "meta": {"tokens": {"input_tokens": 8, "output_tokens": 0}},
                },
            )

        client = SiliconFlowClient(
            api_key="secret",
            embedding_url="https://configured.invalid/v1/embeddings",
            embedding_model="embedding-model",
            reranker_url="https://configured.invalid/v1/rerank",
            reranker_model="reranker-model",
            post=post,
        )
        result = client.rerank("苹果", ["香蕉", "苹果"], top_n=2)
        self.assertEqual([item.index for item in result.items], [1, 0])
        self.assertEqual(result.input_tokens, 8)


if __name__ == "__main__":
    unittest.main()
