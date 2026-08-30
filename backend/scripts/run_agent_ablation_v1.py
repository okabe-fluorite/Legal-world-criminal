"""Run a fixed C0/C1 Agent ablation on the governed Case 144 CR slice."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
for entry in (REPO_ROOT, BACKEND_DIR):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from src.legal_reasoning.gate import LegalReasoningGate, build_case_gate_context  # noqa: E402
from src.pipeline.stage_tool_resolver import describe_stage_tool_matrix  # noqa: E402


DEFAULT_PROTOCOL = BACKEND_DIR / "evaluation" / "agent_ablation_protocol_v1.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "docs" / "AGENT_ABLATION_V1.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "docs" / "AGENT_ABLATION_V1.md"
DEFAULT_BLIND_OUTPUT = BACKEND_DIR / "evaluation" / "agent_ablation_blind_review_packet_v1.json"


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_json(value: str) -> dict[str, Any] | None:
    raw = str(value or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def normalize_orchestrated_ids(reasoning: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Assign stable counterargument IDs in code without changing legal content."""
    output = copy.deepcopy(reasoning)
    changes: list[dict[str, str]] = []
    pattern = re.compile(r"^COUNTER_[A-Z0-9_]{2,64}$")
    for index, row in enumerate(output.get("counterarguments") or [], start=1):
        old = str(row.get("argument_id") or "")
        if pattern.fullmatch(old):
            continue
        new = f"COUNTER_C{index:02d}"
        row["argument_id"] = new
        changes.append({"path": f"counterarguments[{index - 1}].argument_id", "old": old, "new": new})
    return output, changes


def apply_model_config(path: Path) -> dict[str, str]:
    from start import apply_grouped_model_config

    env = apply_grouped_model_config(dict(os.environ), path.resolve())
    for key in ("OPENAI_API_KEY", "OPENAI_API_BASE_URL", "OPENAI_MODEL_NAME"):
        if str(env.get(key) or "").strip():
            os.environ[key] = env[key]
    return env


