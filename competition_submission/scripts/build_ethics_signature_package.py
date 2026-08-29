"""Build public ethics declaration and private signature materials.

This script prepares blank signing materials. It never creates names,
signatures, institutional ethics approval, classroom authorization, expert
validation, participant evidence, or release approval.
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

from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle
from pypdf import PdfReader


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
ETHICS_DIR = SUBMISSION / "02-伦理与安全"
DEFAULT_OUTPUT = ETHICS_DIR / "伦理签署包_DRAFT"
LEGAL_AUDIT = SUBMISSION / "03-Demo" / "LEGAL_SOURCE_CURRENCY_AUDIT.json"
VIDEO_AUDIT = SUBMISSION / "03-Demo" / "NARRATED_VIDEO_DRAFT_AUDIT.json"
EXPERT_MANIFEST = SUBMISSION / "06-效果验证" / "专家审核包_DRAFT" / "MANIFEST.json"
USER_MANIFEST = SUBMISSION / "06-效果验证" / "目标用户试用包_DRAFT" / "MANIFEST.json"
LAW_MANIFEST = REPO / "backend" / "legal_corpus" / "processed" / "law_corpus_manifest.json"
FOOTER_LABEL = "星火智学 · XH-202620 · 伦理与安全签署材料"


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def deterministic_zip(zip_path: Path, base: Path, files: list[Path]) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files, key=lambda value: value.as_posix()):
            info = zipfile.ZipInfo(path.relative_to(base).as_posix(), date_time=(2026, 8, 30, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def bullet(text: str, st: dict[str, Any]) -> Paragraph:
    return p(f"- {text}", st["body"])


def checklist_table(rows: list[tuple[str, str]], st: dict[str, Any]) -> Table:
    data = [[p("确认", st["cell_bold"]), p("门禁", st["cell_bold"]), p("当前状态/复核记录", st["cell_bold"])]]
    for label, status in rows:
        data.append([p("[  ]", st["center"]), p(label, st["cell"]), p(status, st["cell"])])
    table = Table(data, colWidths=[16 * mm, 92 * mm, 63 * mm], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("GRID", (0, 0), (-1, -1), 0.35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return table


def declaration_story(
    commit: str,
    law_sha: str,
    legal: dict[str, Any],
    video: dict[str, Any],
    expert: dict[str, Any],
    users: dict[str, Any],
    st: dict[str, Any],
) -> list[Any]:
    return [
        p("星火智学伦理与安全合规声明", st["title"]),
        p("DRAFT · 待团队负责人、指导教师和数据/安全责任人真实签署", st["subtitle"]),
        label_value_table(
            [
                ("Git commit", commit),
                ("法源manifest SHA-256", law_sha),
                ("关键法条时效复核", f"{legal['target_article_pass_count']}/{legal['target_article_count']} · {legal['checked_at']}"),
                ("专家审核", "材料已就绪，真实专家未审核或签字"),
                ("目标用户", f"预分配U01/U02，真实参与者{users['real_participant_count']}人"),
                ("演示视频", f"{video['duration_seconds']}秒 · {video['resolution']} · AI配音DRAFT"),
            ],
            st,
        ),
        Spacer(1, 5 * mm),
        p("一、项目用途与责任边界", st["h1"]),
        p(
            "星火智学面向本科刑法课堂，提供形成性认知诊断、可信法源检索、个性化学习任务、多智能体案件实训与教师复核。系统只用于教学支持与比赛演示，不替代任课教师、司法机关或执业律师，不自动发布正式成绩或法律意见。",
            st["body"],
        ),
        p(
            "本声明是团队对数据、AI输出、教学边界与安全措施的自我约束。团队签署不等于学校授权、机构伦理委员会审批、课堂试点批准、法学专家背书或法律服务资质。",
            st["body"],
        ),
        p("二、数据来源与最小化", st["h1"]),
        bullet("法律文本来自受治理的本地法源快照，保存来源、版本和SHA-256；正式提交前、每学期开课前和真实法律使用前重新复核。", st),
        bullet("本次只对5条演示关键法条完成2026年时效与逐字一致性审计，不宣称全量法库已逐条复核。", st),
        bullet("ORCDF实验使用MOOCCubeX民法/宪法匿名行为数据，只用于迁移研究和shadow展示，不冒充本科刑法课堂数据。", st),
        bullet("冻结Demo使用虚构邮箱、本地SQLite和确定性脚本输入；不把浏览器smoke、29次固定回答或演示事件冒充真实学生。", st),
        bullet("目标用户试用只收集完成比赛验证所需的最小角色背景、任务、时长、量表与反馈；公开材料只用U01/U02编号。", st),
        PageBreak(),
        p("三、AI生成内容与教师责任", st["h1"]),
        bullet("页面、PPT和视频显著标注AI生成或AI辅助内容；视频AI配音DRAFT尚待团队完整审片。", st),
        bullet("大模型只提供追问、解释、对抗与形成性反馈草稿；主观题只有教师批准后才形成长期画像证据。", st),
        bullet("错条号、伪造引文、越界Evidence、坏JSON和低置信度输出必须拒绝、弃权、回退或进入教师复核。", st),
        bullet("当前基线为OpenCode/DeepSeek兼容路由；微调端点not_connected，不得表述为已完成LoRA/SFT。", st),
        bullet("三题自动门禁3/3只证明结构、要点、来源范围和逐字quote门禁；不等于专家准确率。", st),
        p("四、认知诊断与推荐边界", st["h1"]),
        bullet("insufficient_evidence表示证据不足；provisional表示临时证据状态，均不是校准掌握概率。", st),
        bullet("困惑是学生自报信号，不直接作为答错、扣分或正式成绩证据。", st),
        bullet("ORCDF mastery是未校准潜变量；MOOCCubeX训练只可作为通用初始化研究，不直接迁移旧学生、题目或知识参数。", st),
        bullet("七步个性化路径是基于当前证据的可解释候选排序，不宣称因果最优或已验证学习增益。", st),
        p("五、案件智能体与法律结论边界", st["h1"]),
        bullet("Agent只能围绕受治理案件事实与获准工具活动，不得虚构证据、法源或专家意见。", st),
        bullet("case3不起诉是固定脚本输入下的模型/状态机演示分支，不是独立专家确认的法律结论或真实案件结果保证。", st),
        bullet("任何面向课堂发布的标准答案、指导案例要点和形成性评价仍需任课教师审核。", st),
        PageBreak(),
        p("六、隐私、访问与保留", st["h1"]),
        bullet("API Key、Token、完整私有端点和私有绝对路径不得进入前端响应、日志、截图、PPT、视频或公开附件。", st),
        bullet("学生历史、困惑和主观稿按登录身份隔离；教师只查看自有班级匿名形成性数据。", st),
        bullet("LearningEvent不可变且幂等；同一主观稿最多一次教师决定和一次画像事件。", st),
        bullet("签名同意书与去标识试用记录分开保存；签名原件只允许负责人和指定证据管理员访问，不提交Git。", st),
        bullet("目标用户原始记录在比赛结果公布后90天删除，最长不超过180天；撤回后7天内删除尚未公开的原始记录。", st),
        bullet("演示录屏必须隐藏邮箱、内部用户ID、令牌、密钥、私有路径和未经授权的困惑原文。", st),
        p("七、安全措施与事件处置", st["h1"]),
        bullet("本地演示使用SQLite + adaptive + Vite，不把Docker或外部在线服务作为比赛演示的必需链路。", st),
        bullet("法源检索优先使用本地受治理语料；外部模型或检索失败时必须有拒答、回退或离线快照。", st),
        bullet("发现密钥、真实身份、未授权录屏或错误法律结论泄漏时，立即停止录制/发布，撤下材料、轮换密钥并记录处置。", st),
        bullet("任何数据或内容版本变化都应更新manifest、SHA、模型/Prompt版本和审计日期，禁止静默覆盖旧证据。", st),
        p("八、目标用户试用要求", st["h1"]),
        bullet("参与完全自愿，可随时停止且不影响课程成绩或其他权益；试用不是正式考试或学习效果实验。", st),
        bullet("U01/U02使用独立虚构账号和统一T1-T4；每项最多一次不含答案的中性提示。", st),
        bullet("2人样本只报告有效n、中位数和范围，不做显著性检验，不外推诊断效度或学习效果。", st),
        PageBreak(),
        p("九、主要风险与控制", st["h1"]),
        checklist_table(
            [
                ("法条过期或引用错误", "版本化法源、逐字quote门禁、5条关键法条审计、教师复核、失败弃权"),
                ("模型偏见或不稳定", "独立金标准、A/B专家审核、低置信回退、保留模型与Prompt版本"),
                ("形成性评价被误当正式成绩", "UI/PPT/报告持续标识；不接正式成绩发布"),
                ("学生画像误判", "证据不足优先、事件可追溯、教师解释、学生修订"),
                ("用户试用隐私泄漏", "知情同意、最少字段、编号、私密/公开分包、限定保留期"),
                ("演示数据被冒充真实课堂", "虚构账号和固定脚本显著披露；真实用户与专家状态独立记录"),
                ("Agent适法结论被过度宣传", "明确演示分支；专家PENDING；答辩与材料保留限定语"),
            ],
            st,
        ),
        Spacer(1, 5 * mm),
        p("十、签署与发布条件", st["h1"]),
        p(
            "公开正文可用于团队内部复核和比赛附件草案。只有三名责任角色完成私密签署页、签署前核对清单通过且材料SHA固定后，团队才能把本声明标为“已签署”。如比赛要求公开签署信息，必须另行确认签署人的公开授权。",
            st["body"],
        ),
        p(
            "在真实签署前，本声明保持DRAFT；在专家、目标用户或视频审批尚未完成时，相应PENDING状态继续保留，不因签署伦理声明而自动变为已验证。",
            st["body"],
        ),
        label_value_table(
            [
                ("专家审核状态", "PENDING · 审核包已就绪，未签字"),
                ("目标用户状态", f"PENDING · 真实参与者{users['real_participant_count']}人"),
                ("视频状态", "DRAFT · 待团队完整审片"),
                ("微调状态", "NOT_CONNECTED"),
                ("声明签署状态", "PENDING · 私密签署页为空白"),
            ],
            st,
        ),
    ]


def checklist_story(commit: str, st: dict[str, Any]) -> list[Any]:
    return [
        p("伦理与安全声明 · 签署前核对清单", st["title"]),
        p("所有项目必须由实际责任人复核。勾选不等于机构伦理审批；发现不一致时先修订材料并重新计算SHA。", st["subtitle"]),
        label_value_table([("Git commit", commit), ("核对日期", "[YYYY-MM-DD]"), ("核对主持人", "[填写]")], st),
        Spacer(1, 4 * mm),
        p("一、内容与证据边界", st["h1"]),
        checklist_table(
            [
                ("ORCDF明确为MOOCCubeX民法/宪法shadow，mastery未校准", "[复核位置/说明]"),
                ("Evidence-KT状态不称掌握概率，insufficient_evidence优先", "[复核位置/说明]"),
                ("微调端点显示not_connected，不称已完成LoRA/SFT", "[复核位置/说明]"),
                ("三题3/3称自动门禁，不称专家准确率", "[复核位置/说明]"),
                ("case3不起诉称演示分支，不称专家确认结论", "[复核位置/说明]"),
                ("浏览器smoke、合成账号和固定脚本不称真实用户", "[复核位置/说明]"),
            ],
            st,
        ),
        p("二、隐私与安全", st["h1"]),
        checklist_table(
            [
                ("公开材料无API Key、Token、私有端点、内部ID和私有路径", "[扫描记录]"),
                ("录屏无邮箱、未授权困惑原文或签名同意书", "[审片记录]"),
                ("目标用户同意书与去标识记录分包，签名原件不入Git", "[保管位置]"),
                ("撤回联系方式与证据管理员已填写", "[私密核对]"),
                ("原始记录保留与删除时间已登记", "[登记位置]"),
                ("演示账号均为虚构身份", "[审计文件]"),
            ],
            st,
        ),
        PageBreak(),
        p("三、法源、模型与版本", st["h1"]),
        checklist_table(
            [
                ("5条演示关键法条时效审计为PASS_WITH_SCOPE_LIMITATIONS", "[审计日期/SHA]"),
                ("正式提交前再次查询国家法律法规数据库", "[复核人/时间]"),
                ("PPT、视频、报告与Demo绑定同一最终commit/tag", "[最终commit/tag]"),
                ("模型、provider、Prompt、法源manifest和材料SHA均可追溯", "[manifest位置]"),
                ("离线备份恢复审计通过且私密密码哈希不公开", "[审计文件]"),
            ],
            st,
        ),
        p("四、外部证据与批准", st["h1"]),
        checklist_table(
            [
                ("独立法学专家A阶段先锁定，B阶段后披露", "[签名表SHA]"),
                ("至少2名目标用户形成真实去标识记录", "[U01/U02记录SHA]"),
                ("效果报告只写实际有效n、中位数和范围", "[报告位置]"),
                ("团队完整审片并批准最终视频", "[审片人/日期]"),
                ("三名伦理责任角色完成私密签署页", "[签署页SHA]"),
            ],
            st,
        ),
        Spacer(1, 5 * mm),
        label_value_table(
            [
                ("核对结论", "通过 / 修改后再签 / 暂停发布"),
                ("未通过项与处置", "[填写]"),
                ("核对人签名", "[本人签名]"),
                ("日期", "[YYYY-MM-DD]"),
            ],
            st,
        ),
    ]


def signature_story(commit: str, declaration_sha: str, checklist_sha: str, st: dict[str, Any]) -> list[Any]:
    return [
        p("伦理与安全合规声明 · 私密签署页", st["title"]),
        p("私密文件。签署人的姓名、签名与联系方式不得写入公开代码仓库；如需公开，必须取得签署人单独授权。", st["subtitle"]),
        label_value_table(
            [
                ("Git commit", commit),
                ("公开声明正文SHA-256", declaration_sha),
                ("签署前核对清单SHA-256", checklist_sha),
                ("签署性质", "团队责任声明；不是机构伦理委员会审批或学校授权"),
            ],
            st,
        ),
        Spacer(1, 6 * mm),
        p("签署确认", st["h1"]),
        p(
            "本人已阅读并复核上述commit对应的公开声明正文与签署前核对清单，理解项目用途、数据来源、AI生成内容、认知诊断、Agent适法结论、隐私保留和外部证据边界。本人确认不会把未完成的专家审核、目标用户试用、视频批准、微调模型或学习效果表述为已完成。",
            st["body"],
        ),
        Spacer(1, 8 * mm),
        label_value_table(
            [
                ("团队负责人姓名", "[本人填写]"),
                ("团队负责人签字", "[本人签字]"),
                ("日期", "[YYYY-MM-DD]"),
            ],
            st,
        ),
        Spacer(1, 10 * mm),
        label_value_table(
            [
                ("指导教师姓名", "[本人填写]"),
                ("指导教师签字", "[本人签字]"),
                ("日期", "[YYYY-MM-DD]"),
            ],
            st,
        ),
        Spacer(1, 10 * mm),
        label_value_table(
            [
                ("数据/安全责任人姓名", "[本人填写]"),
                ("数据/安全责任人签字", "[本人签字]"),
                ("日期", "[YYYY-MM-DD]"),
            ],
            st,
        ),
        Spacer(1, 12 * mm),
        label_value_table(
            [
                ("签署完成后本页SHA-256", "[计算后填写]"),
                ("签署原件保管位置", "[私密离线位置]"),
                ("公开签署信息授权", "全部允许 / 仅角色与日期 / 不公开"),
            ],
            st,
        ),
    ]


def manifest(stage: str, base: Path, files: list[Path], boundary: str) -> dict[str, Any]:
    return {
        "schema": "ethics-signature-stage-manifest-v1",
        "stage": stage,
        "files": [{"path": path.relative_to(base).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)} for path in sorted(files, key=lambda value: value.as_posix())],
        "boundary": boundary,
    }


def pdf_text(path: Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def verify(
    output: Path,
    public_files: list[Path],
    private_files: list[Path],
    public_manifest: Path,
    private_manifest: Path,
    public_zip: Path,
    private_zip: Path,
) -> dict[str, Any]:
    pdfs = [*public_files, *private_files]
    pages = {path.relative_to(output).as_posix(): len(PdfReader(str(path)).pages) for path in pdfs}
    if any(value <= 0 for value in pages.values()):
        raise SystemExit("Generated ethics PDF has no pages")
    with zipfile.ZipFile(public_zip) as archive:
        public_names = sorted(archive.namelist())
    with zipfile.ZipFile(private_zip) as archive:
        private_names = sorted(archive.namelist())
    expected_public = sorted(path.relative_to(output).as_posix() for path in [*public_files, public_manifest])
    expected_private = sorted(path.relative_to(output).as_posix() for path in [*private_files, private_manifest])
    if public_names != expected_public or private_names != expected_private:
        raise SystemExit("Ethics public/private zip separation failed")

    public_text = "\n".join(pdf_text(path) for path in public_files)
    private_text = "\n".join(pdf_text(path) for path in private_files)
    private_fields = ["团队负责人姓名", "指导教师姓名", "数据/安全责任人姓名", "本人签字", "签署原件保管位置"]
    privacy_hits = [value for value in private_fields if value in public_text]
    if privacy_hits:
        raise SystemExit(f"Private signature fields leaked into public ethics PDFs: {privacy_hits}")
    required_public = [
        "不替代任课教师",
        "不等于学校授权",
        "MOOCCubeX民法/宪法",
        "not_connected",
        "insufficient_evidence",
        "不等于专家准确率",
        "真实参与者0人",
        "AI配音DRAFT",
        "不做显著性检验",
        "PENDING",
    ]
    missing_public = [value for value in required_public if value not in public_text]
    if missing_public:
        raise SystemExit(f"Required ethics boundary missing: {missing_public}")
    required_private = ["团队负责人姓名", "指导教师姓名", "数据/安全责任人姓名", "不是机构伦理委员会审批", "签署完成后本页SHA-256"]
    missing_private = [value for value in required_private if value not in private_text]
    if missing_private:
        raise SystemExit(f"Required signature field missing: {missing_private}")

    secret_patterns = ["api_key", "PRIVATE KEY", "sk-", "D:\\Code\\", "source_response_sha256"]
    secret_hits = [value for value in secret_patterns if value in public_text + private_text]
    if secret_hits:
        raise SystemExit(f"Sensitive material leaked into ethics package: {secret_hits}")

    manifest_checks: dict[str, bool] = {}
    for manifest_path in (public_manifest, private_manifest):
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        for row in payload["files"]:
            path = output / row["path"]
            manifest_checks[f"{manifest_path.name}:{row['path']}"] = path.is_file() and path.stat().st_size == row["bytes"] and sha256(path) == row["sha256"]
    if not all(manifest_checks.values()):
        raise SystemExit("Ethics stage manifest verification failed")

    return {
        "schema": "ethics-signature-package-build-audit-v1",
        "pdf_count": len(pdfs),
        "pdf_pages": pages,
        "public_package": {"zip_entries": public_names, "private_field_hits": privacy_hits, "privacy_separation_passed": True},
        "private_package": {"zip_entries": private_names},
        "required_public_boundary_missing": missing_public,
        "required_private_fields_missing": missing_private,
        "secret_scan": {"patterns": secret_patterns, "hits": secret_hits, "passed": True},
        "stage_manifest_checks": manifest_checks,
        "required_signature_count": 3,
        "real_signature_count": 0,
        "signature_complete": False,
        "institutional_ethics_approval_claimed": False,
        "evidence_boundary": "Prepared blank signing materials only; no person, signature, institutional approval or release authorization is fabricated",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    register_fonts()
    st = styles()
    output = args.output.resolve()
    public_dir = output / "public"
    private_dir = output / "private"
    public_dir.mkdir(parents=True, exist_ok=True)
    private_dir.mkdir(parents=True, exist_ok=True)
    commit = git_output("rev-parse", "HEAD")
    law_sha = sha256(LAW_MANIFEST)
    legal = load(LEGAL_AUDIT)
    video = load(VIDEO_AUDIT)
    expert = load(EXPERT_MANIFEST)
    users = load(USER_MANIFEST)

    declaration_path = public_dir / "伦理与安全合规声明正文.pdf"
    checklist_path = public_dir / "签署前核对清单.pdf"
    build_pdf(declaration_path, "星火智学伦理与安全合规声明", declaration_story(commit, law_sha, legal, video, expert, users, st), FOOTER_LABEL)
    build_pdf(checklist_path, "星火智学伦理与安全签署前核对清单", checklist_story(commit, st), FOOTER_LABEL)
    public_files = [declaration_path, checklist_path]
    signature_path = private_dir / "伦理声明签署页_私密.pdf"
    build_pdf(signature_path, "星火智学伦理与安全合规声明私密签署页", signature_story(commit, sha256(declaration_path), sha256(checklist_path), st), FOOTER_LABEL)
    private_files = [signature_path]

    public_manifest = public_dir / "PUBLIC_MANIFEST.json"
    private_manifest = private_dir / "PRIVATE_MANIFEST.json"
    write_json(public_manifest, manifest("public_ethics_declaration", output, public_files, "Public draft body and checklist; no names or signatures"))
    write_json(private_manifest, manifest("private_signature_sheet", output, private_files, "Offline private storage only; do not commit completed signatures"))
    public_zip = output / "公开伦理声明包_DRAFT.zip"
    private_zip = output / "私密签署页包_DRAFT.zip"
    deterministic_zip(public_zip, output, [*public_files, public_manifest])
    deterministic_zip(private_zip, output, [*private_files, private_manifest])
    public_sha_path = output / f"{public_zip.name}.sha256.txt"
    private_sha_path = output / f"{private_zip.name}.sha256.txt"
    public_sha_path.write_text(f"{sha256(public_zip)}  {public_zip.name}\n", encoding="utf-8")
    private_sha_path.write_text(f"{sha256(private_zip)}  {private_zip.name}\n", encoding="utf-8")

    audit_path = output / "BUILD_AUDIT.json"
    write_json(audit_path, verify(output, public_files, private_files, public_manifest, private_manifest, public_zip, private_zip))
    readme_path = output / "README.md"
    readme_path.write_text(
        f"""# 伦理与安全签署材料包（DRAFT）

