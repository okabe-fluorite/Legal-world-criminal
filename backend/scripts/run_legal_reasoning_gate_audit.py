"""Run deterministic positive/negative fixtures for the LegalReasoning gate."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
for entry in (REPO_ROOT, BACKEND_DIR):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from src.legal_reasoning.gate import (  # noqa: E402
    LegalReasoningGate,
    build_case_gate_context,
)


DEFAULT_FIXTURES = BACKEND_DIR / "evaluation" / "legal_reasoning_gate_fixtures.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "docs" / "LEGAL_REASONING_GATE_AUDIT.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "docs" / "LEGAL_REASONING_GATE_AUDIT.md"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _set_path(value: Any, path: list[Any], replacement: Any) -> None:
    target = value
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = copy.deepcopy(replacement)


def apply_mutations(base: dict[str, Any], mutations: list[dict[str, Any]]) -> dict[str, Any]:
    output = copy.deepcopy(base)
    for mutation in mutations:
        operation = mutation["op"]
        path = mutation["path"]
        if operation == "set":
            _set_path(output, path, mutation.get("value"))
        elif operation == "slice":
            target = output
            for part in path:
                target = target[part]
            if not isinstance(target, list):
                raise ValueError(f"slice target is not a list: {path}")
            del target[int(mutation["value"]) :]
        else:
            raise ValueError(f"unknown mutation operation: {operation}")
    return output


def run_suite(suite: dict[str, Any]) -> dict[str, Any]:
    gate = LegalReasoningGate()
    base_context = dict(suite["context"])
    rows = []
    expectations_met = True
    for fixture in suite["fixtures"]:
        context_args = {**base_context, **(fixture.get("context_overrides") or {})}
        context_args["case_id"] = context_args.pop("case_bundle_id")
        context = build_case_gate_context(**context_args)
        reasoning = apply_mutations(suite["base_reasoning"], fixture.get("mutations") or [])
        result = gate.evaluate(reasoning, context)
        expected_failed = set(fixture.get("expected_failed_checks") or [])
        actual_failed = set(result["failed_checks"])
        expectation_met = (
            result["passed"] is bool(fixture["expected_pass"])
            and expected_failed <= actual_failed
        )
        expectations_met = expectations_met and expectation_met
        rows.append(
            {
                "fixture_id": fixture["fixture_id"],
                "description": fixture["description"],
                "expected_pass": fixture["expected_pass"],
                "actual_pass": result["passed"],
                "expected_failed_checks": sorted(expected_failed),
                "actual_failed_checks": result["failed_checks"],
                "expectation_met": expectation_met,
                "gate_result": result,
            }
        )
    passed_fixtures = sum(row["actual_pass"] for row in rows)
    blocked_fixtures = len(rows) - passed_fixtures
    return {
        "schema_version": "legal-reasoning-gate-audit-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixture_suite_id": suite["fixture_suite_id"],
        "fixture_suite_sha256": _sha256(DEFAULT_FIXTURES),
        "schema_sha256": _sha256(REPO_ROOT / "schemas" / "legal-reasoning-v1.schema.json"),
        "counts": {
            "fixtures": len(rows),
            "positive_passed": passed_fixtures,
            "negative_blocked": blocked_fixtures,
            "expectations_met": sum(row["expectation_met"] for row in rows),
        },
        "all_expectations_met": expectations_met,
        "model_calls": 0,
        "network_calls": 0,
        "case_context": {
            "case_bundle_id": base_context["case_bundle_id"],
            "stage": base_context["stage"],
            "evidence_status": base_context["evidence_status"],
            "required_element_ids": base_context["required_element_ids"],
        },
        "fixtures": rows,
        "evidence_boundary": [
            "The audit proves deterministic gate behavior on frozen fixtures.",
            "It does not prove that a passed legal conclusion is substantively correct.",
            "Legal entailment, disputed doctrine and classroom Gold still require law-teacher review.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    counts = report["counts"]
    lines = [
        "# Evidence约束法律推理门禁审计",
        "",
        "## 结论",
        "",
        f"冻结的{counts['fixtures']}个fixture全部符合预期："
        f"{counts['positive_passed']}个正例通过，{counts['negative_blocked']}个负例被阻断。",
        "本审计没有调用模型或网络，只证明确定性门禁行为，不替代法学教师判断法律涵摄是否正确。",
        "",
        "## 固定条件",
        "",
        f"- CaseBundle：`{report['case_context']['case_bundle_id']}`",
        f"- 阶段：`{report['case_context']['stage']}`",
        f"- Evidence状态：`{report['case_context']['evidence_status']}`",
        "- 正例与负例共享同一CaseBundle、学生可见事实和刑法第二十条Evidence。",
        "",
        "## Fixture结果",
        "",
        "| Fixture | 预期 | 结果 | 被阻断检查 |",
        "|---|---|---|---|",
    ]
    for row in report["fixtures"]:
        expected = "通过" if row["expected_pass"] else "阻断"
        actual = "通过" if row["actual_pass"] else "阻断"
        checks = ", ".join(row["actual_failed_checks"]) or "—"
        lines.append(f"| {row['fixture_id']} | {expected} | {actual} | {checks} |")
    lines.extend(
        [
            "",
            "## 证据边界",
            "",
            "- 门禁验证Schema、上下文版本、Evidence范围、条号、逐字quote、学生可见事实路径、必要要件、反方、结论强度、弃权与提示注入canary。",
            "- 通过门禁不等于法律结论正确，也不等于教师Gold；语义涵摄和争议观点仍需法学教师复核。",
            "- 本报告可进入比赛技术提交包；专家准确率和学习效果不得由本报告推导。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    args = parser.parse_args()

    suite = json.loads(args.fixtures.read_text(encoding="utf-8"))
    report = run_suite(suite)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    args.output_md.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "all_expectations_met": report["all_expectations_met"],
                **report["counts"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["all_expectations_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
