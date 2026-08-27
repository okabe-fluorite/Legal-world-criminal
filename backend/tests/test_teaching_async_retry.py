from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.teaching.scorer import TeachingScorer


class TeachingAsyncRetryTests(unittest.TestCase):
    def test_retryable_failure_is_retried_without_waiting_in_test(self) -> None:
        scorer = TeachingScorer()
        calls = 0

        def score(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                scorer._retryable_stage_failure = True
                return None
            scorer._retryable_stage_failure = False
            return {"event_id": "evt-retry", "stage": kwargs["stage"]}

        scorer._score_stage_safe = score  # type: ignore[method-assign]
        with tempfile.TemporaryDirectory() as directory, patch(
            "src.teaching.scorer.time.sleep"
        ) as sleep:
            result = scorer._score_stage_async_with_retry(
                case_id="case_1",
                stage="PR",
                case_output_dir=Path(directory),
                student_id="student-1",
            )
        self.assertEqual(result["event_id"], "evt-retry")
        self.assertEqual(calls, 2)
        sleep.assert_called_once()

    def test_non_retryable_empty_stage_stops_immediately(self) -> None:
        scorer = TeachingScorer()
        calls = 0

        def score(**kwargs):
            nonlocal calls
            calls += 1
            scorer._retryable_stage_failure = False
            return None

        scorer._score_stage_safe = score  # type: ignore[method-assign]
        with tempfile.TemporaryDirectory() as directory, patch(
            "src.teaching.scorer.time.sleep"
        ) as sleep:
            result = scorer._score_stage_async_with_retry(
                case_id="case_1",
                stage="PR",
                case_output_dir=Path(directory),
                student_id="student-1",
            )
        self.assertIsNone(result)
        self.assertEqual(calls, 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
