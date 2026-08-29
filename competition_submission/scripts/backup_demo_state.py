"""Create a consistent, offline competition-demo snapshot without secrets.

The stack must be stopped. SQLite databases are copied through the backup API
so committed WAL pages are included. Only synthetic ``@example.com`` accounts
are accepted by default; this prevents accidental packaging of classroom PII.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import socket
import sqlite3
import subprocess
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME = REPO / "backend" / "runtime"
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


def backup_sqlite(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            result = dst.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"integrity_check failed for {target}: {result}")


def audit_demo_identities(database: Path) -> dict[str, object]:
    with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as connection:
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if not table_exists:
            return {"user_count": 0, "domains": {}}
        emails = [row[0] for row in connection.execute("SELECT email FROM users")]
    domains: dict[str, int] = {}
    for email in emails:
        domain = str(email).rsplit("@", 1)[-1].lower()
        domains[domain] = domains.get(domain, 0) + 1
    non_demo = [domain for domain in domains if domain != "example.com"]
    if non_demo:
        raise RuntimeError(
            "refusing to package non-demo identities; unexpected domains: "
            + ", ".join(sorted(non_demo))
        )
    return {"user_count": len(emails), "domains": domains}


def git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    args = parser.parse_args()

    active = listening_ports()
    if active:
        raise SystemExit(f"stop the local stack first; listening ports: {active}")

    output = args.output.resolve()
    runtime = args.runtime.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    main_db = runtime / "legalworld-local.db"
    adaptive_db = runtime / "adaptive.db"
    for required in (main_db, adaptive_db):
        if not required.exists():
            raise SystemExit(f"missing runtime database: {required}")

    identity_audit = audit_demo_identities(main_db)
    backup_sqlite(main_db, output / "runtime" / main_db.name)
    backup_sqlite(adaptive_db, output / "runtime" / adaptive_db.name)

    sandboxes = runtime / "sandboxes"
    if sandboxes.exists():
        shutil.copytree(sandboxes, output / "runtime" / "sandboxes")

    evidence_files = (
        REPO / "docs" / "COMPETITION_CASE3_E2E.json",
        REPO / "docs" / "TYPICAL_QUESTION_EVALUATION.json",
    )
    evidence_dir = output / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for source in evidence_files:
        shutil.copy2(source, evidence_dir / source.name)
    for name in (
        "case3-e2e-summary.json",
        "teacher-smoke-result.json",
        "semantic-audit.json",
    ):
        source = runtime / name
        if source.exists():
            shutil.copy2(source, evidence_dir / name)

    files = sorted(path for path in output.rglob("*") if path.is_file())
    manifest = {
        "schema": "competition-demo-backup-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "identity_audit": identity_audit,
        "contains_password_hashes": True,
        "access_policy": "offline_team_only_do_not_publish",
        "files": [
            {
                "path": path.relative_to(output).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in files
        ],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"output": str(output), **manifest}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
