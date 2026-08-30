"""Regenerate the human-evidence handoff runbook from current DRAFT packages.

The script never creates signatures, expert conclusions, user records, or
approvals.  It only verifies that all blank/public DRAFT packages share one
frozen source commit, checks every ZIP against its SHA sidecar, and writes the
current handoff order and hashes.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
SUBMISSION = REPO / "competition_submission"
OUTPUT = SUBMISSION / "00-提交清单" / "真实人员完成操作单.md"

EXPERT = SUBMISSION / "06-效果验证" / "专家审核包_DRAFT"
USERS = SUBMISSION / "06-效果验证" / "目标用户试用包_DRAFT"
ETHICS = SUBMISSION / "02-伦理与安全" / "伦理签署包_DRAFT"
VIDEO = SUBMISSION / "06-效果验证" / "视频审片包_DRAFT"
EFFECT = SUBMISSION / "06-效果验证" / "效果验证报告包_DRAFT"
PUBLIC = SUBMISSION / "07-公开提交包_DRAFT"


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path) -> str:
    return path.resolve().relative_to(REPO.resolve()).as_posix()


def verified_zip(base: Path, name: str) -> dict[str, Any]:
    path = base / name
    sidecar = base / f"{name}.sha256.txt"
    if not path.is_file() or not sidecar.is_file():
        raise SystemExit(f"Missing ZIP or SHA sidecar: {path} / {sidecar}")
    expected = sidecar.read_text(encoding="utf-8").strip().split()[0].lower()
    actual = sha256(path)
    if expected != actual:
        raise SystemExit(f"ZIP SHA mismatch: {rel(path)} expected={expected} actual={actual}")
    return {"path": rel(path), "sha256": actual, "bytes": path.stat().st_size}


def main() -> int:
    commit = git_output("rev-parse", "HEAD")
    manifests = {
        "专家审核": load(EXPERT / "MANIFEST.json"),
        "目标用户试用": load(USERS / "MANIFEST.json"),
        "伦理签署": load(ETHICS / "MANIFEST.json"),
        "视频审片": load(VIDEO / "MANIFEST.json"),
        "效果报告": load(EFFECT / "MANIFEST.json"),
        "公开提交": load(PUBLIC / "MANIFEST.json"),
    }
    mismatched = {
        name: manifest.get("source_git_commit")
        for name, manifest in manifests.items()
        if manifest.get("source_git_commit") != commit
    }
    if mismatched:
        raise SystemExit(
            f"DRAFT package commits do not match HEAD {commit}: {mismatched}. "
            "Rebuild all packages before refreshing the runbook."
        )

    expert_a = verified_zip(EXPERT, "A阶段_独立判断包_DRAFT.zip")
    expert_b = verified_zip(EXPERT, "B阶段_差异核对包_DRAFT.zip")
    user_private = verified_zip(USERS, "私密知情同意书包_DRAFT.zip")
    user_public = verified_zip(USERS, "去标识试用记录包_DRAFT.zip")
    ethics_public = verified_zip(ETHICS, "公开伦理声明包_DRAFT.zip")
    ethics_private = verified_zip(ETHICS, "私密签署页包_DRAFT.zip")
    video_public = verified_zip(VIDEO, "视频技术审片包_DRAFT.zip")
    video_private = verified_zip(VIDEO, "团队审片批准页包_DRAFT.zip")
    effect_public = verified_zip(EFFECT, "效果验证报告公开包_DRAFT.zip")
    effect_private = verified_zip(EFFECT, "效果报告批准页包_DRAFT.zip")
    public_package = verified_zip(PUBLIC, "星火智学_XH-202620_公开提交包_DRAFT.zip")

    users_manifest = manifests["目标用户试用"]
    ethics_manifest = manifests["伦理签署"]
    video_manifest = manifests["视频审片"]
    effect_manifest = manifests["效果报告"]
    public_manifest = manifests["公开提交"]
    effect_index = load(EFFECT / "public" / "EVIDENCE_INDEX.json")

    if users_manifest.get("real_participant_count") != 0:
        raise SystemExit("Runbook generator only supports the current 0-person DRAFT state")
    if ethics_manifest.get("real_signature_count") != 0:
        raise SystemExit("Runbook generator only supports the current 0-signature DRAFT state")
    if video_manifest.get("real_approval_count") != 0:
        raise SystemExit("Runbook generator only supports the current 0-approval video DRAFT")
    if effect_manifest.get("real_approval_count") != 0:
        raise SystemExit("Runbook generator only supports the current 0-approval report DRAFT")
    if public_manifest.get("ready_for_final_submission") is not False:
        raise SystemExit("Public package must remain DRAFT until all human gates pass")

    short = commit[:12]
    lines = [
        "# XH-202620真实人员完成操作单",
        "",
        "> 本操作单只协调尚未完成的真实人员证据。不得代签、不得用团队自测冒充目标用户、不得让同一模型自评代替法学专家，也不得把空白表或自动门禁改写成真实结论。",
        "",
        "## 当前冻结状态",
        "",
        f"- 统一材料commit：`{commit}`",
        f"- 当前公开包：{public_package['bytes'] / (1024 * 1024):.2f}MiB，SHA-256 `{public_package['sha256']}`",
        f"- 效果报告证据索引：{len(effect_index.get('sources') or [])}项；L2专家、L3真实用户、L4学习效果仍未完成",
        "- 三案例浏览器彩排：3/3、107.25秒、浏览器错误0；这是合成账号L1软件证据",
        "",
        "| 项目 | 材料状态 | 真实完成状态 |",
        "|---|---|---|",
        "| 三题独立专家审核 | A/B两阶段PDF包已在统一commit重建 | 专家未签署 |",
        "| 目标用户试用 | U01/U02私密同意与去标识记录包已在统一commit重建 | 真实参与者0/2 |",
        "| 伦理与安全声明 | 公开正文、核对清单、私密三角色签署页已在统一commit重建 | 真实签名0/3 |",
        "| 121.6秒视频 | 七项技术7/7、技术QA与25帧接触表通过 | 团队完整审片批准0/3 |",
        f"| 效果验证报告 | L1-L4分层PDF与{len(effect_index.get('sources') or [])}项证据索引已就绪 | 报告批准0/3 |",
        f"| 公开提交包 | {public_package['bytes'] / (1024 * 1024):.2f}MiB DRAFT包门禁通过 | 最终提交仍为否 |",
        "",
        "所有签署后原件放入已Git忽略的目录：",
        "",
        "`competition_submission/offline_backup/human-evidence/`",
        "",
        "禁止把签名、姓名、联系方式、同意书原件或私密批准表提交Git。",
        "",
        "## 1. 独立法学专家：严格先A后B",
        "",
        "### 1.1 只发送A阶段",
        "",
        f"- 文件：`{expert_a['path']}`",
        f"- SHA-256：`{expert_a['sha256']}`",
        "- 不得同时发送B包、标准答案草案或自动门禁结果。",
        "- 专家签署并锁定A阶段时间后，保存到`offline_backup/human-evidence/expert/A/A阶段审核表_已签署.pdf`，再进入B阶段。",
        "",
        "### 1.2 再发送B阶段",
        "",
        f"- 文件：`{expert_b['path']}`",
        f"- SHA-256：`{expert_b['sha256']}`",
        "- 保存签署结果到`offline_backup/human-evidence/expert/B/B阶段复核表_已签署.pdf`。",
        "- 如结论为修改后发布/拒绝，保留旧run并整改复签，不能删除不利意见。",
        "",
        "## 2. 两名真实目标用户：同意书私密、记录去标识",
        "",
        f"- 私密同意书包：`{user_private['path']}`，SHA-256 `{user_private['sha256']}`",
        f"- 去标识记录包：`{user_public['path']}`，SHA-256 `{user_public['sha256']}`",
        f"- U01、U02必须使用独立虚构账号、统一commit `{short}`、同一法源和统一T1-T4。",
        "- 每项最多一次不含答案的中性提示，主持人不得代替操作；开发者或队内自测不能冒充目标用户。",
        "- 私密同意书保存到`offline_backup/human-evidence/users/private/`；去标识记录保存到`offline_backup/human-evidence/users/public-candidate/`。",
        "- 只汇总有效n、中位数、范围和经授权原话；2人样本不做显著性检验。",
        "",
        "## 3. 伦理与安全：先核对、后三人签署",
        "",
        f"- 公开材料：`{ethics_public['path']}`，SHA-256 `{ethics_public['sha256']}`",
        f"- 私密签署页：`{ethics_private['path']}`，SHA-256 `{ethics_private['sha256']}`",
        "- 逐项核对后，由团队负责人、指导教师、数据/安全责任人真实签署。",
        "- 保存到`offline_backup/human-evidence/ethics/伦理声明签署页_已签署.pdf`。",
        "- 团队签署是责任声明，不等于机构伦理委员会审批或学校授权。",
        "",
        "## 4. 视频：三名审片人必须完整播放",
        "",
        f"- 技术审片包：`{video_public['path']}`，SHA-256 `{video_public['sha256']}`",
        f"- 私密批准页：`{video_private['path']}`，SHA-256 `{video_private['sha256']}`",
        "- 内容、技术、隐私/伦理三名审片人各自完整播放121.6秒视频；25帧接触表不能代替完整审片。",
        "- 签署后保存到`offline_backup/human-evidence/video/团队完整审片批准表_已签署.pdf`。",
        "- 只有三人一致批准，才能把`video_approved`改为真；否则先修改并复审。",
        "",
        "## 5. 效果验证报告：三角色只批准当前证据边界",
        "",
        f"- 公开报告包：`{effect_public['path']}`，SHA-256 `{effect_public['sha256']}`",
        f"- 私密批准页：`{effect_private['path']}`，SHA-256 `{effect_private['sha256']}`",
        "- 内容、数据、教学三名复核人核对公开PDF和`EVIDENCE_INDEX.json`。",
        "- 保存到`offline_backup/human-evidence/effect-report/效果验证报告批准表_已签署.pdf`。",
        "- 即使批准当前DRAFT，缺少L2/L3/L4时也不得改称学习效果最终报告。",
        "",
        "## 6. 完成后如何继续",
        "",
        "不要手工修改MANIFEST、BUILD_AUDIT、PPT数字或ready状态。将真实材料放入离线目录后，在本任务中回复：",
        "",
        "> 真实专家、用户、伦理、视频和报告材料已经放入`competition_submission/offline_backup/human-evidence/`，请继续验收并生成最终包。",
        "",
        "后续依次验证签署角色/日期/结论/SHA，仅回写允许公开的去标识结果，重建PPT、视频、报告与公开包，并在干净tracked工作树运行最终审计。只有全部门禁通过后才能把`ready_for_final_submission`设为`true`。",
        "",
        "## 7. 当前可供队友预览的DRAFT包",
        "",
        f"- 文件：`{public_package['path']}`",
        f"- SHA-256：`{public_package['sha256']}`",
        "- 只用于队内预览与材料检查，不得作为最终提交或学习效果证明。",
        "",
    ]
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "source_git_commit": commit,
                "package_count": len(manifests),
                "verified_zip_count": 11,
                "public_package_sha256": public_package["sha256"],
                "real_participant_count": 0,
                "real_signature_count": 0,
                "video_real_approval_count": 0,
                "report_real_approval_count": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
