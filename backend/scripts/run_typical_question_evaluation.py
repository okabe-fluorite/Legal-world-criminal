"""Evaluate three governed criminal-law questions with auditable sources.

The automated gate verifies output structure, required point phrases, citation
scope, and exact quotes. It does not replace independent law-teacher review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
for entry in (REPO_ROOT, BACKEND_DIR):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from src.case_bundle.service import CaseBundleService  # noqa: E402
from src.knowledge.service import KnowledgeService  # noqa: E402

DEFAULT_SUITE = REPO_ROOT / "backend" / "evaluation" / "typical_questions.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _extract_json(value: str) -> dict[str, Any] | None:
    raw = str(value or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _apply_model_config(path: Path | None) -> None:
    if path is None:
        return
    from start import apply_grouped_model_config

    env = apply_grouped_model_config(dict(os.environ), path.resolve())
    for key in (
        "OPENAI_API_KEY",
        "OPENAI_API_BASE_URL",
        "OPENAI_MODEL_NAME",
        "SIMLAW_FALLBACK_MODEL_API_KEY",
        "SIMLAW_FALLBACK_MODEL_API_BASE_URL",
        "SIMLAW_FALLBACK_MODEL_NAME",
        "SIMLAW_FALLBACK_MODEL_TIMEOUT_SECONDS",
        "SIMLAW_FALLBACK_CIRCUIT_SECONDS",
    ):
        if str(env.get(key) or "").strip():
            os.environ[key] = env[key]


def _generate(prompt: str) -> tuple[str, dict[str, Any]]:
    from camel.agents import ChatAgent
    from camel.messages import BaseMessage
    from src.utils.model_config import build_camel_model

    model, endpoint = build_camel_model("learning_support", temperature=0.1, max_tokens=1800)
    agent = ChatAgent(
        system_message=(
            "你是本科刑法可信问答基线。只能使用提供的Sources，禁止补造事实、法条或案例；"
            "只返回合法JSON。答案必须简洁呈现规则、适用步骤、结论和争议边界。"
        ),
        model=model,
    )
    response = agent.step(BaseMessage.make_user_message(role_name="student", content=prompt))
    return response.msgs[0].content, endpoint.safe_dict()


def _sources_for(
    case: dict[str, Any],
    knowledge: KnowledgeService,
    bundles: CaseBundleService,
) -> list[dict[str, Any]]:
    sources = []
    card = knowledge.card_by_id[case["knowledge_id"]]
    sources.append(
        {
            "source_id": f"CARD_{card['knowledge_id']}",
            "source_type": "teacher_gated_knowledge_card",
            "title": card["canonical_name"],
            "article_ref": "课程口径",
            "quote": f"{card['learning_objective']} {card['summary']}",
            "authority": "本科刑法试点知识卡",
            "version": card["content_sha256"],
            "source_url": "",
        }
    )
    for evidence_id in case["required_source_ids"]:
        if evidence_id.startswith("CASE_GUIDE_"):
            continue
        row = knowledge.evidence_by_id[evidence_id]
        sources.append(
            {
                "source_id": row["evidence_id"],
                "source_type": row["source_type"],
                "title": row["source_title"],
                "article_ref": row["article_ref"],
                "quote": row["quote"],
                "authority": row["authority_level"],
                "version": row["source_snapshot_id"],
                "source_url": row["source_url"],
                "source_bundle_sha256": row["source_bundle_sha256"],
            }
        )
    bundle_id = str(case.get("case_bundle_id") or "")
    if bundle_id:
        bundle = bundles.by_bundle_id[bundle_id]
        guiding = str((bundle.get("reference_private") or {}).get("guiding_points") or "")
        if guiding:
            sources.append(
                {
                    "source_id": f"CASE_GUIDE_{bundle_id}",
                    "source_type": "guiding_case_point",
                    "title": bundle["title"],
                    "article_ref": bundle["provenance"]["source_reference"],
                    "quote": guiding,
                    "authority": bundle["provenance"]["issuing_authority"],
                    "version": bundle["content_sha256"],
                    "source_url": bundle["provenance"]["source_url"],
                    "local_source_sha256": bundle["provenance"]["local_source_sha256"],
                }
            )
    return sources


def _prompt(case: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    schema = {
        "answer": "string",
        "rule_steps": ["string"],
        "conclusion": "string",
        "citations": [
            {
                "source_id": "EVID_... or CASE_GUIDE_...",
                "title": "string",
                "article_ref": "string",
                "quote": "必须是Sources中quote的逐字片段",
            }
        ],
        "uncertainty": "string",
        "confidence": 0.0,
        "ai_generated": True,
    }
    return (
        "【规则】只能使用Sources；每个关键结论必须引用source_id与逐字quote。"
        "无法由Sources支持时必须在uncertainty中说明，不得猜测。\n"
        f"【Question】{case['question']}\n"
        f"【Sources】{json.dumps(sources, ensure_ascii=False)}\n"
        f"【OutputSchema】{json.dumps(schema, ensure_ascii=False)}"
    )


def _point_audit(answer: str, case: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = _normalize(answer)
    rows = []
    for point in case["required_points"]:
        matched_group = next(
            (
                group
                for group in point["keyword_groups"]
                if all(_normalize(keyword) in normalized for keyword in group)
            ),
            None,
        )
        rows.append(
            {
                "point_id": point["point_id"],
                "label": point["label"],
                "passed": matched_group is not None,
                "matched_keywords": matched_group or [],
            }
        )
    return rows


def _citation_audit(
    payload: dict[str, Any],
    sources: list[dict[str, Any]],
    required_source_ids: list[str],
) -> dict[str, Any]:
    source_by_id = {row["source_id"]: row for row in sources}
    rows = []
    valid_ids = set()
    for citation in payload.get("citations") or []:
        source_id = str(citation.get("source_id") or "") if isinstance(citation, dict) else ""
        source = source_by_id.get(source_id)
        quote = str(citation.get("quote") or "") if isinstance(citation, dict) else ""
        exact = bool(source and quote and _normalize(quote) in _normalize(source["quote"]))
        if exact:
            valid_ids.add(source_id)
        rows.append(
            {
                "source_id": source_id,
                "in_allowed_sources": source is not None,
                "exact_quote": exact,
                "quote": quote,
            }
        )
    missing = [source_id for source_id in required_source_ids if source_id not in valid_ids]
    return {
        "citations": rows,
        "valid_source_ids": sorted(valid_ids),
        "missing_required_source_ids": missing,
        "passed": bool(rows) and not missing and all(row["exact_quote"] for row in rows),
    }


def evaluate_case(
    case: dict[str, Any],
    *,
    knowledge: KnowledgeService,
    bundles: CaseBundleService,
    live_model: bool,
    reused_output: dict[str, Any] | None = None,
    reused_route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sources = _sources_for(case, knowledge, bundles)
    allowed = {row["source_id"] for row in sources}
    missing_inputs = [value for value in case["required_source_ids"] if value not in allowed]
    if missing_inputs:
        raise ValueError(f"{case['case_id']} missing governed sources: {missing_inputs}")
    if not live_model and reused_output is None:
        return {
            **case,
            "sources": sources,
            "run_status": "retrieval_only",
            "model_output": None,
            "automated_gate_pass": False,
            "expert_review_status": "pending",
        }
    if reused_output is None:
        raw, route = _generate(_prompt(case, sources))
        payload = _extract_json(raw)
    else:
        payload = dict(reused_output)
        route = dict(reused_route or {})
    structural = bool(
        payload
        and isinstance(payload.get("answer"), str)
        and isinstance(payload.get("rule_steps"), list)
        and isinstance(payload.get("conclusion"), str)
        and isinstance(payload.get("citations"), list)
        and isinstance(payload.get("uncertainty"), str)
        and isinstance(payload.get("confidence"), (int, float))
        and payload.get("ai_generated") is True
    )
    payload = payload or {}
    combined_answer = " ".join(
        [
            str(payload.get("answer") or ""),
            " ".join(str(value) for value in payload.get("rule_steps") or []),
            str(payload.get("conclusion") or ""),
        ]
    )
    points = _point_audit(combined_answer, case)
    citations = _citation_audit(payload, sources, case["required_source_ids"])
    coverage = sum(row["passed"] for row in points) / len(points)
    gate = structural and citations["passed"] and coverage == 1.0
    return {
        **case,
        "sources": sources,
        "run_status": "model_completed" if structural else "model_invalid_structure",
        "model_output": payload,
        "model_route": route,
        "structural_pass": structural,
        "point_audit": points,
        "point_coverage": round(coverage, 4),
        "citation_audit": citations,
        "automated_gate_pass": gate,
        "expert_review_status": "pending",
        "verified_accurate": False,
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# 三个典型问题可信RAG效果验证",
        "",
        f"- 生成时间：`{report['generated_at']}`",
        f"- 模式：`{report['mode']}`",
        f"- 自动门禁：{report['automated_gate_pass_count']}/{report['case_count']}",
        "- 法学专家复核：**PENDING**",
        "",
        "> 自动门禁只检查结构、标准要点关键词和逐字Evidence引用，不等于法学专家确认准确，也不证明课堂学习效果。",
        "",
        "| 案例 | 要点覆盖 | 引用门禁 | 自动门禁 | 专家复核 |",
        "|---|---:|---:|---:|---|",
    ]
    for row in report["cases"]:
        citation_pass = bool((row.get("citation_audit") or {}).get("passed"))
        lines.append(
            f"| {row['title']} | {float(row.get('point_coverage') or 0):.0%} | "
            f"{'PASS' if citation_pass else 'FAIL'} | "
            f"{'PASS' if row.get('automated_gate_pass') else 'FAIL'} | pending |"
        )
    for row in report["cases"]:
        lines.extend(
            [
                "",
                f"## {row['case_id']} {row['title']}",
                "",
                f"**问题：** {row['question']}",
                "",
                f"**系统输出：** {(row.get('model_output') or {}).get('answer') or '未调用模型'}",
                "",
                f"**标准答案：** {row['standard_answer']}",
                "",
                "**权威来源：** "
                + "；".join(
                    f"{source['title']} {source['article_ref']} ({source['authority']})"
                    for source in row["sources"]
                    if source["source_id"] in row["required_source_ids"]
                ),
                "",
                "**未完成证据：** 需由独立法学教师/法学研究生核对结论、适用步骤和争议边界，并记录姓名或去标识身份、日期与意见。",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "docs" / "TYPICAL_QUESTION_EVALUATION.json")
    parser.add_argument("--markdown-output", type=Path, default=REPO_ROOT / "docs" / "TYPICAL_QUESTION_EVALUATION.md")
    parser.add_argument("--model-config", type=Path)
    parser.add_argument("--live-model", action="store_true")
    parser.add_argument(
        "--reuse-report",
        type=Path,
        help="Re-audit existing model outputs without another model call.",
    )
    args = parser.parse_args()
    _apply_model_config(args.model_config)
    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    knowledge = KnowledgeService()
    bundles = CaseBundleService()
    reused_cases = {}
    if args.reuse_report:
        reused = json.loads(args.reuse_report.read_text(encoding="utf-8"))
        reused_cases = {row["case_id"]: row for row in reused.get("cases") or []}
    rows = [
        evaluate_case(
            case,
            knowledge=knowledge,
            bundles=bundles,
            live_model=args.live_model,
            reused_output=(reused_cases.get(case["case_id"]) or {}).get("model_output"),
            reused_route=(reused_cases.get(case["case_id"]) or {}).get("model_route"),
        )
        for case in suite["cases"]
    ]
    mode = (
        "live_model_reaudited"
        if args.reuse_report
        else "live_model"
        if args.live_model
        else "retrieval_only"
    )
    report = {
        "schema_version": "typical-question-evaluation-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "suite_sha256": _sha256(args.suite),
        "law_manifest_sha256": _sha256(
            REPO_ROOT / "backend" / "legal_corpus" / "processed" / "law_corpus_manifest.json"
        ),
        "case_bundle_manifest_sha256": _sha256(REPO_ROOT / "dataset" / "case_bundle_manifest.json"),
        "case_count": len(rows),
        "automated_gate_pass_count": sum(bool(row.get("automated_gate_pass")) for row in rows),
        "all_expert_reviews_complete": False,
        "cases": rows,
        "boundary": {
            "proves": "governed inputs, model output, point matching, and exact citation gates are reproducible",
            "does_not_prove": "independent legal correctness, learning gain, or classroom effectiveness",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(markdown_report(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "mode": report["mode"],
                "case_count": report["case_count"],
                "automated_gate_pass_count": report["automated_gate_pass_count"],
                "all_expert_reviews_complete": False,
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    if not args.live_model and not args.reuse_report:
        return 0
    return 0 if report["automated_gate_pass_count"] == report["case_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
