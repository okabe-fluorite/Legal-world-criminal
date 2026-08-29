"""Build a QA/contact-sheet package for team review of the narrated demo DRAFT.

The package never marks the video approved. It prepares evidence and blank
approval fields for real content, technical, and privacy reviewers.
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

from PIL import Image, ImageDraw, ImageFont
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
DEFAULT_VIDEO = SUBMISSION / "offline_backup" / "narrated-video-proposed-final" / "星火智学_真实交互演示_AI配音_DRAFT.mp4"
VIDEO_AUDIT = SUBMISSION / "03-Demo" / "NARRATED_VIDEO_DRAFT_AUDIT.json"
DEFAULT_OUTPUT = SUBMISSION / "06-效果验证" / "视频审片包_DRAFT"
FOOTER = "星火智学 · XH-202620 · 视频团队审片材料"
SAMPLE_TIMES = (1.5, 5.0, 8.0, 11.0, 14.0, 17.5, 20.5, 23.0, 28.0, 33.0, 37.0, 39.0, 45.0, 51.0, 57.0, 61.5, 66.0, 69.5, 76.0, 83.0, 90.0, 99.0, 106.0, 114.0, 120.5)


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


def extract_frames(video: Path, output: Path, ffmpeg: str) -> list[Path]:
    frames = output / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    result = []
    for index, second in enumerate(SAMPLE_TIMES, start=1):
        path = frames / f"frame-{index:02d}-{second:05.1f}s.png"
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", str(second), "-i", str(video), "-frames:v", "1", "-vf", "scale=960:-2", "-y", str(path)],
            check=True,
        )
        result.append(path)
    return result


def build_contact_sheet(frames: list[Path], output: Path) -> Path:
    font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 18)
    cols = 5
    width, height = 384, 216
    rows = (len(frames) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * (width + 18) + 18, rows * (height + 42) + 18), (20, 20, 20))
    draw = ImageDraw.Draw(canvas)
    for index, path in enumerate(frames):
        with Image.open(path) as source:
            image = source.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
        x = 18 + (index % cols) * (width + 18)
        y = 18 + (index // cols) * (height + 42)
        canvas.paste(image, (x, y))
        label = f"{SAMPLE_TIMES[index]:05.1f}s"
        draw.text((x, y + height + 6), label, font=font, fill=(238, 238, 238))
    path = output / "25帧视觉接触表.png"
    canvas.save(path, optimize=True)
    return path


def qa_story(audit: dict[str, Any], video: Path, contact_sha: str, st: dict[str, Any]) -> list[Any]:
    media = audit["media"]
    analysis = audit["audio"]["analysis"]
    story: list[Any] = [
        p("121.6秒演示视频 · 技术审片摘要", st["title"]),
        p("DRAFT · 本摘要证明媒体与抽样QA，不代替团队完整播放或最终批准。", st["subtitle"]),
        label_value_table(
            [
                ("源commit", audit["source_git_commit"]),
                ("视频文件", video.name),
                ("视频SHA-256", audit["sha256"]),
                ("接触表SHA-256", contact_sha),
                ("时长/分辨率", f"{audit['duration_seconds']}秒 / {audit['resolution']}"),
                ("编码", f"{media['video_codec']} {media['video_profile']} / {media['audio_codec']} {media['audio_sample_rate']}Hz {media['audio_channels']}声道"),
                ("音频", f"{analysis['integrated_loudness_lufs']} LUFS / 真峰值{analysis['true_peak_dbfs']} dBFS"),
                ("字幕/标识", f"{audit['subtitles']['count']}段中文字幕 / AI配音DRAFT全程标识"),
            ],
            st,
        ),
        Spacer(1, 4 * mm),
        p("一、时间轴", st["h1"]),
    ]
    timeline_data = [[p("镜头", st["cell_bold"]), p("开始", st["cell_bold"]), p("结束", st["cell_bold"]), p("旁白语速", st["cell_bold"])]]
    voice = {row["id"]: row for row in audit["audio"]["voice_items"]}
    for item_id, row in audit["timeline"].items():
        timeline_data.append([p(item_id, st["cell"]), p(f"{row['start_seconds']:.1f}s", st["cell"]), p(f"{row['end_seconds']:.1f}s", st["cell"]), p(f"{voice[item_id]['voice_speed_factor']:.3f}×", st["cell"])])
    table = Table(timeline_data, colWidths=[78 * mm, 30 * mm, 30 * mm, 33 * mm], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("GRID", (0, 0), (-1, -1), 0.35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.extend([table, PageBreak(), p("二、七项强制技术覆盖", st["h1"])])
    coverage_data = [[p("技术", st["cell_bold"]), p("时间", st["cell_bold"]), p("状态", st["cell_bold"])]]
    for row in audit["content_coverage"]["items"]:
        coverage_data.append([p(row["label"], st["cell"]), p(f"{row['start_seconds']:.1f}-{row['end_seconds']:.1f}s", st["cell"]), p("可见" if row["present"] else "缺失", st["cell"])])
    coverage = Table(coverage_data, colWidths=[105 * mm, 38 * mm, 28 * mm], repeatRows=1)
    coverage.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("GRID", (0, 0), (-1, -1), 0.35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.extend(
        [
            coverage,
            Spacer(1, 5 * mm),
            p("三、自动媒体门禁", st["h1"]),
            label_value_table(
                [
                    ("≤180秒", "通过"),
                    ("七项覆盖", f"{audit['content_coverage']['present_count']}/{audit['content_coverage']['required_count']}"),
                    ("最大语速", f"{audit['qa']['max_voice_speed_factor']}× ≤ 1.10×"),
                    ("超过1.2秒静音", f"{analysis['silence_over_threshold_count']}处"),
                    ("字幕", f"{audit['subtitles']['count']}段、最多2行"),
                    ("AI标识", "全程右下角可见"),
                    ("25帧抽检", "已完成；仍需团队完整播放"),
                ],
                st,
            ),
            Spacer(1, 5 * mm),
            p("四、不可外推结论", st["h1"]),
            p("本视频证明软件链路和演示材料可运行，不证明用户认可、学习增益、诊断效度、专家法律结论或机构批准。case3不起诉仍是固定脚本输入下的Agent演示分支。", st["body"]),
        ]
    )
    return story


def review_story(audit: dict[str, Any], st: dict[str, Any]) -> list[Any]:
    checks = [
        ("七项强制技术均清晰可辨", "[时间点/问题]"),
        ("法条名称、条号、原文、来源和版本至少一次清晰可见", "[时间点]"),
        ("错误引用2/2拒绝与专家PENDING同屏", "[时间点]"),
        ("ORCDF、未校准、shadow和迁移边界清晰", "[时间点]"),
        ("微调端点not_connected，不称已完成LoRA/SFT", "[时间点]"),
        ("学生修订与教师HITL闭环清晰", "[时间点]"),
        ("case3固定回答、非用户数据和非专家结论清晰", "[时间点]"),
        ("字幕无遮挡、无错字、旁白清楚且音量一致", "[问题/处置]"),
        ("全片无邮箱、Token、Key、私有路径、内部ID和未授权困惑原文", "[隐私复核]"),
        ("AI配音DRAFT角标全程可见", "[复核]"),
    ]
    data = [[p("确认", st["cell_bold"]), p("审片门禁", st["cell_bold"]), p("记录", st["cell_bold"])]]
    for label, note in checks:
        data.append([p("[  ]", st["center"]), p(label, st["cell"]), p(note, st["cell"])])
    table = Table(data, colWidths=[16 * mm, 105 * mm, 50 * mm], repeatRows=1, rowHeights=[10 * mm] + [14 * mm] * len(checks))
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("GRID", (0, 0), (-1, -1), 0.35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    return [
        p("121.6秒演示视频 · 团队完整审片表", st["title"]),
        p("私密签署页。三名审片人必须完整播放视频；25帧抽检和自动门禁不能代替完整审片。", st["subtitle"]),
        label_value_table([("视频SHA-256", audit["sha256"]), ("源commit", audit["source_git_commit"]), ("审片日期", "[YYYY-MM-DD]")], st),
        Spacer(1, 4 * mm),
        table,
        PageBreak(),
        p("批准结论", st["h1"]),
        p("结论只允许：批准AI配音DRAFT转最终候选 / 替换真人旁白后复审 / 修改画面或字幕后复审 / 拒绝使用。", st["body"]),
        Spacer(1, 5 * mm),
        label_value_table([("内容审片人", "[本人填写/签字]"), ("结论", "[四选一]"), ("问题与处置", "[填写]"), ("日期", "[YYYY-MM-DD]")], st),
        Spacer(1, 8 * mm),
        label_value_table([("技术审片人", "[本人填写/签字]"), ("结论", "[四选一]"), ("问题与处置", "[填写]"), ("日期", "[YYYY-MM-DD]")], st),
        Spacer(1, 8 * mm),
        label_value_table([("隐私/伦理审片人", "[本人填写/签字]"), ("结论", "[四选一]"), ("问题与处置", "[填写]"), ("日期", "[YYYY-MM-DD]")], st),
        Spacer(1, 8 * mm),
        label_value_table([("三人一致最终结论", "[四选一]"), ("签署后本页SHA-256", "[计算后填写]"), ("私密原件位置", "[离线保管]")], st),
    ]


def manifest(stage: str, base: Path, files: list[Path], boundary: str) -> dict[str, Any]:
    return {"schema": "video-review-stage-manifest-v1", "stage": stage, "files": [{"path": file.relative_to(base).as_posix(), "bytes": file.stat().st_size, "sha256": sha256(file)} for file in sorted(files, key=lambda value: value.as_posix())], "boundary": boundary}


def pdf_text(path: Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()
    register_fonts()
    st = styles()
    video = args.video.resolve()
    output = args.output.resolve()
    if not video.is_file():
        raise SystemExit(f"Video not found: {video}")
    audit = load(VIDEO_AUDIT)
    if sha256(video) != audit["sha256"]:
        raise SystemExit("Video SHA does not match public audit")
    public_dir = output / "public"
    private_dir = output / "private"
    public_dir.mkdir(parents=True, exist_ok=True)
    private_dir.mkdir(parents=True, exist_ok=True)
    frames = extract_frames(video, output, args.ffmpeg)
    contact = build_contact_sheet(frames, output)
    qa_pdf = public_dir / "视频技术审计与时间轴.pdf"
    review_pdf = private_dir / "团队完整审片批准表_私密.pdf"
    build_pdf(qa_pdf, "121.6秒演示视频技术审片摘要", qa_story(audit, video, sha256(contact), st), FOOTER)
    build_pdf(review_pdf, "121.6秒演示视频团队完整审片表", review_story(audit, st), FOOTER)
    public_files = [qa_pdf, contact]
    private_files = [review_pdf]
    public_manifest = public_dir / "PUBLIC_MANIFEST.json"
    private_manifest = private_dir / "PRIVATE_MANIFEST.json"
    write_json(public_manifest, manifest("public_video_qa", output, public_files, "Technical and sampled visual QA; not team approval"))
    write_json(private_manifest, manifest("private_full_review_approval", output, private_files, "Blank real-review form; completed signatures stay offline"))
    public_zip = output / "视频技术审片包_DRAFT.zip"
    private_zip = output / "团队审片批准页包_DRAFT.zip"
    deterministic_zip(public_zip, output, [*public_files, public_manifest])
    deterministic_zip(private_zip, output, [*private_files, private_manifest])
    public_sha_path = output / f"{public_zip.name}.sha256.txt"
    private_sha_path = output / f"{private_zip.name}.sha256.txt"
    public_sha_path.write_text(f"{sha256(public_zip)}  {public_zip.name}\n", encoding="utf-8")
    private_sha_path.write_text(f"{sha256(private_zip)}  {private_zip.name}\n", encoding="utf-8")
    public_text = pdf_text(qa_pdf)
    private_text = pdf_text(review_pdf)
    required_public = ["121.6秒", "七项强制技术覆盖", "7/7", "1.037", "0处", "-23.3", "-3.6", "不证明用户认可"]
    missing_public = [value for value in required_public if value not in public_text]
    required_private = ["完整播放", "内容审片人", "技术审片人", "隐私/伦理审片人", "四选一", "签署后本页SHA-256"]
    missing_private = [value for value in required_private if value not in private_text]
    if missing_public or missing_private:
        raise SystemExit(f"Review PDF text gate failed: {missing_public} / {missing_private}")
    secret_patterns = ["api_key", "PRIVATE KEY", "sk-", "D:\\Code\\", "source_response_sha256"]
    secret_hits = [value for value in secret_patterns if value in public_text + private_text]
    if secret_hits:
        raise SystemExit(f"Sensitive review package leak: {secret_hits}")
    build_audit = {
        "schema": "video-review-package-build-audit-v1",
        "video_sha256": audit["sha256"],
        "video_duration_seconds": audit["duration_seconds"],
        "sampled_frame_count": len(frames),
        "content_coverage": audit["content_coverage"],
        "media_qa": audit["qa"],
        "audio_analysis": audit["audio"]["analysis"],
        "public_pdf_pages": len(PdfReader(str(qa_pdf)).pages),
        "private_pdf_pages": len(PdfReader(str(review_pdf)).pages),
        "required_public_missing": missing_public,
        "required_private_missing": missing_private,
        "secret_scan": {"hits": secret_hits, "passed": True},
        "required_reviewer_count": 3,
        "real_approval_count": 0,
        "team_review_complete": False,
        "video_approved": False,
        "evidence_boundary": "Technical QA and blank review form only; the team has not approved the video",
    }
    audit_path = output / "BUILD_AUDIT.json"
    write_json(audit_path, build_audit)
    readme_path = output / "README.md"
    readme_path.write_text(f"""# 121.6秒演示视频审片包（DRAFT）

