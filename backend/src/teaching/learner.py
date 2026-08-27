"""Cross-case learner profile accumulation.

Each LearningEvent updates a learner profile at
`sandbox_data/teaching/profiles/{student_id}.json`.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .rubrics import stage_capability_weights

logger = logging.getLogger(__name__)

PROFILE_SCHEMA = "learner-profile-v1"
DEFAULT_PROFILES_DIR = (
    Path(__file__).resolve().parents[2] / "sandbox_data" / "teaching" / "profiles"
)
_PROFILE_LOCKS: dict[str, threading.RLock] = {}
_PROFILE_LOCKS_GUARD = threading.Lock()
_STATUS_PRIORITY = {"mastered": 1, "partial": 2, "missing": 3}


def _profiles_dir() -> Path:
    return Path(
        os.environ.get("SIMLAW_TEACHING_PROFILES_DIR") or DEFAULT_PROFILES_DIR
    ).resolve()


def _profile_path(student_id: str) -> Path:
    safe_id = "".join(
        ch for ch in str(student_id or "anonymous").strip() if ch.isalnum() or ch in "_-"
    )
    return _profiles_dir() / f"{safe_id}.json"


def _profile_lock(student_id: str) -> threading.RLock:
    safe_id = _profile_path(student_id).stem
    with _PROFILE_LOCKS_GUARD:
        return _PROFILE_LOCKS.setdefault(safe_id, threading.RLock())


def _atomic_write_profile(path: Path, profile: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        temp_path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _load_profile(student_id: str) -> dict[str, Any]:
    path = _profile_path(student_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[Learner] failed to load profile %s: %s", student_id, exc)
    return {
        "schema_version": PROFILE_SCHEMA,
        "student_id": student_id,
        "capability_means": {},
        "knowledge_state": {},
        "error_tag_counts": {},
        "growth_curve": [],
        "cases_played": [],
        "processed_event_ids": [],
        "excluded_events": [],
        "updated_at": "",
    }


def update_profile(student_id: str, event: dict[str, Any]) -> dict[str, Any]:
    """Fold one LearningEvent into the learner profile; returns updated profile."""
    student_id = str(student_id or "anonymous").strip() or "anonymous"
    with _profile_lock(student_id):
        return _update_profile_locked(student_id, event)


def _update_profile_locked(student_id: str, event: dict[str, Any]) -> dict[str, Any]:
    profile = _load_profile(student_id)
    event_id = str(event.get("event_id") or "").strip()
    processed = profile.setdefault("processed_event_ids", [])
    if event_id and event_id in processed:
        return profile

    eligibility = event.get("evidence_eligibility") or {}
    if isinstance(eligibility, dict) and eligibility.get("long_term_profile") is False:
        excluded = profile.setdefault("excluded_events", [])
        if event_id and event_id not in excluded:
            excluded.append(event_id)
            profile["excluded_events"] = excluded[-1000:]
            profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
            _atomic_write_profile(_profile_path(student_id), profile)
        return profile

    stage = str(event.get("stage") or "").strip().upper()
    case_id = str(event.get("case_id") or "")
    scored_at = str(event.get("scored_at") or datetime.now().isoformat(timespec="seconds"))

    # capability means (stage-weighted average: sum(score*weight)/sum(weight))
    weights = stage_capability_weights(stage)
    means = profile.setdefault("capability_means", {})
    weighted_sums = profile.setdefault("_capability_weighted_sums", {})
    weighted_totals = profile.setdefault("_capability_weighted_totals", {})
    for code, entry in (event.get("capability_scores") or {}).items():
        if not isinstance(entry, dict):
            continue
        if entry.get("score") is None:
            continue  # abstained (judge omitted) — never counted as 0
        score = float(entry.get("score") or 0.0)
        weight = weights.get(code, 0.5)
        weighted_sums[code] = float(weighted_sums.get(code, 0.0)) + score * weight
        weighted_totals[code] = float(weighted_totals.get(code, 0.0)) + weight
        means[code] = round(weighted_sums[code] / weighted_totals[code], 3)

    # Knowledge state: one event contributes at most one exposure per knowledge
    # point.  The judge often returns the same weakness in both
    # knowledge_verdicts and knowledge_gaps; counting both inflated evidence.
    knowledge_state = profile.setdefault("knowledge_state", {})
    event_knowledge: dict[str, str] = {}
    knowledge_name_to_id: dict[str, str] = {}
    for verdict in event.get("knowledge_verdicts") or []:
        knowledge_id = str(verdict.get("knowledge_id") or "").strip()
        knowledge_name = str(
            verdict.get("knowledge_name") or verdict.get("kp") or ""
        ).strip()
        kp = knowledge_id or knowledge_name
        if not kp:
            continue
        if knowledge_id and knowledge_name:
            knowledge_name_to_id[knowledge_name] = knowledge_id
        status = str(verdict.get("status") or "partial").strip().lower()
        if status not in _STATUS_PRIORITY:
            status = "partial"
        previous = event_knowledge.get(kp)
        if previous is None or _STATUS_PRIORITY[status] > _STATUS_PRIORITY[previous]:
            event_knowledge[kp] = status

    for gap in event.get("knowledge_gaps") or []:
        gap_name = str(gap or "").strip()
        kp = knowledge_name_to_id.get(gap_name, gap_name)
        if kp:
            event_knowledge[kp] = "missing"

    for kp, status in event_knowledge.items():
        entry = knowledge_state.setdefault(
            kp,
            {"exposed": 0, "latest": "", "history": [], "event_ids": []},
        )
        entry["exposed"] = int(entry.get("exposed") or 0) + 1
        entry["history"].append(status)
        entry["latest"] = status
        if event_id:
            ids = entry.setdefault("event_ids", [])
            if event_id not in ids:
                ids.append(event_id)

    # error tags
    error_counts = profile.setdefault("error_tag_counts", {})
    for tag in event.get("error_tags") or []:
        name = str(tag or "").strip()
        if not name:
            continue
        # group "法条引用错误-264与266混淆" -> "法条引用错误"
        base = name.split("-")[0] if "-" in name else name
        error_counts[base] = int(error_counts.get(base, 0)) + 1

    # growth curve + cases (weighted mean, same caliber as capability_means)
    scored_entries = [
        (float(e.get("score") or 0.0), float(weights.get(code, 0.5)))
        for code, e in (event.get("capability_scores") or {}).items()
        if isinstance(e, dict) and e.get("score") is not None
    ]
    weight_sum = sum(w for _s, w in scored_entries)
    mean = round(sum(s * w for s, w in scored_entries) / weight_sum, 3) if weight_sum else 0.0
    growth = profile.setdefault("growth_curve", [])
    growth.append(
        {
            "at": str(scored_at)[:10],
            "stage": stage,
            "case_id": case_id,
            "mean": mean,
        }
    )
    cases_played = profile.setdefault("cases_played", [])
    if case_id and case_id not in cases_played:
        cases_played.append(case_id)

    if event_id:
        processed.append(event_id)
        profile["processed_event_ids"] = processed[-5000:]
    profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path = _profile_path(student_id)
    _atomic_write_profile(path, profile)
    return profile


def get_profile(student_id: str) -> dict[str, Any]:
    return _load_profile(student_id)


__all__ = ["get_profile", "update_profile"]
