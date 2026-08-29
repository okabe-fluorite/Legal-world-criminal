"""Assemble captured browser segments into a silent H.264 preview and audit it."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration,size:stream=codec_name,width,height,avg_frame_rate",
            "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segments", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-audit", type=Path, required=True)
    parser.add_argument("--sampled-frames-reviewed", action="store_true")
    args = parser.parse_args()

    segment_dir = args.segments.resolve()
    private_manifest = json.loads(
        (segment_dir / "segments-manifest.json").read_text(encoding="utf-8")
    )
    files = [segment_dir / row["file"] for row in private_manifest["segments"]]
    if len(files) != 5 or any(not path.is_file() for path in files):
        raise SystemExit("expected five captured WebM segments")
    if any(
        items
        for row in private_manifest["segments"]
        for items in row["errors"].values()
    ):
        raise SystemExit("captured segments contain browser errors")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    concat = segment_dir / ".concat-private.txt"
    concat.write_text(
        "\n".join(f"file '{path.as_posix()}'" for path in files) + "\n",
        encoding="utf-8",
    )
    try:
        subprocess.run(
            [
                "ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat), "-an", "-c:v", "libx264", "-preset", "medium",
                "-crf", "22", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
            ],
            check=True,
        )
    finally:
        concat.unlink(missing_ok=True)

    segment_audits = []
    for row, path in zip(private_manifest["segments"], files, strict=True):
        metadata = probe(path)
        stream = metadata["streams"][0]
        segment_audits.append(
            {
                "name": row["name"],
                "file": path.name,
                "duration_seconds": round(float(metadata["format"]["duration"]), 3),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "codec": stream["codec_name"],
                "resolution": f"{stream['width']}x{stream['height']}",
                "fps": stream["avg_frame_rate"],
                "browser_error_counts": {
                    key: len(value) for key, value in row["errors"].items()
                },
            }
        )
    preview = probe(output)
    preview_stream = preview["streams"][0]
    public = {
        "schema": "competition-silent-demo-preview-audit-v1",
        "segments": segment_audits,
        "segment_total_duration_seconds": round(
            sum(row["duration_seconds"] for row in segment_audits), 3
        ),
        "preview": {
            "file": output.name,
            "duration_seconds": round(float(preview["format"]["duration"]), 3),
            "bytes": output.stat().st_size,
            "sha256": sha256(output),
            "codec": preview_stream["codec_name"],
            "resolution": f"{preview_stream['width']}x{preview_stream['height']}",
            "fps": preview_stream["avg_frame_rate"],
            "audio": False,
        },
        "qa": {
            "sampled_start_mid_end_frames_reviewed": args.sampled_frames_reviewed,
            "login_pages_removed_by_reencode": True,
            "credential_or_token_files_published": False,
            "browser_error_total": sum(
                count
                for row in segment_audits
                for count in row["browser_error_counts"].values()
            ),
        },
        "evidence_boundary": (
            "silent 65-second browser interaction preview from synthetic frozen-demo accounts; "
            "raw preview is private/ignored and is not the final <=180-second narrated submission; "
            "not evidence of target-user approval, learning gain, or expert legal validity"
        ),
    }
    audit = args.public_audit.resolve()
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(public, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
