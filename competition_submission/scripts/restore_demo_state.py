"""Verify and restore a competition-demo backup into backend/runtime.

The stack must be stopped. Existing runtime files are not changed unless the
operator explicitly passes ``--force``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME = (REPO / "backend" / "runtime").resolve()
PORTS = (5173, 8000, 8010)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def listening_ports() -> list[int]:
    active: list[int] = []
    for port in PORTS:
        with socket.socket() as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                active.append(port)
    return active


def verify_database(path: Path) -> None:
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"integrity_check failed for {path}: {result}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--target-runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    active = listening_ports()
    if active:
        raise SystemExit(f"stop the local stack first; listening ports: {active}")

    backup = args.backup.resolve()
    runtime = args.target_runtime.resolve()
    if runtime == Path(runtime.anchor) or len(runtime.parts) < 3:
        raise SystemExit(f"unsafe target runtime path: {runtime}")
    manifest_path = backup / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "competition-demo-backup-v1":
        raise SystemExit("unsupported or missing backup manifest schema")
    for item in manifest["files"]:
        source = backup / item["path"]
        if not source.is_file() or source.stat().st_size != item["bytes"] or sha256(source) != item["sha256"]:
            raise SystemExit(f"backup verification failed: {item['path']}")

    if runtime.exists() and not args.force:
        raise SystemExit(f"target runtime exists; re-run with --force after confirming: {runtime}")

    source_runtime = backup / "runtime"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:10]
    staging = runtime.parent / f".{runtime.name}.restore-staging-{token}"
    previous = runtime.parent / f".{runtime.name}.restore-previous-{token}"
    try:
        staging.mkdir()
        for name in ("legalworld-local.db", "adaptive.db"):
            source = source_runtime / name
            verify_database(source)
            target = staging / name
            shutil.copy2(source, target)
            verify_database(target)
        source_sandboxes = source_runtime / "sandboxes"
        if source_sandboxes.exists():
            shutil.copytree(source_sandboxes, staging / "sandboxes")
        source_evidence = backup / "evidence"
        for name in (
            "case3-e2e-summary.json",
            "teacher-smoke-result.json",
            "semantic-audit.json",
        ):
            source = source_evidence / name
            if source.exists():
                shutil.copy2(source, staging / name)

        if runtime.exists():
            os.replace(runtime, previous)
        try:
            os.replace(staging, runtime)
        except Exception:
            if previous.exists() and not runtime.exists():
                os.replace(previous, runtime)
            raise
        if previous.exists():
            shutil.rmtree(previous)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    print(
        json.dumps(
            {
                "restored_from": str(backup),
                "target": str(runtime),
                "git_commit": manifest.get("git_commit"),
                "databases": ["legalworld-local.db", "adaptive.db"],
                "sandboxes": (source_runtime / "sandboxes").exists(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
