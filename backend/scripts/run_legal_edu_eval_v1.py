"""Model-independent runner for LegalEduEval-v1 candidate responses.

The runner never calls a model. It scores response JSONL files produced by any
OpenAI-compatible or local adapter and keeps missing E0/E1/E2/E3 columns pending.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = REPO_ROOT / "backend" / "evaluation" / "legal_edu_eval_v1.jsonl"
DEFAULT_MANIFEST = REPO_ROOT / "backend" / "evaluation" / "legal_edu_eval_v1_manifest.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "docs" / "LEGAL_EDU_EVAL_V1_AUDIT.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "docs" / "LEGAL_EDU_EVAL_V1_AUDIT.md"
CANDIDATES = ("E0_base_model", "E1_prompt_few_shot", "E2_trusted_rag", "E3_rag_finetuned_model")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def normalize(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def output_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(output_text(child) for child in value.values())
    if isinstance(value, list):
        return " ".join(output_text(child) for child in value)
    return str(value) if value is not None else ""


def parse_response_specs(values: list[str]) -> dict[str, Path]:
    output: dict[str, Path] = {}
    for value in values:
        candidate, separator, path = value.partition("=")
        if not separator or candidate not in CANDIDATES or not path:
            raise ValueError(f"response must be CANDIDATE=PATH; candidates={CANDIDATES}")
        output[candidate] = Path(path)
    return output


def _point_coverage(output_text: str, points: list[dict[str, Any]]) -> tuple[int, list[str]]:
    normalized = normalize(output_text)
    missing = []
    passed = 0
    for point in points:
        matched = any(
            all(normalize(keyword) in normalized for keyword in group)
            for group in point["keyword_groups"]
        )
        if matched:
            passed += 1
        else:
            missing.append(point["point_id"])
    return passed, missing


def score_response(item: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    output = response.get("output")
    schema_success = isinstance(output, dict) and isinstance(output.get("answer"), str)
    if not schema_success:
        return {
            "task_id": item["task_id"],
            "schema_success": False,
            "point_coverage": 0.0,
            "evidence_scope_pass": False,
            "exact_quote_pass": False,
            "forbidden_output_pass": False,
            "abstention_behavior_pass": False,
            "automatic_gate_pass": False,
            "latency_ms": response.get("latency_ms"),
            "input_tokens": response.get("input_tokens"),
            "output_tokens": response.get("output_tokens"),
            "cost": response.get("cost"),
            "human_review_status": "pending",
            "errors": ["response_schema_invalid"],
        }
    serialized = json.dumps(output, ensure_ascii=False, sort_keys=True)
    semantic_text = output_text(output)
    passed_points, missing_points = _point_coverage(semantic_text, item["required_points"])
    point_coverage = passed_points / len(item["required_points"]) if item["required_points"] else 1.0
    evidence_by_id = {row["evidence_id"]: row for row in item["standard_evidence"]}
    citations = output.get("citations") or []
    citation_rows = []
    for citation in citations:
        evidence_id = str(citation.get("evidence_id") or "") if isinstance(citation, dict) else ""
        quote = str(citation.get("quote") or "") if isinstance(citation, dict) else ""
        evidence = evidence_by_id.get(evidence_id)
        citation_rows.append(
            {
                "evidence_id": evidence_id,
                "in_scope": evidence is not None,
                "exact_quote": bool(
                    evidence and normalize(quote) and normalize(quote) in normalize(evidence["quote"])
                ),
            }
        )
    evidence_scope_pass = all(row["in_scope"] for row in citation_rows)
    exact_quote_pass = all(row["exact_quote"] for row in citation_rows)
    if item["standard_evidence"]:
        evidence_scope_pass = evidence_scope_pass and bool(citation_rows)
        exact_quote_pass = exact_quote_pass and bool(citation_rows)
    forbidden_hits = [value for value in item["forbidden_outputs"] if value in semantic_text]
    forbidden_output_pass = not forbidden_hits
    must_abstain = "must_abstain" in item["risk_labels"]
    abstained = output.get("abstained") is True
    abstention_behavior_pass = abstained if must_abstain else True
    automatic_gate_pass = all(
        [
            schema_success,
            point_coverage == 1.0,
            evidence_scope_pass,
            exact_quote_pass,
            forbidden_output_pass,
            abstention_behavior_pass,
        ]
    )
    errors = []
    if missing_points:
        errors.append("missing_required_points")
    if not evidence_scope_pass:
        errors.append("evidence_scope_failed")
    if not exact_quote_pass:
        errors.append("exact_quote_failed")
    if forbidden_hits:
        errors.append("forbidden_output")
    if not abstention_behavior_pass:
        errors.append("required_abstention_missing")
    return {
        "task_id": item["task_id"],
        "schema_success": schema_success,
        "point_coverage": round(point_coverage, 6),
        "missing_point_ids": missing_points,
        "evidence_scope_pass": evidence_scope_pass,
        "exact_quote_pass": exact_quote_pass,
        "citation_audit": citation_rows,
        "forbidden_output_pass": forbidden_output_pass,
        "forbidden_hits": forbidden_hits,
        "abstention_behavior_pass": abstention_behavior_pass,
        "automatic_gate_pass": automatic_gate_pass,
        "latency_ms": response.get("latency_ms"),
        "input_tokens": response.get("input_tokens"),
        "output_tokens": response.get("output_tokens"),
        "cost": response.get("cost"),
        "human_review_status": "pending",
        "errors": errors,
    }


def summarize(rows: list[dict[str, Any]], items: dict[str, dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    def rate(key: str) -> float | None:
        return round(sum(bool(row.get(key)) for row in rows) / count, 6) if count else None
    latency = [float(row["latency_ms"]) for row in rows if row.get("latency_ms") is not None]
    input_tokens = sum(int(row.get("input_tokens") or 0) for row in rows)
    output_tokens = sum(int(row.get("output_tokens") or 0) for row in rows)
    costs = [float(row["cost"]) for row in rows if row.get("cost") is not None]
    by_type: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[items[row["task_id"]]["task_type"]].append(row)
    for task_type, group in sorted(grouped.items()):
        by_type[task_type] = {
            "count": len(group),
            "automatic_gate_rate": round(
                sum(row["automatic_gate_pass"] for row in group) / len(group), 6
            ),
            "mean_point_coverage": round(
                sum(row["point_coverage"] for row in group) / len(group), 6
            ),
        }
    return {
        "response_count": count,
        "coverage_of_100": round(count / 100, 6),
        "schema_success_rate": rate("schema_success"),
        "evidence_scope_rate": rate("evidence_scope_pass"),
        "exact_quote_rate": rate("exact_quote_pass"),
        "forbidden_output_pass_rate": rate("forbidden_output_pass"),
        "abstention_behavior_rate": rate("abstention_behavior_pass"),
        "automatic_gate_rate": rate("automatic_gate_pass"),
        "mean_required_point_coverage": (
            round(sum(row["point_coverage"] for row in rows) / count, 6) if count else None
        ),
        "latency_ms_mean": round(sum(latency) / len(latency), 3) if latency else None,
        "input_tokens": input_tokens if rows else None,
        "output_tokens": output_tokens if rows else None,
        "cost_total": round(sum(costs), 8) if costs else None,
        "human_score": "pending",
        "by_task_type": by_type,
        "error_counts": dict(sorted(Counter(error for row in rows for error in row["errors"]).items())),
    }


def run_evaluation(
    *,
    dataset_path: Path,
    manifest_path: Path,
    response_paths: dict[str, Path],
) -> dict[str, Any]:
    dataset = read_jsonl(dataset_path)
    item_by_id = {row["task_id"]: row for row in dataset}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidates: dict[str, Any] = {}
    for candidate in CANDIDATES:
        response_path = response_paths.get(candidate)
        if response_path is None:
            candidates[candidate] = {
                "status": "pending_model_delivery" if candidate == "E3_rag_finetuned_model" else "pending",
                "metrics": summarize([], item_by_id),
                "responses": [],
            }
            continue
        raw_rows = read_jsonl(response_path)
        seen: set[str] = set()
        scored = []
        unknown = []
        for response in raw_rows:
            task_id = str(response.get("task_id") or "")
            if task_id not in item_by_id:
                unknown.append(task_id)
                continue
            if task_id in seen:
                raise ValueError(f"duplicate response task_id: {task_id}")
            seen.add(task_id)
            scored.append(score_response(item_by_id[task_id], response))
        candidates[candidate] = {
            "status": "evaluated_partial" if len(scored) < len(dataset) else "evaluated_complete",
            "response_file": response_path.name,
            "unknown_task_ids": unknown,
            "metrics": summarize(scored, item_by_id),
            "responses": scored,
        }
    return {
        "schema_version": "legal-edu-eval-run-report-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_id": manifest["dataset_id"],
        "dataset_status": manifest["status"],
        "dataset_counts": manifest["counts"],
        "candidates": candidates,
        "expert_review_status": "pending",
        "learning_effect_status": "not_evaluated",
        "boundary": [
            "automatic keyword and citation gates are not semantic legal correctness",
            "all benchmark items remain candidate_requires_legal_review and not_gold",
            "missing model columns remain pending and are never filled with simulated scores",
            "this benchmark does not measure student learning gain",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# LegalEduEval-v1候选评测审计",
        "",
        "## 数据集",
        "",
        f"- 候选题：{report['dataset_counts']['items']}题",
        f"- split：dev {report['dataset_counts']['by_split'].get('dev', 0)} / test {report['dataset_counts']['by_split'].get('test', 0)}",
        f"- 跨split来源家族重叠：{report['dataset_counts']['cross_split_family_overlap']}",
        "- 当前状态：candidate_requires_legal_review / not_gold",
        "",
        "## E0—E3状态",
        "",
        "| 方案 | 状态 | 自动门禁率 | 人工评分 |",
        "|---|---|---:|---|",
    ]
    for candidate in CANDIDATES:
        row = report["candidates"][candidate]
        rate = row["metrics"]["automatic_gate_rate"]
        lines.append(f"| {candidate} | {row['status']} | {rate if rate is not None else '—'} | pending |")
    lines.extend(
        [
            "",
            "## 证据边界",
            "",
            "- 当前报告验证100题结构、数量、来源家族隔离和Runner pending语义，不包含虚构模型成绩。",
            "- 自动关键词/引文门禁不能替代法学教师对争点、涵摄、反馈和争议观点的评分。",
            "- E3等待队友Qwen3-8B模型交付；交付前保持pending_model_delivery。",
            "- 本评测不证明学生学习效果。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--response", action="append", default=[], help="CANDIDATE=JSONL")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    args = parser.parse_args()
    report = run_evaluation(
        dataset_path=args.dataset,
        manifest_path=args.manifest,
        response_paths=parse_response_specs(args.response),
    )
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    args.output_md.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    print(json.dumps({key: value["status"] for key, value in report["candidates"].items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
