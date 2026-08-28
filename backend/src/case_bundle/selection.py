from __future__ import annotations

from typing import Any


def select_diverse_cases(cases: list[dict[str, Any]], max_cases: int) -> list[dict[str, Any]]:
    """Round-robin by case cause; shared by CaseBundle and sandbox seed builders."""

    by_cause: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        cause = (
            str(case.get("extracted_info", {}).get("case_cause") or "其他").strip()
            or "其他"
        )
        by_cause.setdefault(cause, []).append(case)

    selected: list[dict[str, Any]] = []
    while len(selected) < max(0, int(max_cases)):
        picked_any = False
        for cause in sorted(by_cause):
            pool = by_cause[cause]
            if not pool:
                continue
            selected.append(pool.pop(0))
            picked_any = True
            if len(selected) >= max_cases:
                break
        if not picked_any:
            break
    return selected


__all__ = ["select_diverse_cases"]
