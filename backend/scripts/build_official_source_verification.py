"""Build 2,024 incremental official-source verification records."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from src.hybrid_rag.official_verification import (  # noqa: E402
    build_verification_records,
    read_jsonl,
    summarize_records,
    write_jsonl,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", type=Path, default=REPO / ".codex-artifacts" / "hybrid-rag-corpus-v1" / "canonical_documents.jsonl")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(os.environ["EDUBRAIN_DATA_ROOT"]) if os.environ.get("EDUBRAIN_DATA_ROOT") else None,
        help="EduBrain data root; defaults to EDUBRAIN_DATA_ROOT when set",
    )
    parser.add_argument("--agent-record", type=Path, action="append", default=[])
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--output", type=Path, default=REPO / "data_governance" / "OFFICIAL_SOURCE_VERIFICATION_V1.jsonl")
    parser.add_argument("--summary", type=Path, default=REPO / "data_governance" / "OFFICIAL_SOURCE_VERIFICATION_V1_SUMMARY.json")
    parser.add_argument("--unresolved-output", type=Path, default=REPO / "data_governance" / "OFFICIAL_SOURCE_UNRESOLVED_V1.jsonl")
    parser.add_argument("--report", type=Path, default=REPO / "data_governance" / "OFFICIAL_SOURCE_VERIFICATION_V1_REPORT.md")
    parser.add_argument(
        "--npc-recheck-summary",
        type=Path,
        default=REPO / "data_governance" / "NPC_LAW_STATUS_RECHECK_V1.json",
    )
    args = parser.parse_args()
    if args.source_root is None:
        parser.error("--source-root or EDUBRAIN_DATA_ROOT is required")
    canonical = read_jsonl(args.canonical.resolve())
    previous = read_jsonl(args.previous.resolve()) if args.previous and args.previous.is_file() else []
    agents = []
    for path in args.agent_record:
        if path.is_file():
            agents.extend(read_jsonl(path.resolve()))
    rows = build_verification_records(
        canonical,
        source_root=args.source_root.resolve(),
        agent_rows=agents,
        previous_rows=previous,
    )
    schema = json.loads((REPO / "schemas" / "official-source-verification-v1.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = [error.message for row in rows for error in validator.iter_errors(row)]
    if errors:
        raise ValueError(f"verification schema errors: {errors[:3]}")
    write_jsonl(args.output.resolve(), rows)
    summary = summarize_records(rows)
    summary["agent_record_files_used"] = [path.name for path in args.agent_record if path.is_file()]
    npc_recheck = (
        json.loads(args.npc_recheck_summary.read_text(encoding="utf-8"))
        if args.npc_recheck_summary.is_file()
        else {}
    )
    if npc_recheck:
        summary["npc_law_status_recheck"] = {
            key: npc_recheck.get(key)
            for key in (
                "input_records",
                "official_api_success",
                "official_api_unavailable",
                "status_conflicts_with_previous",
                "status_mapping",
            )
        }
    summary["schema_errors"] = 0
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    unresolved = [
        {
            "document_id": row["document_id"],
            "source_type": row["source_type"],
            "title": row["title"],
            "issuing_authority": row["issuing_authority"],
            "promulgated_date": row["promulgated_date"],
            "effective_date": row["effective_date"],
            "verification_status": row["verification_status"],
            "source_use": row["source_use"],
        }
        for row in rows
        if row["effective_status"] == "unresolved"
    ]
    write_jsonl(args.unresolved_output.resolve(), unresolved)
    statuses = summary["by_effective_status"]
    coverage = summary["metadata_coverage"]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        "\n".join(
            [
                "# 2,024份官方法律资料来源与效力元数据报告",
                "",
                "## 结果",
                "",
                f"- 逐份验证记录：{summary['documents']:,} / 2,024；",
                f"- raw原件对应：{summary['local_source_matched']:,} / 2,024；",
                f"- 当前有效：{statuses.get('verified_current', 0):,}；",
                f"- 已核实历史发布：{statuses.get('verified_historical', 0):,}；",
                f"- 已被替代：{statuses.get('superseded', 0):,}；",
                f"- 已废止：{statuses.get('repealed', 0):,}；",
                f"- 效力尚未完全核实：{statuses.get('unresolved', 0):,}；",
                "- unresolved不阻塞检索或演示，但在引用详情与模型提示中必须显示效力提示。",
                "",
                "## 来源类型",
                "",
                *[f"- {key}: {value:,}" for key, value in summary["by_source_type"].items()],
                "",
                "## 元数据覆盖",
                "",
                *[f"- {key}: {value:,} / 2,024" for key, value in coverage.items()],
                "",
                "## 国家库法律状态码复核",
                "",
                f"- 法律输入：{npc_recheck.get('input_records', 0):,}；",
                f"- 本轮官方详情API成功：{npc_recheck.get('official_api_success', 0):,}；",
                f"- 官方API限流/暂不可用并保留前轮状态：{npc_recheck.get('official_api_unavailable', 0):,}；",
                f"- 与前轮官方核实状态冲突：{npc_recheck.get('status_conflicts_with_previous', 0):,}；",
                "- 国家库前端枚举：1已废止、2已修改、3有效、4尚未生效；官方成功结果优先，瞬时失败不得降级既有状态。",
                "",
                "## 使用原则",
                "",
                "- 国家法律法规数据库等官方来源原件默认准入，不因缺少详情页或个别日期字段而隔离；",
                "- 法律与行政法规用于规范依据，行政法规不得覆盖法律；",
                "- 司法解释和司法规范性文件用于司法适用；",
                "- 指导性/典型案例用于裁判参考与事实适用示例，不包装成法条；",
                "- 教材用于学理与课堂解释，公开题用于相似题和诊断任务；",
                "- verified_historical、superseded和repealed只用于沿革或比较，不得单独支持现行法结论；",
                "- unresolved可检索并显示效力元数据待完善；它是非阻断提示，不代表来源不可信，也不触发逐份联网或模型深挖；如果缺少现行高层级依据，应当弃权或提示复核；",
                "- 私有答案层不检索、不Embedding；",
                "- 官方信息与模型判断冲突时采用官方信息。",
                "",
                "## 证据边界",
                "",
                "本报告证明每份canonical资料都有核实记录和明确使用身份，不证明检索相关材料必然支持具体法律结论。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
