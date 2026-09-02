"""Build an evidence-indexed effect-validation report and private approval form.

The report distinguishes software evidence (L1), expert content review (L2),
real-user usability evidence (L3), and learning-effect studies (L4). It never
promotes missing L2-L4 evidence into a positive result.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_expert_review_package import (  # noqa: E402
    LIGHT,
    LINE,
    build_pdf,
    label_value_table,
    p,
    register_fonts,
    sha256,
    styles,
    write_json,
)


REPO = SCRIPT_DIR.parents[1]
SUBMISSION = REPO / "competition_submission"
DEFAULT_OUTPUT = SUBMISSION / "06-效果验证" / "效果验证报告包_DRAFT"
FOOTER = "星火智学 · XH-202620 · 效果验证报告材料"

SOURCES = {
    "frozen": SUBMISSION / "03-Demo" / "FROZEN_DEMO_AUDIT.json",
    "legal": SUBMISSION / "03-Demo" / "LEGAL_SOURCE_CURRENCY_AUDIT.json",
    "video": SUBMISSION / "03-Demo" / "NARRATED_VIDEO_DRAFT_AUDIT.json",
    "rehearsal": SUBMISSION / "03-Demo" / "THREE_ROUTE_REHEARSAL_AUDIT.json",
    "web_ppt": SUBMISSION / "04-作品方案" / "guizang-tech-v2" / "qa" / "report.json",
    "pptx": SUBMISSION / "04-作品方案" / "guizang-tech-v2" / "qa" / "pptx-report.json",
    "hybrid_index": REPO / "docs" / "HYBRID_RAG_INDEX_V1_REPORT.json",
    "hybrid_ablation": REPO / "docs" / "HYBRID_RAG_ABLATION_V1.json",
    "hybrid_nli": REPO / "docs" / "HYBRID_RAG_NLI_TRIAGE_V1.json",
    "typical": REPO / "docs" / "TYPICAL_QUESTION_EVALUATION.json",
    "cognitive": REPO / "docs" / "COGNITIVE_DIAGNOSIS_SHOWCASE.md",
    "media": REPO / "docs" / "MULTIMODAL_AVATAR_ARCHITECTURE.md",
    "expert": SUBMISSION / "06-效果验证" / "专家审核包_DRAFT" / "MANIFEST.json",
    "users": SUBMISSION / "06-效果验证" / "目标用户试用包_DRAFT" / "MANIFEST.json",
    "ethics": SUBMISSION / "02-伦理与安全" / "伦理签署包_DRAFT" / "MANIFEST.json",
    "video_review": SUBMISSION / "06-效果验证" / "视频审片包_DRAFT" / "MANIFEST.json",
}


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def deterministic_zip(path: Path, base: Path, files: list[Path]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(files, key=lambda value: value.as_posix()):
            info = zipfile.ZipInfo(file.relative_to(base).as_posix(), date_time=(2026, 8, 30, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, file.read_bytes())


def row_table(headers: tuple[str, ...], rows: list[tuple[Any, ...]], widths: list[float], st: dict[str, Any]) -> Table:
    data = [[p(value, st["cell_bold"]) for value in headers]]
    data.extend([[p(value, st["cell"]) for value in row] for row in rows])
    table = Table(data, colWidths=[value * mm for value in widths], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("GRID", (0, 0), (-1, -1), 0.35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return table


def bullet(text: str, st: dict[str, Any]) -> Paragraph:
    return p(f"- {text}", st["body"])


def report_story(data: dict[str, Any], evidence_sha: str, st: dict[str, Any]) -> list[Any]:
    frozen = data["frozen"]
    legal = data["legal"]
    video = data["video"]
    rehearsal = data["rehearsal"]
    typical = data["typical"]
    expert = data["expert"]
    users = data["users"]
    ethics = data["ethics"]
    video_review = data["video_review"]
    web_ppt = data["web_ppt"]
    pptx = data["pptx"]
    hybrid_index = data["hybrid_index"]
    hybrid_ablation = data["hybrid_ablation"]
    hybrid_nli = data["hybrid_nli"]
    hybrid_r4 = hybrid_ablation["conditions"]["R4_Reranked"]
    web_errors = sum(len(web_ppt.get(key) or []) for key in ("consoleErrors", "pageErrors", "failedRequests"))
    story: list[Any] = [
        p("星火智学效果验证报告", st["title"]),
        p("DRAFT · L1软件证据已形成，L2专家、L3真实用户、L4学习效果均未完成", st["subtitle"]),
        label_value_table(
            [
                ("报告状态", "DRAFT · 待内容、数据、教学三角色批准"),
                ("证据范围", "软件机制、模型接口、真实API探针与候选消融"),
                ("最终提交就绪", "否"),
            ],
            st,
        ),
        Spacer(1, 5 * mm),
        p("一、结论分层", st["h1"]),
        row_table(
            ("层级", "要回答的问题", "当前证据", "当前结论"),
            [
                ("L1 软件机制", "功能是否按契约运行", "自动化、三案例浏览器彩排、真实配置E2E、媒体QA", "已验证到本报告列明范围"),
                ("L2 法学内容", "三题结论和边界是否可靠", "自动检查3/3；A/B专家包", "自动检查通过，真实专家未审核"),
                ("L3 用户可用性", "目标用户能否理解并完成任务", "U01/U02标准化空白材料", "真实参与者0人，无用户结论"),
                ("L4 学习效果", "是否提高保持、迁移或成绩", "前后测、延迟测、对照实验", "尚未开展，不作效果声称"),
            ],
            [24, 49, 54, 44],
            st,
        ),
        Spacer(1, 5 * mm),
        p("二、报告允许表达的总论", st["h1"]),
        p("当前证据支持“比赛演示版的软件闭环、来源治理、媒体质量和教师复核机制可复现”，不支持“已证明刑法认知诊断有效、个性化路径提高成绩、微调模型优于基线、专家已认可或用户已满意”。", st["body"]),
        PageBreak(),
        p("三、L1软件机制证据", st["h1"]),
        row_table(
            ("机制", "当前结果", "证据边界"),
            [
                ("Evidence-KT", "10个刑法知识点；证据不足和临时画像门槛；事件与困惑可追溯", "状态不是校准掌握概率"),
                ("ORCDF shadow", "同47题AUC V0/V1/V2=0.7272/0.7489/0.7528", "数据来自MOOCCubeX民法/宪法；不可用主范围比较Q矩阵优劣"),
                ("七步路径", "薄弱点、先修、选择、主观、案件、角色互换、复习", "候选排序，不宣称因果最优"),
                ("Model Adapter", "火山引擎Ark基线；DeepSeek官方瞬态回退；任务统一路由", "队友微调模型待交付，不称LoRA/SFT完成"),
                ("Hybrid RAG", f"{hybrid_index['totals']['records']:,}条三库索引；候选Recall@5={hybrid_r4['recall_at_5']:.2f}；无答案误返回={hybrid_r4['no_answer_false_positive_rate']:.0f}", "120条qrels教师复核0；候选结果不等于正式准确率"),
                ("NLI模板初筛", f"{hybrid_nli['predicted_pairs']}/{hybrid_nli['input_pairs']}完成；三类各60；模型候选一致率{hybrid_nli['candidate_model_agreement']:.2f}", "教师Gold为0；模型一致不等于NLI准确率"),
                ("知识图/实时语音", "10节点、10条先修边、6步论证模板；讯飞实时IAT partial/final、Evidence回复与TTS多轮通过", "ASR需复核、媒体不进入画像；OCR/数字人未连接"),
                ("可信RAG", f"三题自动检查{typical['automated_gate_pass_count']}/{typical['case_count']}；错误引用2/2拒绝", "自动检查不等于专家准确率"),
                ("教师HITL", "退回-原文修订-批准；同稿单决定、单事件", "合成账号浏览器闭环，不是用户试用"),
                ("case3 Agent", f"{frozen['case3_e2e']['elapsed_seconds']}秒、{frozen['case3_e2e']['fixed_response_count']}次固定回答、3/3 Agent退场、0错误", "不是29名用户；不起诉分支非专家结论"),
            ],
            [35, 79, 57],
            st,
        ),
        PageBreak(),
        p("四、L1量化与交付QA", st["h1"]),
        row_table(
            ("证据对象", "结果", "能证明", "不能证明"),
            [
                ("冻结演示库", f"源{frozen['semantic_audit']['source_check_count']}/24、恢复{frozen['semantic_audit']['restore_check_count']}/24", "备份恢复语义一致", "真实课堂稳定性"),
                ("关键法条", f"{legal['target_article_pass_count']}/{legal['target_article_count']}", "5条来源、版本、文本一致", "全量法库或具体适法正确"),
                ("三案例彩排", f"{rehearsal['routes_passed']}/{rehearsal['route_count']}、{rehearsal['duration_seconds']}秒、浏览器错误{rehearsal['browser_error_total']}", "同一本地栈三条UI路线可重复", "真实用户认可或学习效果"),
                ("网页PPT", f"{len(web_ppt['slides'])}页、浏览器错误{web_errors}、溢出0", "主要视口可用", "目标用户可用性"),
                ("PPTX", f"{pptx['slides']}页、{pptx['pptx_bytes']:,}字节；PowerPoint回渲染{pptx['rendered_slides']}页；最大像素差{pptx['max_mean_absolute_pixel_difference']}", "PPTX结构、视觉源和实际PowerPoint渲染一致", "内容专家认可"),
                ("演示视频", f"{video['duration_seconds']}秒、12/12、{video['qa']['max_voice_speed_factor']}×、静音{video['audio']['analysis']['silence_over_threshold_count']}", "≤180秒、内容覆盖、实时语音与媒体检查", "团队批准或用户认可"),
            ],
            [31, 45, 50, 45],
            st,
        ),
        Spacer(1, 5 * mm),
        p("五、ORCDF受控解释", st["h1"]),
        bullet("V0：1,256题、126,073作答、180个原始exercise_id；同47题AUC 0.7272。", st),
        bullet("V1：590可训练题、124,121作答、74个LLM候选概念、741条Q边；同47题AUC 0.7489。", st),
        bullet("V2：47题、7,356作答、97个教师知识点、105条Q边；同47题AUC 0.7528。", st),
        bullet("V1-V0同47题差0.0299，seed42学生聚类bootstrap 95%CI [0.0037,0.0537]；这不等于刑法课堂效果。", st),
        bullet("V2 mastery集中在0.5附近且未校准，只能称相对状态；新刑法课堂只做通用层初始化与scratch对照。", st),
        PageBreak(),
        p("六、L2法学内容验证", st["h1"]),
        row_table(
            ("题目", "自动检查", "专家状态", "允许结论"),
            [
                ("罪刑法定与从旧兼从轻", "通过", "待复核", "仅称结构/要点/引用检查通过"),
                ("正当防卫与特殊防卫", "通过", "待复核", "case3适法仍需专家判断"),
                ("抢劫罪基本构成", "通过", "待复核", "价值低不当然排除仍需专家复核"),
            ],
            [55, 30, 30, 56],
            st,
        ),
        p("三题使用的目标法条已纳入5/5时效审计，但法条文本现行只消除文本过期/篡改风险，不替代事实涵摄、争议判断和独立专家签署。", st["body"]),
        label_value_table(
            [
                ("专家审核包", "8份PDF、21页；A包盲审隔离和秘密扫描通过"),
                ("真实专家完成", str(expert["evaluation_report"]["all_expert_reviews_complete"]).lower()),
            ],
            st,
        ),
        p("七、L3目标用户验证", st["h1"]),
        label_value_table(
            [
                ("预分配编号", "U01、U02"),
                ("标准化材料", "6份PDF、11页；私密同意与公开记录分离"),
                ("真实参与者", str(users["real_participant_count"])),
                ("真实记录完成", str(users["trial_records_complete"]).lower()),
            ],
            st,
        ),
        p("只有两人真实完成后，才报告各任务有效n、完成状态、量表中位数/范围和经授权原话；2人样本不做显著性检验。", st["body"]),
        p("八、L4学习效果", st["h1"]),
        p("尚未开展前后测、延迟测、对照实验或功效分析。本报告不声称成绩提升、保持改善、迁移增强或路径因果效果。", st["body"]),
        PageBreak(),
        p("九、材料批准与剩余缺口", st["h1"]),
        label_value_table(
            [
                ("视频技术状态", f"DRAFT待批准；团队批准{video_review['real_approval_count']}/{video_review['required_reviewer_count']}"),
                ("伦理签署", f"{ethics['real_signature_count']}/{ethics['required_signature_count']}"),
                ("专家审核", "0个完成签署结论"),
                ("目标用户", f"{users['real_participant_count']}/2"),
                ("本效果报告批准", "0/3"),
            ],
            st,
        ),
        Spacer(1, 5 * mm),
        p("十、不支持的结论", st["h1"]),
        bullet("刑法掌握率达到X%。", st),
        bullet("个性化路径使成绩提升X%或因果最优。", st),
        bullet("V2教师Q矩阵显著优于V1，或主范围AUC可以直接比较。", st),
        bullet("微调模型优于基线，或已经完成LoRA/SFT。", st),
        bullet("已完成伦理审批、课堂试点、专家准确率、用户满意度或50人实验。", st),
        p("十一、报告状态", st["h1"]),
        p("本PDF是证据索引化DRAFT。只有内容、数据、教学三名复核人一致批准，且最终引用的专家/用户/视频状态与证据文件一致后，才能升级为最终报告。", st["body"]),
    ]
    return story


def approval_story(report_sha: str, index_sha: str, commit: str, st: dict[str, Any]) -> list[Any]:
    checks = [
        ("L1结论仅限软件机制与列明范围", "[复核]"),
        ("L2专家仍待复核，未计算专家准确率", "[复核]"),
        ("L3真实参与者0人，未报告用户结论", "[复核]"),
        ("L4未开展，不报告学习增益", "[复核]"),
        ("ORCDF数据、同47题范围、CI和未校准边界准确", "[复核]"),
        ("视频、PPT、法源、case3与三题指标和SHA一致", "[复核]"),
        ("不支持结论完整，未使用显著/有效/提升等越界词", "[复核]"),
        ("公开报告无身份、签名、密钥、私有路径或未授权原话", "[复核]"),
    ]
    data = [[p("确认", st["cell_bold"]), p("报告门禁", st["cell_bold"]), p("记录", st["cell_bold"])]]
    for label, note in checks:
        data.append([p("[  ]", st["center"]), p(label, st["cell"]), p(note, st["cell"])])
    table = Table(data, colWidths=[16 * mm, 108 * mm, 47 * mm], repeatRows=1, rowHeights=[10 * mm] + [16 * mm] * len(checks))
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("GRID", (0, 0), (-1, -1), 0.35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    return [
        p("效果验证报告 · 私密批准表", st["title"]),
        p("三名复核人必须核对公开PDF和证据索引；批准报告不等于补齐L2-L4证据。", st["subtitle"]),
        label_value_table([("Git commit", commit), ("公开报告SHA-256", report_sha), ("证据索引SHA-256", index_sha), ("复核日期", "[YYYY-MM-DD]")], st),
        Spacer(1, 4 * mm),
        table,
        PageBreak(),
        p("批准结论", st["h1"]),
        p("结论只允许：批准为DRAFT报告 / 修改后复审 / 拒绝使用。未补齐L2-L4时不得批准为“学习效果最终报告”。", st["body"]),
        Spacer(1, 5 * mm),
        label_value_table([("内容复核人", "[本人填写/签字]"), ("结论", "[三选一]"), ("问题与处置", "[填写]"), ("日期", "[YYYY-MM-DD]")], st),
        Spacer(1, 8 * mm),
        label_value_table([("数据复核人", "[本人填写/签字]"), ("结论", "[三选一]"), ("问题与处置", "[填写]"), ("日期", "[YYYY-MM-DD]")], st),
        Spacer(1, 8 * mm),
        label_value_table([("教学复核人", "[本人填写/签字]"), ("结论", "[三选一]"), ("问题与处置", "[填写]"), ("日期", "[YYYY-MM-DD]")], st),
        Spacer(1, 8 * mm),
        label_value_table([("三人一致最终结论", "[三选一]"), ("签署后本页SHA-256", "[计算后填写]"), ("私密原件位置", "[离线保管]")], st),
    ]


def manifest(stage: str, base: Path, files: list[Path], boundary: str) -> dict[str, Any]:
    return {"schema": "effect-report-stage-manifest-v1", "stage": stage, "files": [{"path": file.relative_to(base).as_posix(), "bytes": file.stat().st_size, "sha256": sha256(file)} for file in sorted(files, key=lambda value: value.as_posix())], "boundary": boundary}


def pdf_text(path: Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    register_fonts()
    st = styles()
    output = args.output.resolve()
    allowed_root = (SUBMISSION / "06-效果验证").resolve()
    if not output.is_relative_to(allowed_root) or output.name != "效果验证报告包_DRAFT":
        raise SystemExit("Effect-report output must be the named DRAFT directory inside 06-效果验证")
    if output.exists():
        shutil.rmtree(output)
    public_dir = output / "public"
    private_dir = output / "private"
    public_dir.mkdir(parents=True, exist_ok=True)
    private_dir.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {"commit": git_output("rev-parse", "HEAD")}
    for key, path in SOURCES.items():
        data[key] = load(path) if path.suffix == ".json" else path.read_text(encoding="utf-8")
    evidence_index = {
        "schema": "effect-report-evidence-index-v1",
        "source_git_commit": data["commit"],
        "sources": [{"id": key, "path": path.relative_to(REPO).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)} for key, path in SOURCES.items()],
        "evidence_levels": {
            "L1": "software evidence available within listed scope",
            "L2": "expert review pending",
            "L3": "real participant count 0",
            "L4": "not conducted",
        },
        "evidence_boundary": "Indexing evidence does not promote missing L2-L4 results",
    }
    index_path = public_dir / "EVIDENCE_INDEX.json"
    write_json(index_path, evidence_index)
    report_path = public_dir / "星火智学效果验证报告_DRAFT.pdf"
    build_pdf(report_path, "星火智学效果验证报告", report_story(data, sha256(index_path), st), FOOTER)
    approval_path = private_dir / "效果验证报告批准表_私密.pdf"
    build_pdf(approval_path, "效果验证报告私密批准表", approval_story(sha256(report_path), sha256(index_path), data["commit"], st), FOOTER)
    public_files = [report_path, index_path]
    private_files = [approval_path]
    public_manifest = public_dir / "PUBLIC_MANIFEST.json"
    private_manifest = private_dir / "PRIVATE_MANIFEST.json"
    write_json(public_manifest, manifest("public_effect_report", output, public_files, "L1-L4 evidence-indexed DRAFT; L2-L4 remain incomplete"))
    write_json(private_manifest, manifest("private_report_approval", output, private_files, "Blank three-role approval form; completed signatures stay offline"))
    public_zip = output / "效果验证报告公开包_DRAFT.zip"
    private_zip = output / "效果报告批准页包_DRAFT.zip"
    deterministic_zip(public_zip, output, [*public_files, public_manifest])
    deterministic_zip(private_zip, output, [*private_files, private_manifest])
    public_sha = output / f"{public_zip.name}.sha256.txt"
    private_sha = output / f"{private_zip.name}.sha256.txt"
    public_sha.write_text(f"{sha256(public_zip)}  {public_zip.name}\n", encoding="utf-8")
    private_sha.write_text(f"{sha256(private_zip)}  {private_zip.name}\n", encoding="utf-8")
    public_text = pdf_text(report_path)
    private_text = pdf_text(approval_path)
    required_public = ["L1 软件机制", "L2 法学内容", "L3 用户可用性", "L4 学习效果", "真实参与者0人", "不作效果声称", "不支持的结论", "队友微调模型待交付", "专家状态", "待复核", "三案例彩排", "讯飞实时IAT", "ASR需复核", "Hybrid RAG", "57,051", "候选Recall@5=0.86"]
    missing_public = [value for value in required_public if value not in public_text]
    compact_public = re.sub(r"\s+", "", public_text)
    required_compact = ["PowerPoint回渲染13页", "OCR/数字人未连接"]
    missing_public.extend(
        value for value in required_compact if value not in compact_public
    )
    forbidden_positive = ["专家准确率100%", "学习效果已验证", "显著提升成绩", "真实用户已完成", "已完成LoRA/SFT"]
    positive_hits = [value for value in forbidden_positive if value in public_text]
    required_private = ["内容复核人", "数据复核人", "教学复核人", "三人一致最终结论", "不得批准为“学习效果最终报告”"]
    missing_private = [value for value in required_private if value not in private_text]
    if missing_public or positive_hits or missing_private:
        raise SystemExit(f"Effect report text gate failed: {missing_public} / {positive_hits} / {missing_private}")
    secret_patterns = ["api_key", "PRIVATE KEY", "sk-", "D:\\Code\\", "source_response_sha256"]
    secret_hits = [value for value in secret_patterns if value in public_text + private_text + index_path.read_text(encoding="utf-8")]
    if secret_hits:
        raise SystemExit(f"Sensitive effect report leak: {secret_hits}")
    audit = {
        "schema": "effect-report-package-build-audit-v1",
        "public_pdf_pages": len(PdfReader(str(report_path)).pages),
        "private_pdf_pages": len(PdfReader(str(approval_path)).pages),
        "source_count": len(SOURCES),
        "required_public_missing": missing_public,
        "forbidden_positive_hits": positive_hits,
        "required_private_missing": missing_private,
        "secret_scan": {"hits": secret_hits, "passed": True},
        "evidence_levels": evidence_index["evidence_levels"],
        "required_approver_count": 3,
        "real_approval_count": 0,
        "report_review_complete": False,
        "report_approved": False,
        "evidence_boundary": "Generated DRAFT and blank approval form only; no L2-L4 result or human approval is fabricated",
    }
    audit_path = output / "BUILD_AUDIT.json"
    write_json(audit_path, audit)
    readme = output / "README.md"
    readme.write_text(f"""# 效果验证报告包（DRAFT）

