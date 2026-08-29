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
    expert_package = read_json(SUBMISSION / "06-效果验证" / "专家审核包_DRAFT" / "MANIFEST.json")
    expert_package_audit = read_json(SUBMISSION / "06-效果验证" / "专家审核包_DRAFT" / "BUILD_AUDIT.json")
    user_trial_package = read_json(SUBMISSION / "06-效果验证" / "目标用户试用包_DRAFT" / "MANIFEST.json")
    user_trial_audit = read_json(SUBMISSION / "06-效果验证" / "目标用户试用包_DRAFT" / "BUILD_AUDIT.json")
    ethics_package = read_json(SUBMISSION / "02-伦理与安全" / "伦理签署包_DRAFT" / "MANIFEST.json")
    ethics_package_audit = read_json(SUBMISSION / "02-伦理与安全" / "伦理签署包_DRAFT" / "BUILD_AUDIT.json")
    video_review = read_json(SUBMISSION / "06-效果验证" / "视频审片包_DRAFT" / "MANIFEST.json")
    video_review_audit = read_json(SUBMISSION / "06-效果验证" / "视频审片包_DRAFT" / "BUILD_AUDIT.json")
    typical = read_json(REPO / "docs" / "TYPICAL_QUESTION_EVALUATION.json")
    ppt_meta = read_json(ppt_report)
    web_meta = read_json(web_report)
    video_qa = narrated.get("qa", {})
    video_audio_analysis = narrated.get("audio", {}).get("analysis", {})
    video_content = narrated.get("content_coverage", {})
    video_passed = (
        narrated.get("duration_seconds", 999) <= 180
        and narrated.get("resolution") == "1920x1080"
        and narrated.get("audio", {}).get("present") is True
        and narrated.get("audio", {}).get("ai_generated_label_visible") is True
        and narrated.get("subtitles", {}).get("present") is True
        and narrated.get("subtitles", {}).get("count") == 10
        and video_content.get("required_count") == 7
        and video_content.get("present_count") == 7
        and video_content.get("all_required_present") is True
        and video_qa.get("max_voice_speed_factor", 999) <= 1.1
        and video_audio_analysis.get("silence_over_threshold_count", 999) == 0
        and video_qa.get("duration_under_180_seconds") is True
    )

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
            "status": "draft_ready" if video_passed else "failed",
            "evidence": ["competition_submission/03-Demo/VIDEO_SEGMENTS_AUDIT.json", "competition_submission/03-Demo/NARRATED_VIDEO_DRAFT_AUDIT.json"],
            "detail": {
                "source_git_commit": narrated.get("source_git_commit"),
                "real_segment_seconds": segments.get("segment_total_duration_seconds"),
                "draft_seconds": narrated.get("duration_seconds"),
                "draft_bytes": narrated.get("bytes"),
                "draft_sha256": narrated.get("sha256"),
                "draft_resolution": narrated.get("resolution"),
                "video_codec": narrated.get("media", {}).get("video_codec"),
                "audio_codec": narrated.get("media", {}).get("audio_codec"),
                "content_coverage": f"{video_content.get('present_count')}/{video_content.get('required_count')}",
                "all_required_content_present": video_content.get("all_required_present"),
                "max_voice_speed_factor": video_qa.get("max_voice_speed_factor"),
                "silence_over_1_2_seconds": video_audio_analysis.get("silence_over_threshold_count"),
                "integrated_loudness_lufs": video_audio_analysis.get("integrated_loudness_lufs"),
                "true_peak_dbfs": video_audio_analysis.get("true_peak_dbfs"),
                "ai_voice_label_visible": narrated.get("audio", {}).get("ai_generated_label_visible"),
                "subtitle_count": narrated.get("subtitles", {}).get("count"),
                "review_package_sampled_frames": video_review_audit.get("sampled_frame_count"),
                "required_reviewer_count": video_review.get("required_reviewer_count"),
                "real_approval_count": video_review.get("real_approval_count"),
                "team_review_complete": video_review.get("team_review_complete"),
                "video_approved": video_review.get("video_approved"),
            },
            "boundary": "技术QA与25帧接触表已就绪；AI配音DRAFT尚未由内容、技术、隐私/伦理三名审片人完整播放并一致批准",
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
            "detail": {
                "case_count": typical.get("case_count"),
                "automated_gate_pass_count": typical.get("automated_gate_pass_count"),
                "all_expert_reviews_complete": typical.get("all_expert_reviews_complete"),
                "generated_at": typical.get("generated_at"),
                "suite_sha256": typical.get("suite_sha256"),
                "expert_package_source_commit": expert_package.get("source_git_commit"),
                "expert_package_pdf_count": expert_package_audit.get("pdf_count"),
                "expert_package_blinding_passed": expert_package_audit.get("a_stage", {}).get("blinding_passed"),
                "expert_package_secret_scan_passed": expert_package_audit.get("secret_scan", {}).get("passed"),
            },
            "boundary": "A/B两阶段PDF审核包已就绪；自动门禁不等于专家准确率，真实专家仍未审核或签字",
        },
        {
            "id": "target_users",
            "requirement": "至少2名真实目标用户试用记录",
            "status": "pending_external",
            "evidence": [
                "competition_submission/06-效果验证/目标用户试用包_MANIFEST_DRAFT.md",
                "competition_submission/06-效果验证/目标用户试用包_DRAFT/MANIFEST.json",
                "competition_submission/06-效果验证/目标用户试用包_DRAFT/BUILD_AUDIT.json",
            ],
            "detail": {
                "participants_preallocated": user_trial_package.get("participants_preallocated"),
                "pdf_count": user_trial_audit.get("pdf_count"),
                "private_public_separation": user_trial_package.get("private_public_separation"),
                "privacy_separation_passed": user_trial_audit.get("public_package", {}).get("privacy_separation_passed"),
                "secret_scan_passed": user_trial_audit.get("secret_scan", {}).get("passed"),
                "real_participant_count": user_trial_package.get("real_participant_count"),
                "trial_records_complete": user_trial_package.get("trial_records_complete"),
            },
            "boundary": "U01/U02标准化试用材料已就绪，但只是空白表；真实参与者仍为0，不能写成用户验证完成",
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
            "evidence": [
                "competition_submission/02-伦理与安全/伦理签署包_MANIFEST_DRAFT.md",
                "competition_submission/02-伦理与安全/伦理签署包_DRAFT/MANIFEST.json",
                "competition_submission/02-伦理与安全/伦理签署包_DRAFT/BUILD_AUDIT.json",
            ],
            "detail": {
                "pdf_count": ethics_package_audit.get("pdf_count"),
                "privacy_separation_passed": ethics_package_audit.get("public_package", {}).get("privacy_separation_passed"),
                "secret_scan_passed": ethics_package_audit.get("secret_scan", {}).get("passed"),
                "required_signature_count": ethics_package.get("required_signature_count"),
                "real_signature_count": ethics_package.get("real_signature_count"),
                "signature_complete": ethics_package.get("signature_complete"),
                "institutional_ethics_approval_claimed": ethics_package.get("institutional_ethics_approval_claimed"),
            },
            "boundary": "公开声明与私密签署材料已就绪，但真实签名仍为0/3；团队签署不等于机构伦理审批或学校授权",
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
