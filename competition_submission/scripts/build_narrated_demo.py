"""Build a 1080p narrated/subtitled DRAFT from audited real-interaction clips."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


REPO = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent

ITEMS = [
    {
        "id": "01-cover",
        "kind": "image",
        "source": "cover",
        "duration": 3.5,
        "text": "星火智学，让本科刑法学习有据可查。",
        "caption": "星火智学：本科刑法个性化学习有据可查",
    },
    {
        "id": "02-diagnosis",
        "kind": "video",
        "source": "01-diagnosis-orcdf-path-model.webm",
        "duration": 17.48,
        "text": "没有课堂历史数据时，系统不生成默认掌握率，而从证据不足开始。在线证据追踪展示知识状态、六条事件和困惑信号；欧阿西迪艾弗只作为民法宪法迁移实验，路径和模型路由都明确证据边界。",
        "caption": "缺少课堂数据：从证据不足开始\nORCDF只进入shadow，不冒充掌握率",
    },
    {
        "id": "03-rag",
        "kind": "video",
        "source": "02-trusted-rag.webm",
        "duration": 15.48,
        "text": "可信知识检索把系统输出、标准答案、法条原文、来源版本和逐字证据放在同一界面。三个典型问题自动门禁通过，但专家复核仍待完成；错误引用现场二比二拒绝。",
        "caption": "系统输出、标准答案与权威Evidence同屏\n错误引用2/2拒绝；专家复核仍pending",
    },
    {
        "id": "04-student",
        "kind": "video",
        "source": "03-student-teacher-feedback.webm",
        "duration": 9.28,
        "text": "人工智能反馈只是形成性建议。学生能看到退回意见、带入原文修订，并在教师批准后看到评分、知识状态和证据事件。",
        "caption": "AI只给形成性建议\n教师批准后才进入长期画像",
    },
    {
        "id": "05-teacher",
        "kind": "video",
        "source": "04-teacher-dashboard.webm",
        "duration": 11.08,
        "text": "教师看板只展示自有班级的匿名形成性数据。退回与批准分属两个不可变稿件，队列清零，班级事件从二变为三。",
        "caption": "教师只看自有班级匿名数据\n退回、修订、批准形成可追溯闭环",
    },
    {
        "id": "06-agent-architecture",
        "kind": "image",
        "source": "architecture",
        "duration": 4.5,
        "text": "案件实训由状态机和多智能体编排，受工具权限、权威法源与能力量表共同约束。",
        "caption": "状态机 × 多Agent × 权限工具 × Rubric",
    },
    {
        "id": "07-case",
        "kind": "video",
        "source": "05-case3-card-and-evidence.webm",
        "duration": 11.92,
        "text": "冻结演示库的张那木拉案真实走完委托、侦查和审查起诉。二十九次固定脚本回答后作出不起诉分支，三名智能体退场、零运行错误，并形成三条案件学习事件。",
        "caption": "case3真实E2E：461.547秒、29次固定回答\n3事件、3/3 Agent退场、0 runtime issue",
    },
    {
        "id": "08-close",
        "kind": "image",
        "source": "closing",
        "duration": 3.5,
        "text": "演示证明软件闭环，不代表用户认可、学习增益或专家法律结论。",
        "caption": "软件闭环已验证 ≠ 用户认可/学习增益/专家结论",
    },
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(args: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def atempo_chain(factor: float) -> str:
    parts: list[float] = []
    while factor > 2.0:
        parts.append(2.0)
        factor /= 2.0
    while factor < 0.5:
        parts.append(0.5)
        factor /= 0.5
    parts.append(factor)
    return ",".join(f"atempo={value:.5f}" for value in parts)


def srt_time(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segments", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--public-audit", type=Path, required=True)
    parser.add_argument("--voice", default="Microsoft Huihui Desktop")
    args = parser.parse_args()

    segments = args.segments.resolve()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"output directory must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    pieces = output / "pieces"
    voice_dir = output / "voice"
    pieces.mkdir()
    voice_dir.mkdir()

    slides = REPO / "competition_submission" / "04-作品方案" / "guizang" / "qa" / "screens"
    source_map = {
        "cover": slides / "slide-01.png",
        "architecture": slides / "slide-09.png",
        "closing": slides / "slide-12.png",
    }
    for item in ITEMS:
        source = source_map.get(item["source"], segments / item["source"])
        if not source.is_file():
            raise SystemExit(f"missing visual source: {source}")

    spec = output / "narration-spec.json"
    spec.write_text(
        json.dumps(
            [{"id": item["id"], "text": item["text"]} for item in ITEMS],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(SCRIPT_DIR / "synthesize_narration.ps1"), "-Spec", str(spec),
            "-OutputDir", str(voice_dir), "-Voice", args.voice, "-Rate", "2",
        ]
    )

    piece_paths: list[Path] = []
    voice_audit: list[dict] = []
    for item in ITEMS:
        duration = float(item["duration"])
        visual = source_map.get(item["source"], segments / item["source"])
        audio = voice_dir / f"{item['id']}.wav"
        audio_duration = probe_duration(audio)
        target_speech = max(1.0, duration - 0.35)
        speed = max(1.0, audio_duration / target_speech)
        audio_filter = f"{atempo_chain(speed)},apad=pad_dur={duration:.3f}"
        piece = pieces / f"{item['id']}.mp4"
        if item["kind"] == "image":
            visual_args = ["-loop", "1", "-framerate", "25", "-i", str(visual)]
        else:
            visual_args = ["-i", str(visual)]
        run(
            [
                "ffmpeg", "-loglevel", "error", "-y", *visual_args, "-i", str(audio),
                "-filter_complex", f"[1:a]{audio_filter}[a]", "-map", "0:v:0", "-map", "[a]",
                "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-pix_fmt", "yuv420p", "-r", "25", "-c:a", "aac", "-b:a", "160k",
                "-ar", "48000", "-ac", "2", str(piece),
            ]
        )
        piece_paths.append(piece)
        voice_audit.append(
            {
                "id": item["id"],
                "visual_duration_seconds": duration,
                "raw_voice_duration_seconds": round(audio_duration, 3),
                "voice_speed_factor": round(speed, 5),
            }
        )

    concat = output / "concat-private.txt"
    concat.write_text(
        "\n".join(f"file '{piece.as_posix()}'" for piece in piece_paths) + "\n",
        encoding="utf-8",
    )
    pre = output / "pre-subtitles.mp4"
    run(
        [
            "ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat), "-c", "copy", str(pre),
        ]
    )

    timeline = 0.0
    srt_blocks = []
    for index, item in enumerate(ITEMS, 1):
        start = timeline + 0.15
        timeline += float(item["duration"])
        end = timeline - 0.15
        srt_blocks.append(
            f"{index}\n{srt_time(start)} --> {srt_time(end)}\n{item['caption']}\n"
        )
    srt = output / "narration.srt"
    srt.write_text("\n".join(srt_blocks), encoding="utf-8-sig")

    label = output / "ai-voice-label.png"
    image = Image.new("RGBA", (270, 52), (0, 47, 167, 235))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 22)
    draw.text((15, 10), "AI配音 · DRAFT", font=font, fill=(255, 255, 255, 255))
    image.save(label)

    final = output / "星火智学_真实交互演示_AI配音_DRAFT.mp4"
    pre_duration = probe_duration(pre)
    filter_graph = (
        "[0:v]scale=1920:1080[v0];"
        "[v0][1:v]overlay=W-w-24:H-h-24[v1];"
        "[v1]subtitles=narration.srt:force_style='FontName=Microsoft YaHei,"
        "FontSize=15,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BorderStyle=3,BackColour=&H90000000,Alignment=2,MarginV=42'[v]"
    )
    run(
        [
            "ffmpeg", "-loglevel", "error", "-y", "-i", str(pre),
            "-loop", "1", "-i", str(label),
            "-filter_complex", filter_graph, "-map", "[v]", "-map", "0:a:0",
            "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-t", f"{pre_duration:.3f}",
            "-movflags", "+faststart", str(final),
        ],
        cwd=output,
    )

    final_duration = probe_duration(final)
    audit = {
        "schema": "competition-narrated-demo-draft-audit-v1",
        "file": final.name,
        "duration_seconds": round(final_duration, 3),
        "bytes": final.stat().st_size,
        "sha256": sha256(final),
        "resolution": "1920x1080",
        "fps": 25,
        "audio": {
            "present": True,
            "voice": args.voice,
            "ai_generated_label_visible": True,
            "voice_items": voice_audit,
        },
        "subtitles": {"present": True, "language": "zh-CN", "count": len(ITEMS)},
        "source_interaction_audit": "VIDEO_SEGMENTS_AUDIT.json",
        "evidence_boundary": (
            "AI-voiced DRAFT assembled from audited real browser interactions and three PPT stills; "
            "not the final team-approved submission, not target-user evidence, and not expert validation"
        ),
    }
    public = args.public_audit.resolve()
    public.parent.mkdir(parents=True, exist_ok=True)
    public.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