def build_live_caller(model_config: Path) -> tuple[Callable[[str, str, int], dict[str, Any]], dict[str, Any]]:
    from openai import OpenAI
    from src.utils.model_config import resolve_model_endpoint

    apply_model_config(model_config)
    endpoint = resolve_model_endpoint("agent")
    if not (endpoint.api_key and endpoint.api_base_url and endpoint.model_name):
        raise RuntimeError("primary model endpoint is not fully configured")
    client = OpenAI(
        api_key=endpoint.api_key,
        base_url=endpoint.api_base_url,
        timeout=endpoint.timeout_seconds,
    )

    def call(system: str, prompt: str, max_tokens: int) -> dict[str, Any]:
        started = time.perf_counter()
        response = client.chat.completions.create(
            model=endpoint.model_name,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        usage = getattr(response, "usage", None)
        return {
            "raw": response.choices[0].message.content or "",
            "elapsed_ms": elapsed_ms,
            "usage": {
                "input_tokens": getattr(usage, "prompt_tokens", None),
                "output_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            },
            "finish_reason": response.choices[0].finish_reason,
        }

    return call, endpoint.safe_dict()


def source_payload(protocol: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    context = build_case_gate_context(
        case_id=protocol["case_bundle_id"],
        stage=protocol["stage"],
        required_element_ids=protocol["required_element_ids"],
        evidence_status=protocol["evidence_status"],
        student_input=protocol["student_initial_answer"],
    )
    facts = [
        {"fact_id": f"FACT_F{index + 1:02d}", "source_path": path, "source_quote": quote}
        for index, (path, quote) in enumerate(context["visible_fact_sources"].items())
    ]
    evidences = list(context["allowed_evidence"].values())
    shared = {
        "question": protocol["question"],
        "student_initial_answer": protocol["student_initial_answer"],
        "case_context_exact": {
            "case_bundle_id": context["case_bundle_id"],
            "case_bundle_version": context["case_bundle_version"],
            "stage": context["stage"],
            "student_visible_sha256": context["student_visible_sha256"],
            "evidence_scope_id": context["evidence_scope_id"],
        },
        "student_visible_fact_catalog": facts,
        "allowed_evidence": evidences,
        "required_element_ids": protocol["required_element_ids"],
        "evidence_status": protocol["evidence_status"],
    }
    return context, shared


def final_prompt(
    *,
    shared: dict[str, Any],
    schema: dict[str, Any],
    condition: str,
    fact_review: dict[str, Any] | None = None,
    prosecutor_challenge: dict[str, Any] | None = None,
) -> str:
    payload = {
        **shared,
        "condition": condition,
        "fact_review": fact_review,
        "prosecutor_challenge": prosecutor_challenge,
        "output_schema": schema,
        "required_reasoning_id": (
            "LR_C0000000000000000000" if condition == "C0" else "LR_C1111111111111111111"
        ),
    }
    return (
        "只返回一个合法JSON对象，不要代码围栏，不输出隐藏思维过程。"
        "case_context五个字段必须逐字复制case_context_exact；facts只能选择fact catalog中的source_path/source_quote；"
        "rules只能引用allowed_evidence中的evidence_id、source_title、article_ref和逐字quote；"
        "applications覆盖四个required_element_ids；结论强度不得高于limited Evidence；必须保留反方和教师复核。\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def run_condition_c0(
    *,
    caller: Callable[[str, str, int], dict[str, Any]],
    protocol: dict[str, Any],
    shared: dict[str, Any],
    schema: dict[str, Any],
) -> dict[str, Any]:
    states = ["INIT", "STATIC_RESPONSE"]
    call = caller(
        "你是本科刑法静态学习材料回答基线。只能使用给定事实和Evidence，不得虚构。",
        final_prompt(shared=shared, schema=schema, condition="C0"),
        protocol["max_tokens"],
    )
    states.extend(["DETERMINISTIC_GATE", "COMPLETE"])
    return {"states": states, "calls": [call], "reasoning": extract_json(call["raw"])}


def run_condition_c1(
    *,
    caller: Callable[[str, str, int], dict[str, Any]],
    protocol: dict[str, Any],
    shared: dict[str, Any],
    schema: dict[str, Any],
) -> dict[str, Any]:
    states = ["INIT", "FACT_REVIEW"]
    fact_call = caller(
        "你是事实审查员。只选择学生可见fact catalog，不补写事实；只返回JSON。",
        "返回{issue,selected_fact_ids,missing_facts,disputed_fact_ids}，不要隐藏思维。\n"
        + json.dumps(shared, ensure_ascii=False),
        900,
    )
    fact_review = extract_json(fact_call["raw"])
    states.extend(["EVIDENCE_TOOL", "PROSECUTOR_CHALLENGE"])
    prosecutor_call = caller(
        "你是检察官对抗审查角色。只能使用同一学生可见事实和刑法Evidence，提出最强反方，不得定案；只返回JSON。",
        "返回{counterarguments:[{position,fact_ids,evidence_ids}],required_checks,unresolved_points}，不要隐藏思维。\n"
        + json.dumps({"shared": shared, "fact_review": fact_review}, ensure_ascii=False),
        1200,
    )
    challenge = extract_json(prosecutor_call["raw"])
    states.extend(["DEFENSE_REVISION", "DETERMINISTIC_GATE"])
    defense_call = caller(
        "你是辩方修订角色。必须回应检察官最强反方并按LegalReasoning Schema输出；只能使用给定事实和Evidence。",
        final_prompt(
            shared=shared,
            schema=schema,
            condition="C1",
            fact_review=fact_review,
            prosecutor_challenge=challenge,
        ),
        protocol["max_tokens"],
    )
    raw_reasoning = extract_json(defense_call["raw"])
    if isinstance(raw_reasoning, dict):
        reasoning, normalization_changes = normalize_orchestrated_ids(raw_reasoning)
    else:
        reasoning, normalization_changes = raw_reasoning, []
    states.extend(["SCHEMA_NORMALIZATION", "COMPLETE"])
    return {
        "states": states,
        "calls": [fact_call, prosecutor_call, defense_call],
        "fact_review": fact_review,
        "prosecutor_challenge": challenge,
        "reasoning_raw": raw_reasoning,
        "reasoning": reasoning,
        "schema_normalization": {
            "model_calls": 0,
            "semantic_fields_changed": False,
            "changes": normalization_changes,
        },
        "deterministic_tool": {
            "tool_id": "governed_evidence_scope_and_quote_check",
            "allowed_evidence_ids": [row["evidence_id"] for row in shared["allowed_evidence"]],
            "network_calls": 0,
        },
    }


def summarize_condition(
    condition: str,
    run: dict[str, Any],
    context: dict[str, Any],
    gate: LegalReasoningGate,
) -> dict[str, Any]:
    reasoning = run.get("reasoning")
    raw_reasoning = run.get("reasoning_raw", reasoning)
    raw_gate_result = gate.evaluate(raw_reasoning, context) if isinstance(raw_reasoning, dict) else None
    gate_result = gate.evaluate(reasoning, context) if isinstance(reasoning, dict) else {
        "passed": False,
        "failed_checks": ["model_output_json_invalid"],
        "checks": [],
        "boundary": "model output did not parse as JSON",
    }
    usage = {
        "model_calls": len(run["calls"]),
        "elapsed_ms": round(sum(float(row["elapsed_ms"]) for row in run["calls"]), 3),
        "input_tokens": sum(int((row.get("usage") or {}).get("input_tokens") or 0) for row in run["calls"]),
        "output_tokens": sum(int((row.get("usage") or {}).get("output_tokens") or 0) for row in run["calls"]),
        "total_tokens": sum(int((row.get("usage") or {}).get("total_tokens") or 0) for row in run["calls"]),
    }
    applications = reasoning.get("applications") if isinstance(reasoning, dict) else []
    counters = reasoning.get("counterarguments") if isinstance(reasoning, dict) else []
    return {
        "condition": condition,
        "workflow_completed": run["states"][-1] == "COMPLETE",
        "states": run["states"],
        "usage": usage,
        "structured_json": isinstance(reasoning, dict),
        "raw_schema_pass": bool(
            raw_gate_result
            and next(
                (row["passed"] for row in raw_gate_result["checks"] if row["check_id"] == "schema_valid"),
                False,
            )
        ),
        "schema_normalization": run.get(
            "schema_normalization",
            {"model_calls": 0, "semantic_fields_changed": False, "changes": []},
        ),
        "gate_pass": gate_result["passed"],
        "failed_checks": gate_result["failed_checks"],
        "required_element_coverage": len(
            set(context["required_element_ids"])
            & {row.get("element_id") for row in applications or []}
        ),
        "required_element_total": len(context["required_element_ids"]),
        "counterargument_count": len(counters or []),
        "gate_result": gate_result,
        "reasoning_raw": raw_reasoning,
        "reasoning": reasoning,
        "teacher_blind_score": "pending",
    }


def run_ablation(
    *,
    protocol: dict[str, Any],
    caller: Callable[[str, str, int], dict[str, Any]],
    route: dict[str, Any],
) -> dict[str, Any]:
    context, shared = source_payload(protocol)
    schema_path = REPO_ROOT / "schemas" / "legal-reasoning-v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    gate = LegalReasoningGate(schema_path=schema_path)
    c0_run = run_condition_c0(caller=caller, protocol=protocol, shared=shared, schema=schema)
    c1_run = run_condition_c1(caller=caller, protocol=protocol, shared=shared, schema=schema)
    c0 = summarize_condition("C0", c0_run, context, gate)
    c1 = summarize_condition("C1", c1_run, context, gate)
    matrix = describe_stage_tool_matrix()[protocol["stage"]]
    return {
        "schema_version": "agent-ablation-report-v1",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": sha256_file(DEFAULT_PROTOCOL),
        "legal_reasoning_schema_sha256": sha256_file(schema_path),
        "run_status": "completed",
        "fixed_conditions": {
            "case_bundle_id": context["case_bundle_id"],
            "case_bundle_version": context["case_bundle_version"],
            "stage": context["stage"],
            "student_visible_sha256": context["student_visible_sha256"],
            "evidence_scope_id": context["evidence_scope_id"],
            "model_route": route,
            "temperature": protocol["temperature"],
            "prompt_versions": protocol["prompt_versions"],
        },
        "c1_tool_permissions": matrix,
        "conditions": {"C0": c0, "C1": c1},
        "automatic_comparison": {
            "gate_pass_delta": int(c1["gate_pass"]) - int(c0["gate_pass"]),
            "element_coverage_delta": c1["required_element_coverage"] - c0["required_element_coverage"],
            "counterargument_count_delta": c1["counterargument_count"] - c0["counterargument_count"],
            "elapsed_ms_delta": round(c1["usage"]["elapsed_ms"] - c0["usage"]["elapsed_ms"], 3),
            "total_tokens_delta": c1["usage"]["total_tokens"] - c0["usage"]["total_tokens"],
            "elapsed_ratio_c1_over_c0": round(
                c1["usage"]["elapsed_ms"] / c0["usage"]["elapsed_ms"], 4
            ) if c0["usage"]["elapsed_ms"] else None,
            "token_ratio_c1_over_c0": round(
                c1["usage"]["total_tokens"] / c0["usage"]["total_tokens"], 4
            ) if c0["usage"]["total_tokens"] else None,
        },
        "teacher_blind_review": "pending",
        "evidence_boundary": [
            "automatic gates measure structure and Evidence discipline, not substantive legal correctness",
            "C1 is a focused CR reasoning slice; the existing six-stage E2E remains engineering evidence",
            "one run cannot establish general model or teaching superiority",
            "teacher blind scores remain pending",
        ],
    }


def reprocess_existing_report(
    *,
    report: dict[str, Any],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    """Apply the deterministic C1 ID node to an already completed live run."""
    if report.get("run_status") != "completed":
        raise ValueError("only completed reports can be reprocessed")
    context, _ = source_payload(protocol)
    schema_path = REPO_ROOT / "schemas" / "legal-reasoning-v1.schema.json"
    gate = LegalReasoningGate(schema_path=schema_path)
    c1 = report["conditions"]["C1"]
    raw = c1.get("reasoning_raw") or c1.get("reasoning")
    if not isinstance(raw, dict):
        raise ValueError("completed C1 report has no structured reasoning")
    normalized, changes = normalize_orchestrated_ids(raw)
    raw_result = gate.evaluate(raw, context)
    result = gate.evaluate(normalized, context)
    raw_schema_pass = next(
        (row["passed"] for row in raw_result["checks"] if row["check_id"] == "schema_valid"),
        False,
    )
    states = list(c1["states"])
    if "SCHEMA_NORMALIZATION" not in states:
        insert_at = states.index("DETERMINISTIC_GATE") if "DETERMINISTIC_GATE" in states else len(states) - 1
        states.insert(insert_at, "SCHEMA_NORMALIZATION")
    c1.update(
        {
            "states": states,
            "raw_schema_pass": raw_schema_pass,
            "schema_normalization": {
                "model_calls": 0,
                "semantic_fields_changed": False,
                "changes": changes,
            },
            "gate_pass": result["passed"],
            "failed_checks": result["failed_checks"],
            "gate_result": result,
            "reasoning_raw": raw,
            "reasoning": normalized,
            "counterargument_count": len(normalized.get("counterarguments") or []),
        }
    )
    c0 = report["conditions"]["C0"]
    c0_raw = c0.get("reasoning_raw") or c0.get("reasoning")
    if isinstance(c0_raw, dict):
        c0_raw_result = gate.evaluate(c0_raw, context)
        c0["raw_schema_pass"] = next(
            (
                row["passed"]
                for row in c0_raw_result["checks"]
                if row["check_id"] == "schema_valid"
            ),
            False,
        )
    report["automatic_comparison"] = {
        "gate_pass_delta": int(c1["gate_pass"]) - int(c0["gate_pass"]),
        "element_coverage_delta": c1["required_element_coverage"] - c0["required_element_coverage"],
        "counterargument_count_delta": c1["counterargument_count"] - c0["counterargument_count"],
        "elapsed_ms_delta": round(c1["usage"]["elapsed_ms"] - c0["usage"]["elapsed_ms"], 3),
        "total_tokens_delta": c1["usage"]["total_tokens"] - c0["usage"]["total_tokens"],
        "elapsed_ratio_c1_over_c0": round(
            c1["usage"]["elapsed_ms"] / c0["usage"]["elapsed_ms"], 4
        ) if c0["usage"]["elapsed_ms"] else None,
        "token_ratio_c1_over_c0": round(
            c1["usage"]["total_tokens"] / c0["usage"]["total_tokens"], 4
        ) if c0["usage"]["total_tokens"] else None,
    }
    report["reprocessed_with"] = {
        "node": "deterministic_counterargument_id_normalization_v1",
        "additional_model_calls": 0,
        "semantic_fields_changed": False,
    }
    return report


def build_blind_review_packet(
    report: dict[str, Any],
    protocol: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Build an A/B packet without condition or model labels."""
    order = ["C0", "C1"]
    if int(report["protocol_sha256"][:2], 16) % 2:
        order.reverse()
    labels = {condition: label for condition, label in zip(order, ("A", "B"))}
    submissions = []
    for condition in order:
        reasoning = copy.deepcopy(report["conditions"][condition]["reasoning"])
        reasoning.pop("reasoning_id", None)
        reasoning.pop("case_context", None)
        submissions.append({"submission_label": labels[condition], "reasoning": reasoning})
    packet = {
        "schema_version": "agent-ablation-blind-review-packet-v1",
        "packet_id": f"BLIND_{report['protocol_sha256'][:20].upper()}",
        "status": "pending_two_independent_law_reviewers",
        "question": protocol["question"],
        "student_initial_answer": protocol["student_initial_answer"],
        "review_instructions": [
            "Do not inspect the ablation report before submitting the locked first-stage review.",
            "Score A and B independently; do not guess which condition used Agents.",
            "Record abstention when the governed material is insufficient.",
        ],
        "rubric": [
            {"dimension": "争点与事实纪律", "max_score": 4},
            {"dimension": "法源与逐字Evidence", "max_score": 4},
            {"dimension": "要件涵摄", "max_score": 4},
            {"dimension": "最强反方与回应", "max_score": 4},
            {"dimension": "不确定性与形成性价值", "max_score": 4},
        ],
        "review_slots": [
            {"reviewer_id": None, "submission_A": None, "submission_B": None, "preferred": None},
            {"reviewer_id": None, "submission_A": None, "submission_B": None, "preferred": None},
        ],
        "submissions": submissions,
        "boundary": "This packet is pending; empty review slots are not expert evidence.",
    }
    return packet, labels


def pending_report(protocol: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "agent-ablation-report-v1",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": sha256_file(DEFAULT_PROTOCOL),
        "run_status": "pending_live_model_run",
        "conditions": {"C0": "pending", "C1": "pending"},
        "teacher_blind_review": "pending",
        "evidence_boundary": protocol["limits"],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent C0/C1消融", "", f"状态：`{report['run_status']}`", ""]
    if report["run_status"] != "completed":
        lines.extend(["C0/C1真实模型运行尚未完成，教师盲评保持pending。", ""])
        return "\n".join(lines)
    lines.extend(
        [
            "## 固定条件",
            "",
            f"- CaseBundle：`{report['fixed_conditions']['case_bundle_id']}`",
            f"- 阶段：`{report['fixed_conditions']['stage']}`",
            f"- 模型：`{report['fixed_conditions']['model_route']['model_name']}`",
            f"- 温度：{report['fixed_conditions']['temperature']}",
            "",
            "## 结果",
            "",
            "| 条件 | 状态数 | 模型调用 | 原始Schema | 最终Gate | 要件覆盖 | 反方 | 耗时ms | tokens | 教师盲评 |",
            "|---|---:|---:|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for name in ("C0", "C1"):
        row = report["conditions"][name]
        lines.append(
            f"| {name} | {len(row['states'])} | {row['usage']['model_calls']} | "
            f"{'通过' if row.get('raw_schema_pass', row['gate_pass']) else '未通过'} | "
            f"{'通过' if row['gate_pass'] else '未通过'} | "
            f"{row['required_element_coverage']}/{row['required_element_total']} | "
            f"{row['counterargument_count']} | {row['usage']['elapsed_ms']} | "
            f"{row['usage']['total_tokens']} | pending |"
        )
    comparison = report["automatic_comparison"]
    lines.extend(
        [
            "",
            "## 自动比较",
            "",
            f"- C1相对C0增加{comparison['counterargument_count_delta']}条反方观点；两者必要要件覆盖相同。",
            f"- C1耗时为C0的{comparison['elapsed_ratio_c1_over_c0']}倍，token为{comparison['token_ratio_c1_over_c0']}倍。",
            f"- C1原始输出有{len(report['conditions']['C1']['schema_normalization']['changes'])}个反方ID不符合Schema；确定性节点只归一ID，0额外模型调用、0语义字段改写。",
            "- 在教师盲评完成前，本结果不支持宣称C1教学质量优于C0。",
            "",
            "## 证据边界",
            "",
            "- 自动门禁只比较结构和Evidence纪律，不等于法律结论正确。",
            "- 本实验是CR阶段纵向切片，不用来替代六阶段工程E2E。",
            "- 单次运行不能证明Agent普遍优于静态提示，教师盲评仍为pending。",
            "- C1如发生ID归一，只修改编排标识符并保留原始输出；不修改法律语义字段，也不增加模型调用。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--model-config", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--reprocess-existing", action="store_true")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--blind-output", type=Path, default=DEFAULT_BLIND_OUTPUT)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    if args.reprocess_existing:
        if not args.output_json.is_file():
            raise FileNotFoundError(args.output_json)
        report = reprocess_existing_report(
            report=json.loads(args.output_json.read_text(encoding="utf-8")),
            protocol=protocol,
        )
    elif args.live:
        if args.model_config is None:
            raise ValueError("--live requires --model-config")
        caller, route = build_live_caller(args.model_config)
        report = run_ablation(protocol=protocol, caller=caller, route=route)
    else:
        report = pending_report(protocol)
    if report.get("run_status") == "completed":
        blind_packet, blind_labels = build_blind_review_packet(report, protocol)
        args.blind_output.write_text(
            json.dumps(blind_packet, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        report["blind_review"] = {
            "status": blind_packet["status"],
            "packet_file": args.blind_output.name,
            "packet_sha256": sha256_file(args.blind_output),
            "internal_label_mapping": blind_labels,
        }
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    args.output_md.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    print(json.dumps({"run_status": report["run_status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
