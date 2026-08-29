"""Build separated private-consent and de-identified target-user trial PDFs.

The generated package prepares U01/U02 forms but never invents participant
identity, ratings, quotes, consent, usability findings, or learning effects.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle
from pypdf import PdfReader


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_expert_review_package import (  # noqa: E402
    ACCENT,
    INK,
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
EFFECT_DIR = SUBMISSION / "06-效果验证"
LAW_MANIFEST = REPO / "backend" / "legal_corpus" / "processed" / "law_corpus_manifest.json"
DEFAULT_OUTPUT = EFFECT_DIR / "目标用户试用包_DRAFT"
PARTICIPANTS = ("U01", "U02")
FOOTER_LABEL = "星火智学 · XH-202620 · 目标用户试用材料"


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deterministic_zip(zip_path: Path, base: Path, files: list[Path]) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files, key=lambda value: value.as_posix()):
            info = zipfile.ZipInfo(path.relative_to(base).as_posix(), date_time=(2026, 8, 30, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def blank_lines(count: int, style: Any) -> Paragraph:
    return Paragraph("<br/>" * count, style)


def consent_story(participant: str, commit: str, st: dict[str, Any]) -> list[Any]:
    consent_id = f"CONSENT-{participant}"
    body = st["body"].clone(f"ConsentBody{participant}")
    body.fontSize = 8.2
    body.leading = 12.2
    body.spaceAfter = 1.2 * mm
    heading = st["h1"].clone(f"ConsentHeading{participant}")
    heading.fontSize = 12.5
    heading.leading = 16
    heading.spaceBefore = 1.5 * mm
    heading.spaceAfter = 1.2 * mm
    return [
        p(f"目标用户试用知情同意书 · {participant}", st["title"]),
        p(
            "私密文件。签名同意书与去标识试用记录分开保存，不进入公开比赛附件。参与完全自愿，可随时停止，不影响课程成绩或其他权益。",
            st["subtitle"],
        ),
        label_value_table(
            [
                ("同意书编号", consent_id),
                ("参与者编号", participant),
                ("系统版本/commit", commit),
                ("活动性质", "本科刑法教学软件可用性与比赛展示验证"),
                ("非活动性质", "不是正式考试、法律咨询或学习效果实验"),
            ],
            st,
        ),
        Spacer(1, 2 * mm),
        p("一、参与内容", heading),
        p(
            "预计一次、约20-30分钟。参与者独立查看认知诊断、个性化路径、可信RAG、形成性任务及案件智能体关键节点；主持人最多提供一次不含答案的中性操作提示。",
            body,
        ),
        p("二、风险与退出", heading),
        p(
            "系统可能给出不完整或错误的AI反馈；教师保留最终教学责任。参与者可跳过任何环节或随时停止。试用时不得输入本人或第三方真实案件、姓名、学号、联系方式、精确住址等敏感信息。",
            body,
        ),
        p("三、数据与保留", heading),
        p(
            "公开材料只使用参与者编号、去标识任务结果、量表和经授权原话。签名原件仅负责人和证据管理员访问。原始记录在比赛结果公布后90天删除，最长不超过180天；撤回后7天内删除尚未公开的原始记录。",
            body,
        ),
        label_value_table(
            [
                ("撤回联系方式", "[团队负责人使用前填写]"),
                ("证据管理员", "[团队使用前填写]"),
            ],
            st,
        ),
        Spacer(1, 2 * mm),
        p("四、授权选项（请逐项圈选）", heading),
        label_value_table(
            [
                ("我同意参加", "是 / 否"),
                ("比赛材料可引用", "实名 / 仅参与者编号 / 不引用原话"),
                ("去标识截图/录屏", "允许 / 不允许"),
                ("理解AI反馈边界", "是 / 否"),
            ],
            st,
        ),
        Spacer(1, 2 * mm),
        p("五、签署", heading),
        label_value_table(
            [
                ("参与者姓名", "[本人填写]"),
                ("参与者签名/可核验确认", "[本人完成]"),
                ("日期", "[YYYY-MM-DD]"),
                ("主持人", "[填写]"),
            ],
            st,
        ),
    ]


def host_story(commit: str, law_sha: str, st: dict[str, Any]) -> list[Any]:
    tasks = [
        ("T1", "打开认知诊断并解释一个状态", "指出证据数/状态，并说明不是掌握概率", "3分钟", "告知入口名称"),
        ("T2", "找到推荐路径及推荐原因", "指出当前任务、一个先修或原因码", "3分钟", "告知切换到路径页"),
        ("T3", "查看特殊防卫可信RAG", "找到条号、原文、来源/版本和专家PENDING", "4分钟", "告知选择TQ02"),
        ("T4", "运行错误引用门禁", "页面显示2/2拒绝并能解释原因", "2分钟", "指出按钮区域"),
        ("T5", "完成一次选择或主观任务", "成功提交并区分AI形成性/教师结论", "6分钟", "仅提示操作位置"),
        ("T6", "进入case3关键节点", "说出学生角色、一个Agent角色和Evidence作用", "5分钟", "告知标杆案卡片"),
    ]
    data = [[p(value, st["cell_bold"]) for value in ("编号", "任务", "成功标准", "超时", "允许提示")]]
    for row in tasks:
        data.append([p(value, st["cell"]) for value in row])
    table = Table(data, colWidths=[13 * mm, 40 * mm, 68 * mm, 19 * mm, 31 * mm], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("GRID", (0, 0), (-1, -1), 0.35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return [
        p("目标用户统一试用主持脚本", st["title"]),
        p("公开工作文件。不含任何身份、签署、联系或授权信息。U01/U02必须使用相同版本、任务和主持规则。", st["subtitle"]),
        label_value_table(
            [
                ("Git commit", commit),
                ("法源manifest SHA-256", law_sha),
                ("建议视口", "1500×980、浏览器100%缩放"),
                ("独立账号", "每位参与者使用独立虚构账号，从0事件开始"),
            ],
            st,
        ),
        Spacer(1, 4 * mm),
        p("一、开始前门禁", st["h1"]),
        p("确认对应私密同意书已完成；确认虚构账号、0事件、同一commit和同一法源；不得复用上一名参与者画像。", st["body"]),
        p("二、统一主持词", st["h1"]),
        p(
            "“请把它当作一段本科刑法自主学习体验。系统反馈不是正式成绩或法律意见。请按你自己的理解操作；如果卡住可以说出来，我最多给一次不含答案的操作提示。请勿输入任何真实案件或个人敏感信息。”",
            st["body"],
        ),
        p("三、统一任务与成功标准", st["h1"]),
        table,
        Spacer(1, 4 * mm),
        p("四、统一记录规则", st["h1"]),
        p(
            "状态只允许：完成 / 提示后完成 / 未完成 / 超时 / 未体验。U01/U02必须完成相同的T1-T4；T5/T6未体验时填写NA并从该项有效n排除。主持人不得代替操作或解释正确答案。错误、卡顿、误解和隐私顾虑原样记录。",
            st["body"],
        ),
        p("五、汇总边界", st["h1"]),
        p("2人样本只报告有效n、中位数和范围，不做显著性检验；主观感受不外推诊断效度或学习效果。", st["body"]),
    ]


def record_story(participant: str, commit: str, law_sha: str, st: dict[str, Any]) -> list[Any]:
    tasks = [
        ("T1", "认知诊断与证据状态"),
        ("T2", "个性化路径与原因"),
        ("T3", "特殊防卫可信RAG"),
        ("T4", "错误引用门禁"),
        ("T5", "选择题或主观短答"),
        ("T6", "case3案件智能体关键节点"),
    ]
    task_data = [[p(value, st["cell_bold"]) for value in ("任务", "状态", "用时", "提示", "观察/困难")]]
    for task_id, label in tasks:
        task_data.append([p(f"{task_id} {label}", st["cell"]), p("[五态]", st["cell"]), p("[分钟]", st["cell"]), p("0/1", st["cell"]), p("", st["cell"])])
    task_table = Table(task_data, colWidths=[54 * mm, 31 * mm, 18 * mm, 14 * mm, 54 * mm], repeatRows=1, rowHeights=[9 * mm] + [15.5 * mm] * len(tasks))
    task_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("GRID", (0, 0), (-1, -1), 0.35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 3)]))
    statements = [
        "我能理解系统为什么推荐当前任务",
        "法条来源、版本和引用足以让我复核",
        "证据不足、AI反馈和教师结论的边界清楚",
        "案件实训比只做客观题更能暴露我的薄弱点",
        "页面与操作适合本科刑法学习",
        "我愿意在真实课程中继续使用",
    ]
    rating_data = [[p("陈述", st["cell_bold"]), p("评分", st["cell_bold"]), p("说明", st["cell_bold"])]]
    for statement in statements:
        rating_data.append([p(statement, st["cell"]), p("1 2 3 4 5 / NA", st["cell"]), p("", st["cell"])])
    rating_table = Table(rating_data, colWidths=[91 * mm, 34 * mm, 46 * mm], repeatRows=1, rowHeights=[9 * mm] + [13.5 * mm] * len(statements))
    rating_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("GRID", (0, 0), (-1, -1), 0.35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 3)]))
    return [
        p(f"目标用户去标识试用记录 · {participant}", st["title"]),
        p("公开候选记录。只填写编号和最小必要学习背景；严禁任何可识别身份、签署、联系、精确住址或真实案件信息。", st["subtitle"]),
        label_value_table(
            [
                ("参与者编号", participant),
                ("同意书编号", f"CONSENT-{participant}"),
                ("身份", "本科法学生 / 法学教师 / 其他目标用户"),
                ("年级或教龄", "[最小必要范围]"),
                ("专业背景", "[刑法课程学习/授课经历]"),
                ("试用日期与方式", "[填写]"),
                ("频次与总时长", "[填写]"),
                ("设备与浏览器", "[填写]"),
                ("系统版本/commit", commit),
                ("法源manifest SHA-256", law_sha),
            ],
            st,
        ),
        PageBreak(),
        p("一、完成任务", st["h1"]),
        task_table,
        Spacer(1, 3 * mm),
        p("五态：完成 / 提示后完成 / 未完成 / 超时 / 未体验。每项最多一次中性提示，主持人不得代替操作。", st["small"]),
        p("二、1-5分量表", st["h1"]),
        p("1=非常不同意，5=非常同意。未体验填NA，不得用中间分代替。", st["small"]),
        rating_table,
        PageBreak(),
        p("三、开放反馈", st["h1"]),
        p("只记录去标识原话；比较性量表只代表主观使用感受，不作为诊断效度或学习增益证据。", st["subtitle"]),
        p("1. 最有帮助的一个环节及原因", st["h2"]),
        blank_lines(5, st["body"]),
        p("2. 最困惑或最不可信的一个环节", st["h2"]),
        blank_lines(5, st["body"]),
        p("3. 必须修复的问题", st["h2"]),
        blank_lines(5, st["body"]),
        p("4. 希望增加或删除的内容", st["h2"]),
        blank_lines(4, st["body"]),
        p("5. 是否发生错误、超时或隐私顾虑", st["h2"]),
        blank_lines(4, st["body"]),
        label_value_table([("记录人", "[填写]"), ("记录完成时间", "[YYYY-MM-DD HH:mm]")], st),
    ]


def summary_story(commit: str, st: dict[str, Any]) -> list[Any]:
    task_data = [[p(value, st["cell_bold"]) for value in ("任务", "U01", "U02", "完成n", "提示后完成n", "未完成/超时n", "未体验n")]]
    for task in ("T1", "T2", "T3", "T4", "T5", "T6"):
        task_data.append([p(task, st["cell"])] + [p("", st["cell"]) for _ in range(6)])
    task_table = Table(task_data, colWidths=[20 * mm, 23 * mm, 23 * mm, 24 * mm, 31 * mm, 31 * mm, 24 * mm], repeatRows=1, rowHeights=[11 * mm] + [15 * mm] * 6)
    task_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("GRID", (0, 0), (-1, -1), 0.35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 3)]))
    rating_data = [[p(value, st["cell_bold"]) for value in ("量表项", "有效n", "中位数", "范围", "NA n")]]
    for index in range(1, 7):
        rating_data.append([p(f"Q{index}", st["cell"]), p("", st["cell"]), p("", st["cell"]), p("", st["cell"]), p("", st["cell"])])
    rating_table = Table(rating_data, colWidths=[70 * mm, 25 * mm, 25 * mm, 30 * mm, 21 * mm], repeatRows=1, rowHeights=[11 * mm] + [14 * mm] * 6)
    rating_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("GRID", (0, 0), (-1, -1), 0.35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 3)]))
    return [
        p("两名目标用户去标识汇总模板", st["title"]),
        p("只有U01和U02均形成真实记录后才能填写。本表不生成结果，不做显著性检验，不报告学习效果。", st["subtitle"]),
        label_value_table([("系统版本/commit", commit), ("参与者", "U01、U02"), ("真实记录完成", "否 / 待外部完成")], st),
        Spacer(1, 4 * mm),
        p("一、任务完成汇总", st["h1"]),
        task_table,
        Spacer(1, 5 * mm),
        p("二、量表汇总", st["h1"]),
        rating_table,
        Spacer(1, 5 * mm),
        p("三、去标识原话与问题处置", st["h1"]),
        blank_lines(8, st["body"]),
        p("四、允许写入比赛材料的结论", st["h1"]),
        p("[仅填写实际完成率、有效n、量表中位数/范围及经授权原话；不得写学习增益、诊断效度或显著性结论]", st["body"]),
        blank_lines(5, st["body"]),
        label_value_table([("汇总人", "[填写]"), ("复核人", "[填写]"), ("日期", "[YYYY-MM-DD]")], st),
    ]


def manifest_for(stage: str, base: Path, files: list[Path], boundary: str) -> dict[str, Any]:
    return {
        "schema": "target-user-trial-stage-manifest-v1",
        "stage": stage,
        "files": [{"path": path.relative_to(base).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)} for path in sorted(files, key=lambda value: value.as_posix())],
        "boundary": boundary,
    }


def pdf_text(path: Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def verify(
    output: Path,
    private_files: list[Path],
    public_files: list[Path],
    private_manifest: Path,
    public_manifest: Path,
    private_zip: Path,
    public_zip: Path,
) -> dict[str, Any]:
    pdfs = [*private_files, *public_files]
    pages = {path.relative_to(output).as_posix(): len(PdfReader(str(path)).pages) for path in pdfs}
    if any(value <= 0 for value in pages.values()):
        raise SystemExit("A generated trial PDF has no pages")
    with zipfile.ZipFile(private_zip) as archive:
        private_names = sorted(archive.namelist())
    with zipfile.ZipFile(public_zip) as archive:
        public_names = sorted(archive.namelist())
    expected_private = sorted(path.relative_to(output).as_posix() for path in [*private_files, private_manifest])
    expected_public = sorted(path.relative_to(output).as_posix() for path in [*public_files, public_manifest])
    if private_names != expected_private or public_names != expected_public:
        raise SystemExit("Trial zip content separation failed")

    public_text = "\n".join(pdf_text(path) for path in public_files)
    private_only = ["参与者姓名", "参与者签名/可核验确认", "撤回联系方式", "比赛材料可引用", "去标识截图/录屏"]
    privacy_hits = [value for value in private_only if value in public_text]
    if privacy_hits:
        raise SystemExit(f"Private consent fields leaked into public trial PDFs: {privacy_hits}")
    required_public = ["U01", "U02", "T1", "T4", "不是掌握概率", "PENDING", "有效n", "中位数", "不做显著性检验"]
    missing_public = [value for value in required_public if value not in public_text]
    if missing_public:
        raise SystemExit(f"Required public trial guidance missing: {missing_public}")
    private_text = "\n".join(pdf_text(path) for path in private_files)
    required_private = ["参与完全自愿", "可随时停止", "不影响课程成绩", "最长不超过180天", "CONSENT-U01", "CONSENT-U02"]
    missing_private = [value for value in required_private if value not in private_text]
    if missing_private:
        raise SystemExit(f"Required consent language missing: {missing_private}")

    secret_patterns = ["api_key", "PRIVATE KEY", "sk-", "D:\\Code\\", "source_response_sha256"]
    all_text = private_text + "\n" + public_text
    secret_hits = [value for value in secret_patterns if value in all_text]
    if secret_hits:
        raise SystemExit(f"Sensitive material leaked into trial package: {secret_hits}")

    manifest_checks: dict[str, bool] = {}
    for manifest_path in (private_manifest, public_manifest):
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        for row in payload["files"]:
            path = output / row["path"]
            manifest_checks[f"{manifest_path.name}:{row['path']}"] = path.is_file() and path.stat().st_size == row["bytes"] and sha256(path) == row["sha256"]
    if not all(manifest_checks.values()):
        raise SystemExit("Trial stage manifest verification failed")

    return {
        "schema": "target-user-trial-package-build-audit-v1",
        "pdf_count": len(pdfs),
        "pdf_pages": pages,
        "private_package": {"zip_entries": private_names},
        "public_package": {"zip_entries": public_names, "private_field_hits": privacy_hits, "privacy_separation_passed": True},
        "required_public_guidance_missing": missing_public,
        "required_consent_language_missing": missing_private,
        "secret_scan": {"patterns": secret_patterns, "hits": secret_hits, "passed": True},
        "stage_manifest_checks": manifest_checks,
        "real_participant_count": 0,
        "trial_records_complete": False,
        "evidence_boundary": "Prepared blank U01/U02 materials only; no consent, participant, rating, quote, usability result or learning effect is fabricated",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    register_fonts()
    st = styles()
    output = args.output.resolve()
    private_dir = output / "private"
    public_dir = output / "public"
    private_dir.mkdir(parents=True, exist_ok=True)
    public_dir.mkdir(parents=True, exist_ok=True)
    commit = git_output("rev-parse", "HEAD")
    law_sha = sha(LAW_MANIFEST)

    private_files: list[Path] = []
    for participant in PARTICIPANTS:
        path = private_dir / f"{participant}_知情同意书_私密.pdf"
        build_pdf(path, f"{participant}目标用户试用知情同意书", consent_story(participant, commit, st), FOOTER_LABEL)
        private_files.append(path)

    host_path = public_dir / "统一试用主持脚本.pdf"
    build_pdf(host_path, "目标用户统一试用主持脚本", host_story(commit, law_sha, st), FOOTER_LABEL)
    public_files = [host_path]
    for participant in PARTICIPANTS:
        path = public_dir / f"{participant}_去标识试用记录.pdf"
        build_pdf(path, f"{participant}去标识试用记录", record_story(participant, commit, law_sha, st), FOOTER_LABEL)
        public_files.append(path)
    summary_path = public_dir / "U01_U02去标识汇总模板.pdf"
    build_pdf(summary_path, "U01 U02去标识试用汇总模板", summary_story(commit, st), FOOTER_LABEL)
    public_files.append(summary_path)

    private_manifest = private_dir / "PRIVATE_MANIFEST.json"
    public_manifest = public_dir / "PUBLIC_MANIFEST.json"
    write_json(private_manifest, manifest_for("private_signed_consent", output, private_files, "Private offline storage only; never include in public competition attachments"))
    write_json(public_manifest, manifest_for("deidentified_trial_records", output, public_files, "Blank de-identified forms only; real participant results are not yet present"))
    private_zip = output / "私密知情同意书包_DRAFT.zip"
    public_zip = output / "去标识试用记录包_DRAFT.zip"
    deterministic_zip(private_zip, output, [*private_files, private_manifest])
    deterministic_zip(public_zip, output, [*public_files, public_manifest])
    private_sha_path = output / f"{private_zip.name}.sha256.txt"
    public_sha_path = output / f"{public_zip.name}.sha256.txt"
    private_sha_path.write_text(f"{sha256(private_zip)}  {private_zip.name}\n", encoding="utf-8")
    public_sha_path.write_text(f"{sha256(public_zip)}  {public_zip.name}\n", encoding="utf-8")

    audit_path = output / "BUILD_AUDIT.json"
    write_json(audit_path, verify(output, private_files, public_files, private_manifest, public_manifest, private_zip, public_zip))
    readme_path = output / "README.md"
    readme_path.write_text(
        f"""# 目标用户试用材料包（DRAFT）

