from __future__ import annotations

import asyncio
import unittest

from src.orchestration.scenario_orchestrator import ScenarioOrchestrator
from src.pipeline.stage_tool_resolver import resolve_configured_tool_names


class FakeMapEngine:
    def __init__(self) -> None:
        self._agent_states = {
            "client": {"birth_loc_id": "birth_locationA"},
            "lawyer": {"birth_loc_id": "birth_locationA"},
            "prosecutor": {"birth_loc_id": "birth_locationB"},
        }
        self.calls: list[tuple[str, str, str]] = []

    async def stand_agent(self, agent_id: str) -> None:
        self.calls.append(("stand", agent_id, ""))

    async def move_to_location(self, agent_id: str, loc_id: str) -> None:
        self.calls.append(("move", agent_id, loc_id))

    async def despawn_agent(self, agent_id: str) -> None:
        self.calls.append(("despawn", agent_id, ""))
        self._agent_states.pop(agent_id, None)


class CaseCloseChoreographyTests(unittest.TestCase):
    def test_lawyer_memory_tools_are_not_injected_into_judge_or_prosecutor(self) -> None:
        prosecutor_tools = resolve_configured_tool_names("PR", "prosecutor", "prosecutor")
        judge_tools = resolve_configured_tool_names("CR", "judge", "judge")
        lawyer_tools = resolve_configured_tool_names("DS", "lawyer", "lawyer")
        for tools in (prosecutor_tools, judge_tools):
            self.assertNotIn("load_lawyer_memory", tools)
            self.assertNotIn("save_lawyer_memory", tools)
        self.assertIn("load_lawyer_memory", lawyer_tools)
        self.assertIn("save_lawyer_memory", lawyer_tools)

    def test_case_close_returns_unique_agents_releases_seats_and_despawns(self) -> None:
        orchestrator = object.__new__(ScenarioOrchestrator)
        orchestrator.map_engine = FakeMapEngine()
        orchestrator._occupied_locations = {
            "meeting_chair_1": "client",
            "meeting_chair_2": "lawyer",
            "unrelated_chair": "other",
        }
        asyncio.run(
            orchestrator._return_agents_to_birth_and_despawn(
                ["client", "lawyer", "prosecutor", "client"]
            )
        )
        self.assertEqual(orchestrator.map_engine._agent_states, {})
        self.assertEqual(orchestrator._occupied_locations, {"unrelated_chair": "other"})
        despawned = [row[1] for row in orchestrator.map_engine.calls if row[0] == "despawn"]
        self.assertEqual(despawned, ["client", "lawyer", "prosecutor"])
        moves = {
            (row[1], row[2]) for row in orchestrator.map_engine.calls if row[0] == "move"
        }
        self.assertEqual(
            moves,
            {
                ("client", "birth_locationA"),
                ("lawyer", "birth_locationA"),
                ("prosecutor", "birth_locationB"),
            },
        )


if __name__ == "__main__":
    unittest.main()
