from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .planner import INSTRUCTIONAL_ORDER
from .store import AdaptiveStore


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class AdaptiveService:
    def __init__(self, *, data_dir: Path, store: AdaptiveStore) -> None:
        self.data_dir = Path(data_dir)
        self.store = store
        task_path = self.data_dir / "task_items.jsonl"
        card_path = self.data_dir / "knowledge_cards.jsonl"
        self.uses_governed_contracts = task_path.is_file() and card_path.is_file()
        self.approved = read_jsonl(
            task_path if self.uses_governed_contracts else self.data_dir / "approved_items.jsonl"
        )
        self.q_edges = read_jsonl(self.data_dir / "q_matrix.jsonl")
        self.nodes = read_jsonl(
            card_path if self.uses_governed_contracts else self.data_dir / "knowledge_nodes.jsonl"
        )
        self.item_records = {
            str(row.get("task_id") or row.get("candidate_id")): row
            for row in self.approved
        }
        self.item_to_knowledge = {
            str(row["item_id"]): str(row["knowledge_id"]) for row in self.q_edges
        }
        self.knowledge_by_id = {
            str(row["knowledge_id"]): row for row in self.nodes
        }
        self.items_by_knowledge: dict[str, list[str]] = defaultdict(list)
        for item_id, knowledge_id in self.item_to_knowledge.items():
            if item_id in self.item_records:
                self.items_by_knowledge[knowledge_id].append(item_id)

    def profile(self, student_id: str) -> dict[str, Any]:
        return self.store.profile(student_id)

    def recommendations(
        self,
        student_id: str,
        *,
        limit: int = 10,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        profile = self.profile(student_id)
        attempted = {
            str(value)
            for value in ((context or {}).get("attempted_item_ids") or [])
        }
        selected = []
        candidates = set(self.item_records) - attempted
        selected_by_knowledge: defaultdict[str, int] = defaultdict(int)

        while candidates and len(selected) < max(1, min(int(limit), 30)):
            scored = []
            for item_id in candidates:
                knowledge_id = self.item_to_knowledge[item_id]
                node = self.knowledge_by_id[knowledge_id]
                name = str(node["canonical_name"])
                state = (profile.get("knowledge") or {}).get(knowledge_id) or {}
                latest = str(state.get("latest") or "")
                status = str(state.get("evidence_status") or "insufficient_evidence")
                if latest == "missing":
                    base, reason = 145.0, "case_evidence_indicates_weakness"
                elif latest == "partial":
                    base, reason = 120.0, "case_evidence_requires_reinforcement"
                elif latest == "mastered" and status == "provisional":
                    base, reason = 45.0, "provisional_mastery_spaced_review"
                elif state:
                    base, reason = 105.0, "insufficient_repeated_evidence"
                else:
                    base, reason = 100.0, "no_evidence_collect_diagnostic"
                order = INSTRUCTIONAL_ORDER.get(name, 99)
                score = base - order * 2.5 - selected_by_knowledge[knowledge_id] * 35
                scored.append((score, -order, item_id, knowledge_id, reason))
            score, _order, item_id, knowledge_id, reason = max(scored)
            candidates.remove(item_id)
            selected_by_knowledge[knowledge_id] += 1
            record = self.item_records[item_id]
            item = record if self.uses_governed_contracts else record["item"]
            selected.append(
                {
                    "rank": len(selected) + 1,
                    "task_id": item_id,
                    "item_id": item_id,
                    "task_type": "diagnostic_item",
                    "knowledge_id": knowledge_id,
                    "knowledge_name": self.knowledge_by_id[knowledge_id]["canonical_name"],
                    "stem": item["stem"],
                    "options": item["options"],
                    "difficulty": item.get("difficulty", 2),
                    "cognitive_dimension": item.get("cognitive_dimension", ""),
                    "reason_code": reason,
                    "score": round(score, 4),
                    "answer_included": False,
                    "content_version": str(item.get("content_sha256") or ""),
                    "standard_evidence_ids": list(item.get("standard_evidence_ids") or []),
                }
            )
        return selected

    def ingest(self, event: dict[str, Any]) -> dict[str, Any]:
        status = self.store.insert(event)
        student_id = str(
            event.get("student_pseudonym") or event.get("student_id") or ""
        ).strip()
        profile = self.profile(student_id)
        recommendations = self.recommendations(student_id, limit=10)
        return {
            "schema_version": "edubrain-adaptive-event-response-v1",
            "event_status": status,
            "profile": profile,
            "recommendations": recommendations,
            "policy_version": "hybrid-case-evidence-cold-start-v1",
        }