构建commit：`{commit}`

## 使用顺序

1. 团队先在私密同意书中填写撤回联系方式与证据管理员。
2. U01/U02分别完成同意书；同意书只离线私密保管。
3. 使用统一主持脚本完成相同的T1-T4，T5/T6按实际体验记录。
4. 只在去标识记录中填写编号、任务结果、量表和经授权原话。
5. 两人真实记录完成后再填写汇总模板；只报告有效n、中位数和范围，不做显著性检验。

当前`real_participant_count=0`、`trial_records_complete=false`。这些PDF只是空白执行材料，不是试用结果。
""",
        encoding="utf-8",
    )
    all_files = [*private_files, *public_files, private_manifest, public_manifest, private_zip, public_zip, private_sha_path, public_sha_path, audit_path, readme_path]
    root_manifest = {
        "schema": "target-user-trial-package-manifest-v1",
        "source_git_commit": commit,
        "package_build_date": date(2026, 8, 30).isoformat(),
        "participants_preallocated": list(PARTICIPANTS),
        "law_manifest_sha256": law_sha,
        "files": [{"path": path.relative_to(output).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)} for path in sorted(all_files, key=lambda value: value.as_posix())],
        "private_public_separation": True,
        "real_participant_count": 0,
        "trial_records_complete": False,
        "evidence_boundary": "Prepared blank execution materials; no real participant evidence exists until signed consents and completed de-identified records are returned",
    }
    write_json(output / "MANIFEST.json", root_manifest)
    print(json.dumps({"output": str(output), "pdf_count": len(private_files) + len(public_files), "private_zip": {"sha256": sha256(private_zip), "bytes": private_zip.stat().st_size}, "public_zip": {"sha256": sha256(public_zip), "bytes": public_zip.stat().st_size}, "real_participant_count": 0}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
