"""Run real iFlytek TTS -> IAT verification without publishing credentials."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
for entry in (REPO, BACKEND):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import start as local_start  # noqa: E402
from src.media.providers import IflytekSpeechProvider  # noqa: E402


DEFAULT_TEXT = "罪刑法定原则要求法无明文规定不为罪，法无明文规定不处罚。"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", value).lower()


def inside_repo(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(REPO.resolve()):
        raise SystemExit(f"output must stay inside repository: {path.name}")
    return resolved


def write_wav(path: Path, pcm: bytes, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm)


def wav_metadata(path: Path) -> dict:
    with wave.open(str(path), "rb") as audio:
        frames = audio.getnframes()
        sample_rate = audio.getframerate()
        return {
            "channels": audio.getnchannels(),
            "sample_width_bytes": audio.getsampwidth(),
            "sample_rate_hz": sample_rate,
            "frames": frames,
            "duration_seconds": round(frames / sample_rate, 3),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--audio-output",
        type=Path,
        default=REPO / "competition_submission" / "03-Demo" / "iflytek-speech" / "iflytek-tts-verification.wav",
    )
    parser.add_argument(
        "--public-audit",
        type=Path,
        default=REPO / "competition_submission" / "03-Demo" / "IFLYTEK_ASR_TTS_VERIFICATION.json",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=REPO / "docs" / "IFLYTEK_ASR_TTS_VERIFICATION.md",
    )
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--voice", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    config = args.config.resolve()
    if not config.is_file():
        raise SystemExit("iFlytek config file not found")
    audio_path = inside_repo(args.audio_output)
    audit_path = inside_repo(args.public_audit)
    report_path = inside_repo(args.report)
    for output in (audio_path, audit_path, report_path):
        if output.exists() and not args.force:
            raise SystemExit(f"output already exists: {output.name}; pass --force to replace")

    env = dict(os.environ)
    local_start.apply_iflytek_config(env, config)
    required = ("XFYUN_APP_ID", "XFYUN_API_KEY", "XFYUN_API_SECRET")
    if not all(str(env.get(name) or "").strip() for name in required):
        raise SystemExit("APPID/APIKey/APISecret are not all configured")
    previous = {name: os.environ.get(name) for name in required}
    try:
        for name in required:
            os.environ[name] = env[name]
        provider = IflytekSpeechProvider.from_environment()
        voice = args.voice or str(env.get("XFYUN_TTS_VOICE") or "xiaoyan")
        tts = provider.synthesize(text=args.text, voice=voice, audio_format="wav")
        write_wav(audio_path, tts.audio, tts.sample_rate)
        iat = provider.transcribe(
            audio=tts.audio,
            language="zh_cn",
            encoding="raw",
            sample_rate=tts.sample_rate,
        )
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    expected = normalize_text(args.text)
    actual = normalize_text(iat.transcript)
    similarity = difflib.SequenceMatcher(a=expected, b=actual).ratio()
    required_terms = ["罪刑法定", "明文规定", "不为罪", "不处罚"]
    term_checks = {term: term in iat.transcript for term in required_terms}
    metadata = wav_metadata(audio_path)
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
    ).strip()
    audit = {
        "schema_version": "iflytek-asr-tts-real-verification-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_git_commit": source_commit,
        "provider": "iFlytek WebSocket API",
        "real_network_calls": {"tts": 1, "iat": 1},
        "credentials": {
            "names": list(required),
            "configured": True,
            "values_published": False,
        },
        "tts": {
            "status": "succeeded",
            "request_text": args.text,
            "voice": voice,
            "audio_file": audio_path.relative_to(REPO).as_posix(),
            "audio_bytes": audio_path.stat().st_size,
            "audio_sha256": sha256(audio_path),
            "provider_session_present": bool(tts.provider_sid),
            "wav": metadata,
            "ai_generated_disclosure": True,
        },
        "asr": {
            "status": "succeeded_needs_review",
            "transcript": iat.transcript,
            "transcript_sha256": hashlib.sha256(
                iat.transcript.encode("utf-8")
            ).hexdigest(),
            "provider_session_present": bool(iat.provider_sid),
            "segment_count": len(iat.segments),
            "normalized_similarity_to_tts_text": round(similarity, 6),
            "required_term_checks": term_checks,
            "human_review_required": True,
        },
        "gates": {
            "real_tts_audio_nonempty": audio_path.stat().st_size > 44,
            "wav_mono_16bit_16khz": (
                metadata["channels"] == 1
                and metadata["sample_width_bytes"] == 2
                and metadata["sample_rate_hz"] == 16000
            ),
            "real_asr_transcript_nonempty": bool(iat.transcript.strip()),
            "legal_terms_all_present": all(term_checks.values()),
            "normalized_similarity_at_least_0_80": similarity >= 0.80,
            "provider_sessions_returned": bool(tts.provider_sid and iat.provider_sid),
            "credential_values_absent": True,
            "learning_event_created": False,
            "formal_grading_eligible": False,
            "digital_human_connected": False,
        },
        "evidence_boundary": [
            "This proves one real iFlytek TTS call and one real iFlytek IAT call.",
            "The transcript is synthetic verification content, not classroom data.",
            "ASR output requires rule or teacher review before any learning evidence.",
            "Digital human remains postponed and not_connected.",
        ],
    }
    required_true = [
        "real_tts_audio_nonempty",
        "wav_mono_16bit_16khz",
        "real_asr_transcript_nonempty",
        "legal_terms_all_present",
        "normalized_similarity_at_least_0_80",
        "provider_sessions_returned",
        "credential_values_absent",
    ]
    if not all(audit["gates"][name] for name in required_true):
        audit["overall_status"] = "failed"
    else:
        audit["overall_status"] = "passed"

    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "\n".join(
            [
                "# 讯飞ASR/TTS真实接通验证",
                "",
                f"- 状态：`{audit['overall_status']}`",
                f"- 代码commit：`{source_commit}`",
                f"- 真实调用：TTS `{audit['real_network_calls']['tts']}` 次，IAT `{audit['real_network_calls']['iat']}` 次",
                f"- TTS音频：`{audit['tts']['audio_file']}`，{audit['tts']['audio_bytes']}字节，SHA-256 `{audit['tts']['audio_sha256']}`",
                f"- 音频：{metadata['sample_rate_hz']}Hz、{metadata['channels']}声道、{metadata['sample_width_bytes'] * 8}bit、{metadata['duration_seconds']}秒",
                f"- IAT转写：{iat.transcript}",
                f"- 归一化相似度：`{audit['asr']['normalized_similarity_to_tts_text']}`",
                f"- 法学词检查：`{json.dumps(term_checks, ensure_ascii=False)}`",
                "",
                "## 边界",
                "",
                "- 这是合成测试句的真实云端往返，不是课堂数据或学习效果。",
                "- ASR结果保持`needs_review`，不自动生成LearningEvent或正式成绩。",
                "- TTS必须保留AI合成标识；数字人继续后置并保持`not_connected`。",
                "- 公开产物不含APPID、APIKey、APISecret或签名URL。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "overall_status": audit["overall_status"],
                "audio_file": audit["tts"]["audio_file"],
                "audio_bytes": audit["tts"]["audio_bytes"],
                "audio_sha256": audit["tts"]["audio_sha256"],
                "transcript": audit["asr"]["transcript"],
                "similarity": audit["asr"]["normalized_similarity_to_tts_text"],
                "credential_values_published": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if audit["overall_status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