1. 公开PDF按L1-L4区分证据，不把自动化与演示数据写成学习效果。
2. 内容、数据、教学三名复核人核对PDF和EVIDENCE_INDEX.json。
3. 三人一致批准后，只能批准为当前证据状态下的DRAFT/比赛报告；缺少L2-L4时不能改称学习效果最终报告。

当前`real_approval_count=0`、`report_review_complete=false`、`report_approved=false`。
""", encoding="utf-8")
    all_files = [*public_files, *private_files, public_manifest, private_manifest, public_zip, private_zip, public_sha, private_sha, audit_path, readme]
    root = {
        "schema": "effect-report-package-manifest-v1",
        "source_git_commit": data["commit"],
        "package_build_date": date(2026, 8, 30).isoformat(),
        "report_sha256": sha256(report_path),
        "evidence_index_sha256": sha256(index_path),
        "files": [{"path": file.relative_to(output).as_posix(), "bytes": file.stat().st_size, "sha256": sha256(file)} for file in sorted(all_files, key=lambda value: value.as_posix())],
        "evidence_levels": evidence_index["evidence_levels"],
        "required_approver_count": 3,
        "real_approval_count": 0,
        "report_review_complete": False,
        "report_approved": False,
        "evidence_boundary": "Evidence-indexed report DRAFT; no missing expert, user, learning-effect or approval evidence is fabricated",
    }
    write_json(output / "MANIFEST.json", root)
    print(json.dumps({"output": str(output), "report_sha256": sha256(report_path), "public_pages": audit["public_pdf_pages"], "private_pages": audit["private_pdf_pages"], "source_count": len(SOURCES), "real_approval_count": 0}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
