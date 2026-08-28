"""Generate criminal sandbox seed data from criminal_case_dataset.json.

Mirrors scripts/build_seed_data.py (civil) but for the criminal adaptation:

    sandbox_seed_data/
    ├─ case_data_extracted.json          # copy of the criminal dataset
    ├─ cases/case_<id>/{plaintiff,defendant}/config.yaml
    │     (criminal cases: plaintiff = 被告人委托方/家属视角, defendant = 被告人)
    ├─ law_firms/firm_01/{lawyer_roster.yaml, lawyers/lawyer_XX/config.yaml}
    ├─ court_system/{basic_court,intermediate_court}/judges/judge_XX/config.yaml
    └─ prosecutors/prosecutor_01/config.yaml   # ★ criminal: prosecutor agent

Usage:
    python backend/scripts/build_seed_data_criminal.py [--dataset PATH] [--max-cases N]

Idempotent — re-running overwrites case configs but leaves templates intact.
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
from pathlib import Path

import yaml

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.case_bundle.selection import select_diverse_cases  # noqa: E402

DEFAULT_DATASET = REPO_ROOT / "dataset" / "released_case_dataset.json"
SEED_DIR = REPO_ROOT / "backend" / "sandbox_seed_data"
EXTRACTED_FILENAME = "case_data_extracted.json"

MAX_CASES_DEFAULT = 8

# ── Templates ──────────────────────────────────────────────

LAW_FIRM_ID = "firm_zhengyi"
LAW_FIRM_NAME = "正意律师事务所"

LAWYER_ROSTER = {
    "firm_id": LAW_FIRM_ID,
    "firm_name": LAW_FIRM_NAME,
    "lawyers": [
        {
            "id": "lawyer_01",
            "name": "沈度",
            "seniority": "Senior Partner",
            "specialty": ["刑事辩护", "暴力犯罪"],
        },
        {
            "id": "lawyer_02",
            "name": "纪明澜",
            "seniority": "Partner",
            "specialty": ["经济犯罪", "金融犯罪"],
        },
        {
            "id": "lawyer_03",
            "name": "裴见素",
            "seniority": "Associate",
            "specialty": ["财产犯罪", "毒品犯罪"],
        },
        {
            "id": "lawyer_04",
            "name": "温以珩",
            "seniority": "Associate",
            "specialty": ["职务犯罪", "少年司法"],
        },
    ],
}


def lawyer_config(lawyer_entry: dict) -> dict:
    return {
        "profile": {
            "lawyer_id": lawyer_entry["id"],
            "name": lawyer_entry["name"],
            "seniority": lawyer_entry["seniority"],
            "specialty": lawyer_entry["specialty"],
            "firm_id": LAW_FIRM_ID,
            "law_firm": LAW_FIRM_NAME,
        },
        "case_state": "空闲",
        "current_handling_case": None,
        "case_queue": [],
        "long_term_memory": {
            "case_summary": "",
            "legal_relationship": "",
            "dispute_focus": "",
        },
    }


BASIC_COURT_NAME = "基层人民法院"
INTERMEDIATE_COURT_NAME = "中级人民法院"

JUDGES = [
    {"name": "贺兰", "court_level": "basic", "years": 12},
    {"name": "陆青崖", "court_level": "basic", "years": 8},
    {"name": "闻笛", "court_level": "intermediate", "years": 15},
    {"name": "简清越", "court_level": "intermediate", "years": 10},
]


def judge_config(*, name: str, court_name: str, court_level: str, years: int) -> dict:
    return {
        "profile": {
            "name": name,
            "court_name": court_name,
            "court_level": court_level,
            "years_of_experience": years,
        },
        "case_state": "空闲",
        "current_handling_case": None,
        "case_queue": [],
    }


PROSECUTOR_ID = "prosecutor_01"
PROSECUTOR_NAME = "阚泽民"


def prosecutor_config() -> dict:
    return {
        "profile": {
            "prosecutor_id": PROSECUTOR_ID,
            "name": PROSECUTOR_NAME,
            "title": "公诉人",
            "organization": "某某市人民检察院",
            "specialty": ["刑事公诉", "证据审查"],
        },
        "case_state": "空闲",
        "current_handling_case": None,
        "case_queue": [],
    }


# ── Case config generation ─────────────────────────────────

def case_config(
    *,
    case_id: int,
    party_role: str,
    dataset_path: str,
    case_cause: str,
    source_title: str = "",
    original_case_id: int | None = None,
    case_bundle_id: str = "",
    case_bundle_version: str = "",
    case_bundle_content_sha256: str = "",
) -> dict:
    config = {
        "case_id": str(case_id),
        "party_role": party_role,
        "dataset_path": dataset_path,
        "case_type": case_cause,
        "case_category": "criminal",
        "case_state": "空闲",
        "designated_lawyer_id": "",
        "assigned_lawyer_id": "",
        "profile": {},  # auto-filled from dataset by seeder
    }
    if original_case_id is not None:
        config["original_case_id"] = int(original_case_id)
    if case_bundle_id:
        config["case_bundle_id"] = case_bundle_id
        config["case_bundle_version"] = case_bundle_version
        config["case_bundle_content_sha256"] = case_bundle_content_sha256
    if source_title:
        config["source_title"] = source_title
    return config


# ── Driver ─────────────────────────────────────────────────

def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def build_templates() -> None:
    # Law firm
    firm_dir = SEED_DIR / "law_firms" / LAW_FIRM_ID
    write_yaml(firm_dir / "lawyer_roster.yaml", LAWYER_ROSTER)
    for entry in LAWYER_ROSTER["lawyers"]:
        write_yaml(firm_dir / "lawyers" / entry["id"] / "config.yaml", lawyer_config(entry))

    # Courts
    for level, court_name in (("basic", BASIC_COURT_NAME), ("intermediate", INTERMEDIATE_COURT_NAME)):
        court_dir = SEED_DIR / "court_system" / f"{level}_court" / "judges"
        for judge in JUDGES:
            if judge["court_level"] != level:
                continue
            write_yaml(
                court_dir / f"judge_{judge['name']}" / "config.yaml",
                judge_config(
                    name=judge["name"],
                    court_name=court_name,
                    court_level=level,
                    years=judge["years"],
                ),
            )

    # Prosecutor (criminal-only)
    write_yaml(
        SEED_DIR / "court_system" / "procuratorate" / "prosecutors" / PROSECUTOR_ID / "config.yaml",
        prosecutor_config(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path, default=DEFAULT_DATASET,
        help=f"Path to criminal_case_dataset.json (default: {DEFAULT_DATASET})",
    )
    parser.add_argument("--max-cases", type=int, default=MAX_CASES_DEFAULT)
    parser.add_argument("--seed-dir", type=Path, default=SEED_DIR)
    parser.add_argument(
        "--prefer-complete", action="store_true", default=True,
        help="Prefer cases with judgment text (skip label-controlled drafts)",
    )
    args = parser.parse_args()

    dataset_path: Path = args.dataset.resolve()
    if not dataset_path.exists():
        print(f"[ERROR] dataset not found: {dataset_path}", file=sys.stderr)
        return 1

    seed_dir: Path = args.seed_dir.resolve()
    seed_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] Loading dataset from {dataset_path}")
    with dataset_path.open("r", encoding="utf-8") as handle:
        cases = json.load(handle)
    if not isinstance(cases, list):
        print("[ERROR] expected a list of cases at top level", file=sys.stderr)
        return 1

    from audit_case_dataset import audit_case

    blocked = [
        (case, audit_case(case))
        for case in cases
        if not audit_case(case)["releasable"]
    ]
    if blocked:
        for case, audit in blocked[:10]:
            print(
                f"[BLOCKED] case {case.get('original_id')}: "
                f"{[flag['code'] for flag in audit['flags']]}",
                file=sys.stderr,
            )
        print("[ERROR] dataset contains unreleasable cases", file=sys.stderr)
        return 1

    if args.prefer_complete:
        complete = [
            c for c in cases
            if (c.get("extracted_info", {}).get("first_instance", {}).get("main_sentence") or "").strip()
        ]
        others = [c for c in cases if c not in complete]
        cases = complete + others
        print(f"  完整判决案件: {len(complete)} / {len(cases)}（优先取用）")

    selected = select_diverse_cases(cases, args.max_cases)
    causes_selected = [str(c.get("extracted_info", {}).get("case_cause") or "?") for c in selected]
    print(f"  选案罪名分布: { {k: causes_selected.count(k) for k in causes_selected} }")
    print(f"[2/4] Seeding {len(selected)} cases into {seed_dir}")

    cases_dir = seed_dir / "cases"
    from src.case_bundle.service import get_case_bundle_service

    bundle_service = get_case_bundle_service()
    reset_dir(cases_dir)
    for idx, case in enumerate(selected, start=1):
        extracted = case.get("extracted_info", {})
        cause = str(extracted.get("case_cause") or "刑事案件")
        source_title = str(extracted.get("source_title") or "").strip()
        governed_bundle = bundle_service.resolve(f"case_{idx}")
        if governed_bundle is None or int(governed_bundle["original_case_id"]) != int(
            case["original_id"]
        ):
            raise ValueError(
                f"CaseBundle runtime mapping drift for case_{idx}: "
                f"selected original_id={case.get('original_id')}"
            )
        for party_role in ("plaintiff", "defendant"):
            write_yaml(
                cases_dir / f"case_{idx}" / party_role / "config.yaml",
                case_config(
                    case_id=idx,
                    party_role=party_role,
                    dataset_path=EXTRACTED_FILENAME,
                    case_cause=cause,
                    source_title=source_title,
                    original_case_id=int(case["original_id"]),
                    case_bundle_id=str(governed_bundle["case_bundle_id"]),
                    case_bundle_version=str(governed_bundle["version"]),
                    case_bundle_content_sha256=str(governed_bundle["content_sha256"]),
                ),
            )

    print(f"[3/4] Writing dataset copy → {seed_dir / EXTRACTED_FILENAME}")
    shutil.copyfile(dataset_path, seed_dir / EXTRACTED_FILENAME)

    print("[4/4] Building firm/court/prosecutor templates")
    build_templates()

    print("Done. Seed tree:")
    for path in sorted(seed_dir.rglob("config.yaml")):
        print(f"  {path.relative_to(seed_dir)}")
    print(f"  {EXTRACTED_FILENAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