构建commit：`{commit}`

1. 团队先复核`public/伦理与安全合规声明正文.pdf`。
2. 逐项完成`public/签署前核对清单.pdf`；未通过项必须先整改。
3. 三名真实责任人在`private/伦理声明签署页_私密.pdf`签署。
4. 签署后计算私密签署页SHA-256并离线保管，不得覆盖或提交到Git。
5. 如比赛要求公开姓名或签名，须另行取得公开授权。

当前`real_signature_count=0`、`signature_complete=false`。团队签署也不等于机构伦理委员会审批或学校授权。
""",
        encoding="utf-8",
    )
    all_files = [*public_files, *private_files, public_manifest, private_manifest, public_zip, private_zip, public_sha_path, private_sha_path, audit_path, readme_path]
    root_manifest = {
        "schema": "ethics-signature-package-manifest-v1",
        "source_git_commit": commit,
        "package_build_date": date(2026, 8, 30).isoformat(),
        "law_manifest_sha256": law_sha,
        "legal_currency_checked_at": legal["checked_at"],
        "legal_currency_passed": legal["target_article_pass_count"],
        "expert_review_complete": expert["evaluation_report"]["all_expert_reviews_complete"],
        "real_participant_count": users["real_participant_count"],
        "video_status": "DRAFT",
        "files": [{"path": path.relative_to(output).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)} for path in sorted(all_files, key=lambda value: value.as_posix())],
        "required_signature_count": 3,
        "real_signature_count": 0,
        "signature_complete": False,
        "institutional_ethics_approval_claimed": False,
        "evidence_boundary": "Blank team responsibility signing materials; not institutional ethics approval, school authorization or proof that pending external validations are complete",
    }
    write_json(output / "MANIFEST.json", root_manifest)
    print(json.dumps({"output": str(output), "pdf_count": len(public_files) + len(private_files), "public_zip": {"sha256": sha256(public_zip), "bytes": public_zip.stat().st_size}, "private_zip": {"sha256": sha256(private_zip), "bytes": private_zip.stat().st_size}, "real_signature_count": 0}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
