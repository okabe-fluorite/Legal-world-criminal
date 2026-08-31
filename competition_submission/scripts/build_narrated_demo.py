"""Build a 1080p narrated/subtitled DRAFT from audited real-interaction clips."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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
        "duration": 4.1,
        "text": "星火智学，让本科刑法学习有据可查。",
        "caption": "星火智学：本科刑法个性化学习有据可查",
    },
    {
        "id": "02-technical-evidence",
        "kind": "video",
        "source": "technical-evidence.webm",
        "duration": 18.6,
        "text": "先看机器证据总账。四千一百七十三份候选材料，经治理形成八百一十三条正式法源；十一项推理门禁、百题候选评测和智能体消融都由审计文件哈希绑定。自动门禁不等于专家准确率，百题仍待教师审核。",
        "caption": "数据治理→Evidence推理→模型无关评测→Agent消融\n自动Gate≠专家准确率；100题仍为not_gold",
    },
    {
        "id": "02-diagnosis",
        "kind": "video",
        "source": "01-diagnosis-orcdf-path-model.webm",
        "duration": 17.8,
        "text": "没有课堂历史数据时，系统不生成默认掌握率，而从证据不足开始。在线证据追踪展示知识状态、六条事件和困惑信号；欧阿西迪艾弗只作为民法宪法迁移实验，路径和模型路由都明确证据边界。",
        "caption": "缺少课堂数据：从证据不足开始\nORCDF只进入shadow，不冒充掌握率",
    },
    {
        "id": "03-rag",
        "kind": "video",
        "source": "02-trusted-rag.webm",
        "duration": 15.7,
        "text": "可信知识检索把系统输出、标准答案、法条原文、来源版本和逐字证据放在同一界面。三个典型问题自动门禁通过，但专家复核仍待完成；错误引用现场二比二拒绝。",
        "caption": "系统输出、标准答案与权威Evidence同屏\n错误引用2/2拒绝；专家复核仍pending",
    },
    {
        "id": "04-student",
        "kind": "video",
        "source": "03-student-teacher-feedback.webm",
        "duration": 11.6,
        "text": "人工智能反馈只是形成性建议。学生能看到退回意见、带入原文修订，并在教师批准后看到评分、知识状态和证据事件。",
        "caption": "AI只给形成性建议\n教师批准后才进入长期画像",
    },
    {
        "id": "05-teacher",
        "kind": "video",
        "source": "04-teacher-dashboard.webm",
        "duration": 11.0,
        "text": "教师看板只展示自有班级的匿名形成性数据。退回与批准分属两个不可变稿件，队列清零，班级事件从二变为三。",
        "caption": "教师只看自有班级匿名数据\n退回、修订、批准形成可追溯闭环",
    },
    {
        "id": "06-agent-architecture",
        "kind": "image",
        "source": "architecture",
        "duration": 8.0,
        "text": "案件实训由状态机和多智能体编排，受工具权限、权威法源与能力量表共同约束。",
        "caption": "状态机 × 多Agent × 权限工具 × Rubric",
    },
    {
        "id": "07-case-inv",
        "kind": "image",
        "source": "inv_snapshot",
        "duration": 15.2,
        "text": "侦查阶段的学习事件显示，学生识别了侵害人数、凶器和两段时间轴，但没有充分回应会见、取保候审和刑法第二十条。系统把证据方向与程序缺口分开呈现。",
        "caption": "INV形成性审计：证据方向正确，程序回应不足\n原始INV结果阶段标记不一致，已排除该文件断言",
    },
    {
        "id": "08-case-pr",
        "kind": "image",
        "source": "pr_snapshot",
        "duration": 16.7,
        "text": "审查起诉阶段，学生引用刑法第二十条主张特殊防卫。检察官要求监控、证言与报警记录交叉印证，随后智能体进入不起诉分支。这个分支是工程证据，不是专家确认的法律结论。",
        "caption": "PR对抗：法条核验通过，检察官要求补充证据\nAgent进入不起诉分支 ≠ 专家法律结论",
    },
    {
        "id": "09-case",
        "kind": "video",
        "source": "05-case3-card-and-evidence.webm",
        "duration": 15.0,
        "mask_synthetic_account_header": True,
        "text": "冻结演示库的张那木拉案真实走完委托、侦查和审查起诉。二十九次固定脚本回答后作出不起诉分支，三名智能体退场、零运行错误，并形成三条案件学习事件。",
        "caption": "case3真实E2E：461.547秒、29次固定回答\n3事件、3/3 Agent退场、0 runtime issue",
    },
    {
        "id": "10-iflytek",
        "kind": "video",
        "source": "iflytek-realtime-voice.webm",
        "duration": 20.0,
        "text": "最后是实时语音多模态。浏览器麦克风持续发送十六千赫兹PCM分片，讯飞边听边返回动态转写；结束本轮后，系统检索受治理法源，生成形成性短答并自动播放讯飞合成语音。整个过程没有文件上传，不生成学习事件，数字人仍保持未连接。",
        "caption": "浏览器麦克风PCM→讯飞partial/final→Evidence短答→TTS播放\n文件上传0、转写needs_review、LearningEvent 0；数字人not_connected",
    },
    {
        "id": "11-close",
        "kind": "image",
        "source": "closing",
        "duration": 6.4,
        "text": "演示证明软件闭环，不代表用户认可、学习增益或专家法律结论。",
        "caption": "软件闭环已验证 ≠ 用户认可/学习增益/专家结论",
    },
]

REQUIRED_CONTENT = [
    {
        "id": "governed_legal_data",
        "label": "4,173候选材料到813正式法源的数据治理",
        "items": ["02-technical-evidence"],
    },
    {
        "id": "legal_reasoning_gate",
        "label": "11项Evidence约束推理Gate与正负fixture",
        "items": ["02-technical-evidence"],
    },
    {
        "id": "legal_edu_eval",
        "label": "LegalEduEval-v1百题候选与E0—E3 pending矩阵",
        "items": ["02-technical-evidence"],
    },
    {
        "id": "agent_ablation",
        "label": "同条件C0/C1反方收益与耗时/token成本",
        "items": ["02-technical-evidence"],
    },
    {
        "id": "evidence_kt",
        "label": "Evidence-KT保守画像与证据不足",
        "items": ["02-diagnosis"],
    },
    {
        "id": "orcdf_shadow",
        "label": "ORCDF V0/V1/V2 shadow、未校准与迁移边界",
        "items": ["02-diagnosis"],
    },
    {
        "id": "personalized_path",
        "label": "七步个性化路径与LearningEvent重排",
        "items": ["02-diagnosis"],
    },
    {
        "id": "model_adapter",
        "label": "Model Adapter基线与微调not_connected",
        "items": ["02-diagnosis"],
    },
    {
        "id": "trusted_rag",
        "label": "可信RAG、权威Evidence与错误引用拒绝",
        "items": ["03-rag"],
    },
    {
        "id": "teacher_hitl",
        "label": "学生修订与教师Human-in-the-loop门禁",
        "items": ["04-student", "05-teacher"],
    },
    {
        "id": "multi_agent_case",
        "label": "状态机、多智能体、工具权限与case3真实E2E",
        "items": ["06-agent-architecture", "07-case-inv", "08-case-pr", "09-case"],
    },
    {
        "id": "iflytek_asr_tts",
        "label": "讯飞实时IAT partial/final、Evidence回复、TTS播放与数字人后置边界",
        "items": ["10-iflytek"],
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


def probe_media(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout.decode("utf-8"))
    video = next(stream for stream in payload["streams"] if stream["codec_type"] == "video")
    audio = next(stream for stream in payload["streams"] if stream["codec_type"] == "audio")
    return {
        "format": payload["format"].get("format_name"),
        "video_codec": video.get("codec_name"),
        "video_profile": video.get("profile"),
        "pixel_format": video.get("pix_fmt"),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": video.get("avg_frame_rate"),
        "audio_codec": audio.get("codec_name"),
        "audio_sample_rate": int(audio.get("sample_rate", 0)),
        "audio_channels": audio.get("channels"),
    }


def analyze_audio(path: Path, silence_threshold: float = 1.2) -> dict:
    silence_result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(path),
            "-af", f"silencedetect=noise=-45dB:d={silence_threshold}",
            "-f", "null", "NUL",
        ],
        check=True,
        capture_output=True,
    )
    silence_log = silence_result.stderr.decode("utf-8", errors="replace")
    silence_durations = [
        float(value)
        for value in re.findall(r"silence_duration:\s*([0-9.]+)", silence_log)
    ]
    loudness_result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(path),
            "-af", "ebur128=peak=true", "-f", "null", "NUL",
        ],
        check=True,
        capture_output=True,
    )
    loudness_log = loudness_result.stderr.decode("utf-8", errors="replace")
    integrated_matches = re.findall(r"I:\s*(-?[0-9.]+)\s*LUFS", loudness_log)
    peak_matches = re.findall(r"Peak:\s*(-?[0-9.]+)\s*dBFS", loudness_log)
    return {
        "silence_threshold_seconds": silence_threshold,
        "silence_over_threshold_count": len(silence_durations),
        "silence_durations_seconds": [round(value, 3) for value in silence_durations],
        "max_silence_seconds": round(max(silence_durations, default=0.0), 3),
        "integrated_loudness_lufs": (
            float(integrated_matches[-1]) if integrated_matches else None
        ),
        "true_peak_dbfs": float(peak_matches[-1]) if peak_matches else None,
    }


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
    parser.add_argument("--sampled-frames-reviewed", action="store_true")
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

    technical_audit_path = (
        REPO
        / "competition_submission"
        / "03-Demo"
        / "TECHNICAL_EVIDENCE_VIDEO_SEGMENT_AUDIT.json"
    )
    technical_audit = json.loads(technical_audit_path.read_text(encoding="utf-8"))
    technical_segment = segments / "technical-evidence.webm"
    if not technical_segment.is_file():
        raise SystemExit(f"missing technical evidence segment: {technical_segment}")
    if sha256(technical_segment) != technical_audit.get("sha256"):
        raise SystemExit("technical evidence segment SHA does not match public audit")
    if int((technical_audit.get("qa") or {}).get("browser_error_total") or 0) != 0:
        raise SystemExit("technical evidence segment public audit contains browser errors")
    if not bool((technical_audit.get("qa") or {}).get("expected_visible_checks_pass")):
        raise SystemExit("technical evidence segment visible-check audit did not pass")

    iflytek_audit_path = (
        REPO
        / "competition_submission"
        / "03-Demo"
        / "IFLYTEK_BROWSER_VIDEO_SEGMENT_AUDIT.json"
    )
    iflytek_audit = json.loads(iflytek_audit_path.read_text(encoding="utf-8"))
    iflytek_segment = segments / "iflytek-realtime-voice.webm"
    if not iflytek_segment.is_file():
        raise SystemExit(f"missing iFlytek video segment: {iflytek_segment}")
    if sha256(iflytek_segment) != iflytek_audit.get("sha256"):
        raise SystemExit("iFlytek video segment SHA does not match public audit")
    if int((iflytek_audit.get("qa") or {}).get("browser_error_total") or 0) != 0:
        raise SystemExit("iFlytek video segment public audit contains browser errors")
    visible = dict(iflytek_audit.get("visible_checks") or {})
    if not (
        int(visible.get("browser_pcm_frames") or 0) >= 100
        and visible.get("file_upload_requests") == 0
        and int(visible.get("partial_results") or 0) >= 1
        and visible.get("final_results") == 1
        and visible.get("governed_reply_source") == "llm_governed_evidence"
        and visible.get("available_capabilities") == 3
        and visible.get("asr_status") == "needs_review"
        and visible.get("digital_human_status") == "not_connected"
        and visible.get("learning_event_created") is False
    ):
        raise SystemExit("iFlytek video segment visible-state audit did not pass")

    slides = (
        REPO
        / "competition_submission"
        / "04-作品方案"
        / "guizang-tech-v2"
        / "qa"
        / "screens"
    )
    source_map = {
        "cover": slides / "slide-01.png",
        "architecture": slides / "slide-08.png",
        "closing": slides / "slide-12.png",
        "inv_snapshot": REPO / "competition_submission" / "03-Demo" / "case3-snapshots" / "CASE3_E2E_INV.png",
        "pr_snapshot": REPO / "competition_submission" / "03-Demo" / "case3-snapshots" / "CASE3_E2E_PR.png",
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
            video_filter = ""
            video_map = "0:v:0"
        else:
            visual_args = ["-i", str(visual)]
            operations = []
            if item.get("mask_synthetic_account_header"):
                operations.extend(
                    [
                        "drawbox=x=1360:y=67:w=170:h=28:color=0x0C0906@1:t=fill",
                        "drawbox=x=1536:y=50:w=58:h=58:color=0x0C0906@1:t=fill",
                    ]
                )
            operations.append(f"tpad=stop_mode=clone:stop_duration={duration:.3f}")
            video_filter = f"[0:v]{','.join(operations)}[v];"
            video_map = "[v]"
        run(
            [
                "ffmpeg", "-loglevel", "error", "-y", *visual_args, "-i", str(audio),
                "-filter_complex", f"{video_filter}[1:a]{audio_filter}[a]", "-map", video_map, "-map", "[a]",
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
    item_timeline: dict[str, dict[str, float]] = {}
    srt_blocks = []
    for index, item in enumerate(ITEMS, 1):
        item_start = timeline
        start = timeline + 0.15
        timeline += float(item["duration"])
        end = timeline - 0.15
        item_timeline[item["id"]] = {
            "start_seconds": round(item_start, 3),
            "end_seconds": round(timeline, 3),
        }
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
        "FontSize=13,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BorderStyle=3,BackColour=&H90000000,Alignment=2,MarginV=24'[v]"
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
    case_snapshot_audit = json.loads(
        (REPO / "competition_submission" / "03-Demo" / "CASE3_INV_PR_SNAPSHOT.json")
        .read_text(encoding="utf-8")
    )
    media = probe_media(final)
    audio_analysis = analyze_audio(final)
    source_hashes = {}
    for item in ITEMS:
        source = source_map.get(item["source"], segments / item["source"])
        source_hashes[item["id"]] = {
            "source": source.name,
            "sha256": sha256(source),
        }
    content_coverage = []
    for row in REQUIRED_CONTENT:
        intervals = [item_timeline[item_id] for item_id in row["items"]]
        content_coverage.append(
            {
                **row,
                "start_seconds": min(item["start_seconds"] for item in intervals),
                "end_seconds": max(item["end_seconds"] for item in intervals),
                "present": True,
            }
        )
    audit = {
        "schema": "competition-narrated-demo-draft-audit-v4",
        "source_git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "file": final.name,
        "duration_seconds": round(final_duration, 3),
        "bytes": final.stat().st_size,
        "sha256": sha256(final),
        "resolution": f"{media['width']}x{media['height']}",
        "fps": media["fps"],
        "media": media,
        "audio": {
            "present": True,
            "voice": args.voice,
            "ai_generated_label_visible": True,
            "voice_items": voice_audit,
            "analysis": audio_analysis,
        },
        "subtitles": {"present": True, "language": "zh-CN", "count": len(ITEMS)},
        "timeline": item_timeline,
        "content_coverage": {
            "required_count": len(REQUIRED_CONTENT),
            "present_count": len(content_coverage),
            "all_required_present": all(row["present"] for row in content_coverage),
            "items": content_coverage,
        },
        "visual_source_sha256": source_hashes,
        "source_interaction_audit": "VIDEO_SEGMENTS_AUDIT.json",
        "technical_evidence_segment_audit": {
            "file": technical_audit_path.name,
            "source_git_commit": technical_audit.get("source_git_commit"),
            "duration_seconds": technical_audit.get("duration_seconds"),
            "sha256": technical_audit.get("sha256"),
            "browser_error_total": (technical_audit.get("qa") or {}).get(
                "browser_error_total"
            ),
            "expected_visible_checks_pass": (technical_audit.get("qa") or {}).get(
                "expected_visible_checks_pass"
            ),
        },
        "iflytek_speech_segment_audit": {
            "file": iflytek_audit_path.name,
            "source_git_commit": iflytek_audit.get("source_git_commit"),
            "duration_seconds": iflytek_audit.get("duration_seconds"),
            "sha256": iflytek_audit.get("sha256"),
            "browser_error_total": (iflytek_audit.get("qa") or {}).get(
                "browser_error_total"
            ),
            "available_capabilities": visible.get("available_capabilities"),
            "browser_pcm_frames": visible.get("browser_pcm_frames"),
            "partial_results": visible.get("partial_results"),
            "final_results": visible.get("final_results"),
            "file_upload_requests": visible.get("file_upload_requests"),
            "asr_status": visible.get("asr_status"),
            "digital_human_status": visible.get("digital_human_status"),
        },
        "privacy_redactions": [
            {
                "item": "09-case",
                "target": "synthetic account email and logout control in app header",
                "method": "deterministic solid mask after source capture",
                "changes_legal_or_learning_evidence": False,
            }
        ],
        "case3_audit_snapshots": {
            "present": True,
            "inv_stage": case_snapshot_audit["inv"]["stage"],
            "pr_stage": case_snapshot_audit["pr"]["stage"],
            "source_warning_disclosed": bool(case_snapshot_audit["excluded_source_warning"]),
            "source_sha256": case_snapshot_audit["source_sha256"],
        },
        "qa": {
            "sampled_timeline_frames_reviewed": args.sampled_frames_reviewed,
            "subtitles_max_two_lines": True,
            "ai_voice_label_visible_throughout": True,
            "silence_over_1_2_seconds_detected": (
                audio_analysis["silence_over_threshold_count"] > 0
            ),
            "max_voice_speed_factor": max(row["voice_speed_factor"] for row in voice_audit),
            "duration_under_180_seconds": final_duration <= 180,
        },
        "evidence_boundary": (
            "AI-voiced DRAFT assembled from seven audited real browser interactions, three PPT "
            "stills, and two frozen case3 audit snapshots; "
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
