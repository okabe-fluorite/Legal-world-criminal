from __future__ import annotations

import unittest

from src.runtime_tech_strategy import RuntimeTechStrategy


class FakeMap:
    def __init__(self) -> None:
        self.events = []

    async def broadcast_runtime_progress(self, case_id, **kwargs):
        self.events.append({"case_id": case_id, **kwargs})


class RuntimeTruthfulnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_tool_failure_is_not_reported_completed(self) -> None:
        view = FakeMap()

        def fail(_name, **_kwargs):
            raise RuntimeError("index unavailable")

        strategy = RuntimeTechStrategy(map_engine=view, tool_executor=fail)
        result = await strategy.call_tool_or_demo(
            case_id="case_1",
            stage_code="DS",
            tool_name="search_laws",
            message="法条检索完成",
        )
        self.assertFalse(result.succeeded)
        metadata = view.events[-1]["metadata"]
        self.assertEqual(metadata["tech_event_status"], "failed")
        self.assertIn("未执行", metadata["tech_event_label"])

    async def test_demo_and_real_statuses_are_distinct(self) -> None:
        view = FakeMap()
        strategy = RuntimeTechStrategy(
            map_engine=view,
            tool_executor=lambda name, **kwargs: {"tool": name, "ok": True},
        )
        await strategy.emit_stage_start(case_id="case_1", stage_code="DS")
        await strategy.call_tool_or_demo(
            case_id="case_1",
            stage_code="DS",
            tool_name="check_citations",
            message="引用校验完成",
        )
        statuses = [row["metadata"]["tech_event_status"] for row in view.events]
        self.assertEqual(statuses, ["demo", "completed"])


if __name__ == "__main__":
    unittest.main()