视频SHA：`{audit['sha256']}`

1. 查看25帧接触表和技术审计PDF。
2. 三名审片人分别完整播放私密视频，不能只看接触表。
3. 内容、技术、隐私/伦理审片人填写私密批准表。
4. 只有三人一致批准后，才能将视频状态从DRAFT改为最终候选。

当前`real_approval_count=0`、`team_review_complete=false`、`video_approved=false`。
""", encoding="utf-8")
    all_files = [*public_files, *private_files, public_manifest, private_manifest, public_zip, private_zip, public_sha_path, private_sha_path, audit_path, readme_path]
    root = {
        "schema": "video-review-package-manifest-v1",
        "source_git_commit": git_output("rev-parse", "HEAD"),
        "package_build_date": date(2026, 8, 30).isoformat(),
        "video_sha256": audit["sha256"],
        "video_duration_seconds": audit["duration_seconds"],
        "files": [{"path": file.relative_to(output).as_posix(), "bytes": file.stat().st_size, "sha256": sha256(file)} for file in sorted(all_files, key=lambda value: value.as_posix())],
        "required_reviewer_count": 3,
        "real_approval_count": 0,
        "team_review_complete": False,
        "video_approved": False,
        "evidence_boundary": "Prepared review evidence and blank private approval form; no review or approval is fabricated",
    }
    write_json(output / "MANIFEST.json", root)
    print(json.dumps({"output": str(output), "video_sha256": audit["sha256"], "sampled_frames": len(frames), "public_zip": sha256(public_zip), "private_zip": sha256(private_zip), "real_approval_count": 0}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
