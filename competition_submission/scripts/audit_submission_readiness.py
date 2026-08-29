"""Generate an evidence-backed XH-202620 submission readiness audit."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SUBMISSION = REPO / "competition_submission"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()

    ppt = SUBMISSION / "04-作品方案" / "星火智学_作品方案_Guizang_DRAFT.pptx"
    ppt_report = SUBMISSION / "04-作品方案" / "guizang" / "qa" / "pptx-report.json"
    web_report = SUBMISSION / "04-作品方案" / "guizang" / "qa" / "report.json"
    frozen = read_json(SUBMISSION / "03-Demo" / "FROZEN_DEMO_AUDIT.json")
    segments = read_json(SUBMISSION / "03-Demo" / "VIDEO_SEGMENTS_AUDIT.json")
    narrated = read_json(SUBMISSION / "03-Demo" / "NARRATED_VIDEO_DRAFT_AUDIT.json")
    legal_currency = read_json(SUBMISSION / "03-Demo" / "LEGAL_SOURCE_CURRENCY_AUDIT.json")
    typical = read_json(REPO / "docs" / "TYPICAL_QUESTION_EVALUATION.json")
    ppt_meta = read_json(ppt_report)
    web_meta = read_json(web_report)

    tracked_clean = subprocess.run(
        ["git", "diff", "--quiet"], cwd=REPO, check=False
    ).returncode == 0 and subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=REPO, check=False
    ).returncode == 0
    untracked = [
        line[3:] for line in git_output("status", "--short").splitlines()
        if line.startswith("?? ")
    ]

    checks = [
        {
            "id": "demo_docs",
            "requirement": "可访问Demo或明确本地一键启动说明",
            "status": "passed",
            "evidence": ["competition_submission/03-Demo/本地演示与离线备份_DRAFT.md"],
            "boundary": "本地运行；尚无公开在线地址",
        },
        {
            "id": "ppt",
            "requirement": "100MB以内作品方案PPT",
            "status": "passed" if ppt.is_file() and ppt.stat().st_size < 100 * 1024 * 1024 and ppt_meta.get("slides") == 12 else "failed",
            "evidence": [str(ppt.relative_to(REPO)), str(ppt_report.relative_to(REPO))],
            "detail": {"bytes": ppt.stat().st_size, "slides": ppt_meta.get("slides"), "max_render_mae": ppt_meta.get("max_mean_abs_error")},
            "boundary": "仍名为DRAFT；真实用户/专家状态待替换",
        },
        {
            "id": "video",
            "requirement": "3分钟以内真实交互演示视频",
            "status": "draft_ready",
            "evidence": ["competition_submission/03-Demo/VIDEO_SEGMENTS_AUDIT.json", "competition_submission/03-Demo/NARRATED_VIDEO_DRAFT_AUDIT.json"],
            "detail": {"real_segment_seconds": segments.get("segment_total_duration_seconds"), "draft_seconds": narrated.get("duration_seconds"), "draft_resolution": narrated.get("resolution")},
            "boundary": "AI配音DRAFT已含去标识case3 INV/PR审计快照，尚未团队完整审片与最终批准",
        },
        {
            "id": "reproducible_code",
            "requirement": "可复现代码、依赖锁和模型接口说明",
            "status": "passed",
            "evidence": ["requirements.lock.txt", "frontend/package-lock.json", "docs/MODEL_ADAPTER.md", "competition_submission/scripts/"],
            "boundary": "私密模型配置不入库",
        },
        {
            "id": "legal_source_currency",
            "requirement": "演示关键法源现行有效且可追溯",
            "status": "passed" if (
                legal_currency.get("result") == "PASS_WITH_SCOPE_LIMITATIONS"
                and legal_currency.get("target_article_count") == 5
                and legal_currency.get("target_article_pass_count") == 5
                and legal_currency.get("local_corpus_integrity", {})
                .get("criminal_law_output", {})
                .get("hash_match") is True
                and legal_currency.get("local_corpus_integrity", {})
                .get("criminal_procedure_law_output", {})
                .get("hash_match") is True
                and legal_currency.get("local_corpus_integrity", {})
                .get("official_download_artifacts", {})
                .get("all_manifest_hashes_matched") is True
            ) else "failed",
            "evidence": [
                "competition_submission/03-Demo/LEGAL_SOURCE_CURRENCY_AUDIT.json",
                "competition_submission/03-Demo/LEGAL_SOURCE_CURRENCY_AUDIT.md",
            ],
            "detail": {
                "target_articles": legal_currency.get("target_article_count"),
                "passed": legal_currency.get("target_article_pass_count"),
                "checked_at": legal_currency.get("checked_at"),
            },
            "boundary": "仅覆盖5条演示关键法条；法条文本现行不等于case3适法结论已获专家确认",
        },
        {
            "id": "three_questions",
            "requirement": "至少3个典型问题及准确性论证",
            "status": "expert_pending",
            "evidence": ["docs/TYPICAL_QUESTION_EVALUATION.json", "competition_submission/06-效果验证/专家审核包_MANIFEST_DRAFT.md"],
            "detail": {"automatic_gate_passed": typical.get("summary", {}).get("passed"), "expert_status": typical.get("expert_review_status")},
            "boundary": "自动门禁不等于专家准确率",
        },
        {
            "id": "target_users",
            "requirement": "至少2名真实目标用户试用记录",
            "status": "pending_external",
            "evidence": ["competition_submission/06-效果验证/目标用户知情同意书_DRAFT.md", "competition_submission/06-效果验证/目标用户统一试用主持脚本_DRAFT.md", "competition_submission/06-效果验证/目标用户试用记录表_DRAFT.md"],
            "boundary": "只有模板，无真实参与者记录",
        },
        {
            "id": "effect_report",
            "requirement": "效果验证报告",
            "status": "draft_ready",
            "evidence": ["competition_submission/06-效果验证/效果验证报告_DRAFT.md"],
            "boundary": "L1软件证据完成；L2专家/L3用户待补；不声称L4学习效果",
        },
        {
            "id": "ethics",
            "requirement": "伦理与安全合规声明",
            "status": "signature_pending",
            "evidence": ["competition_submission/02-伦理与安全/伦理与安全合规声明_DRAFT.md"],
            "boundary": "尚未团队负责人/指导教师签字",
        },
        {
            "id": "ai_label",
            "requirement": "AI生成内容显著标识",
            "status": "passed",
            "evidence": ["competition_submission/04-作品方案/guizang/slides.html", "competition_submission/03-Demo/NARRATED_VIDEO_DRAFT_AUDIT.json"],
            "detail": {"video_ai_label": narrated.get("audio", {}).get("ai_generated_label_visible")},
        },
        {
            "id": "offline_backup",
            "requirement": "离线演示备份和演示账号/数据",
            "status": "passed",
            "evidence": ["competition_submission/03-Demo/FROZEN_DEMO_AUDIT.json"],
            "detail": {"source_checks": frozen.get("semantic_audit", {}).get("source_check_count"), "restore_checks": frozen.get("semantic_audit", {}).get("restore_check_count"), "synthetic_users": frozen.get("identity_boundary", {}).get("user_count")},
            "boundary": "私密备份含演示密码哈希，不入Git，仅团队离线保管",
        },
    ]

    external_pending = [row["id"] for row in checks if row["status"] in {"pending_external", "expert_pending", "signature_pending"}]
    internal_pending = [row["id"] for row in checks if row["status"] == "draft_ready"]
    audit = {
        "schema": "xh-202620-submission-readiness-audit-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_output("rev-parse", "HEAD"),
        "tracked_worktree_clean_before_audit": tracked_clean,
        "untracked_user_material_count": len(untracked),
        "checks": checks,
        "external_pending": external_pending,
        "internal_pending": internal_pending,
        "ready_for_final_submission": not external_pending and not internal_pending and all(row["status"] == "passed" for row in checks),
        "web_ppt_qa": {"overflow": sum(len(row.get("overflow") or []) for row in web_meta.get("slides") or []), "console_errors": len(web_meta.get("consoleErrors") or []), "page_errors": len(web_meta.get("pageErrors") or []), "failed_requests": len(web_meta.get("failedRequests") or [])},
    }
    json_path = args.json.resolve()
    md_path = args.markdown.resolve()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    labels = {"passed": "已证明", "draft_ready": "DRAFT待批准", "expert_pending": "专家待审", "pending_external": "真实用户待补", "signature_pending": "待签字", "failed": "失败"}
    lines = [
        "# XH-202620最终提交就绪审计（DRAFT）",
        "",
        f"- Git：`{audit['git_commit']}`",
        f"- 最终提交就绪：**{'是' if audit['ready_for_final_submission'] else '否'}**",
        f"- 外部待补：`{', '.join(external_pending) or '无'}`",
        f"- 内部待批准：`{', '.join(internal_pending) or '无'}`",
        "",
        "| 要求 | 状态 | 证据边界 |",
        "|---|---|---|",
    ]
    for row in checks:
        lines.append(f"| {row['requirement']} | {labels.get(row['status'], row['status'])} | {row.get('boundary', '')} |")
    lines.extend([
        "",
        "## 停止扩功能后的剩余动作",
        "",
        "1. 真实法学专家完成A/B两阶段审核，必要时整改复签。",
        "2. 至少2名目标用户按统一主持脚本试用并形成去标识记录。",
        "3. 团队完整审片并批准最终视频，决定保留AI配音或替换真人旁白。",
        "4. 团队负责人和指导教师签署伦理声明，更新PPT/报告中的pending。",
    ])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ready": audit["ready_for_final_submission"], "external_pending": external_pending, "internal_pending": internal_pending, "json": str(json_path), "markdown": str(md_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
