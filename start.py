"""Start the complete LegalWorld stack locally (no Docker required).

Example:
    uv run --isolated --with-requirements requirements.lock.txt -- \
      python start.py --model-config E:\\path\\to\\model-groups.env.example

The optional model file may contain repeated ``api_key/baseurl/model`` groups.
The OpenCode group is mapped to the preferred OPENAI_* endpoint; the official
DeepSeek group is mapped to the transient-error fallback. Keys are never
printed. With explicit user authorization, ``sync_local_env_from_external``
can copy only the required values into the Git-ignored repository ``.env``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
ADAPTIVE_DIR = ROOT / "adaptive_service"
RUNTIME_DIR = BACKEND_DIR / "runtime"
ROOT_ENV_PATH = ROOT / ".env"
DEFAULT_BACKEND_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = "8000"
DEFAULT_ADAPTIVE_PORT = "8010"
DEFAULT_FRONTEND_PORT = "5173"

processes: list[subprocess.Popen[Any]] = []


def read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip().strip('"').strip("'")
    return values


def read_repeated_model_groups(path: Path) -> list[dict[str, str]]:
    """Read repeated generic api_key/baseurl/model groups in file order."""

    if not path.is_file():
        raise FileNotFoundError(path)
    groups: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = key.strip().lower()
        normalized_value = value.strip().strip('"').strip("'")
        if normalized_key == "api_key" and current:
            groups.append(current)
            current = {}
        current[normalized_key] = normalized_value
    if current:
        groups.append(current)
    return groups


def read_named_config_sections(path: Path) -> dict[str, dict[str, list[str]]]:
    """Read sectioned config while preserving repeated keys such as model=."""

    if not path.is_file():
        raise FileNotFoundError(path)
    sections: dict[str, dict[str, list[str]]] = {"root": {}}
    section = "root"
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith(":") and "=" not in line:
            section = line[:-1].strip().lower() or "root"
            sections.setdefault(section, {})
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lower()
        value = value.strip().strip('"').strip("'")
        sections.setdefault(section, {}).setdefault(key, []).append(value)
    return sections


def apply_grouped_model_config(env: dict[str, str], path: Path) -> dict[str, str]:
    groups = read_repeated_model_groups(path)
    primary = next(
        (group for group in groups if "opencode.ai" in group.get("baseurl", "")),
        None,
    )
    fallback = next(
        (
            group
            for group in groups
            if urlsplit(group.get("baseurl", "")).netloc == "api.deepseek.com"
        ),
        None,
    )
    def set_if_empty(key: str, value: str) -> None:
        if not str(env.get(key) or "").strip():
            env[key] = value

    if primary:
        set_if_empty("OPENAI_API_KEY", primary.get("api_key", ""))
        set_if_empty("OPENAI_API_BASE_URL", primary.get("baseurl", ""))
        set_if_empty("OPENAI_MODEL_NAME", primary.get("model", ""))
    if fallback:
        set_if_empty("SIMLAW_FALLBACK_MODEL_API_KEY", fallback.get("api_key", ""))
        set_if_empty(
            "SIMLAW_FALLBACK_MODEL_API_BASE_URL", fallback.get("baseurl", "")
        )
        set_if_empty("SIMLAW_FALLBACK_MODEL_NAME", fallback.get("model", ""))
        env.setdefault("SIMLAW_FALLBACK_MODEL_TIMEOUT_SECONDS", "180")
        env.setdefault("SIMLAW_FALLBACK_CIRCUIT_SECONDS", "900")
    return env


def apply_iflytek_config(env: dict[str, str], path: Path) -> dict[str, str]:
    """Map the user's generic iFlytek section without printing or copying keys."""

    values = read_env_file(path)
    mapping = {
        "XFYUN_APP_ID": "APPID",
        "XFYUN_API_KEY": "APIKey",
        "XFYUN_API_SECRET": "APISecret",
    }
    for target, source in mapping.items():
        if not str(env.get(target) or "").strip() and str(values.get(source) or "").strip():
            env[target] = values[source]
    return env


def apply_hybrid_rag_config(env: dict[str, str], path: Path) -> dict[str, str]:
    """Map SiliconFlow embedding and reranker models into separate settings."""

    section = read_named_config_sections(path).get("siliconflow") or {}
    api_keys = [value for value in section.get("api_key", []) if value]
    bases = [value.rstrip() for value in section.get("baseurl", []) if value]
    models = [value for value in section.get("model", []) if value]
    if not api_keys or not bases:
        return env
    embedding_model = next((value for value in models if "embedding" in value.lower()), "")
    reranker_model = next((value for value in models if "reranker" in value.lower()), "")
    api_root = re.sub(r"/(?:embeddings|rerank)$", "", bases[0].rstrip("/"), flags=re.IGNORECASE)

    def set_if_empty(name: str, value: str) -> None:
        if value and not str(env.get(name) or "").strip():
            env[name] = value

    set_if_empty("LAW_EMBEDDING_API_KEY", api_keys[0])
    set_if_empty("LAW_EMBEDDING_API_BASE_URL", f"{api_root}/embeddings")
    set_if_empty("LAW_EMBEDDING_MODEL", embedding_model)
    set_if_empty("LAW_RERANKER_API_KEY", api_keys[0])
    set_if_empty("LAW_RERANKER_API_BASE_URL", f"{api_root}/rerank")
    set_if_empty("LAW_RERANKER_MODEL", reranker_model)
    return env


LOCAL_ENV_ALLOWLIST = (
    "OPENAI_API_KEY",
    "OPENAI_API_BASE_URL",
    "OPENAI_MODEL_NAME",
    "SIMLAW_FALLBACK_MODEL_API_KEY",
    "SIMLAW_FALLBACK_MODEL_API_BASE_URL",
    "SIMLAW_FALLBACK_MODEL_NAME",
    "SIMLAW_FALLBACK_MODEL_TIMEOUT_SECONDS",
    "SIMLAW_FALLBACK_CIRCUIT_SECONDS",
    "XFYUN_APP_ID",
    "XFYUN_API_KEY",
    "XFYUN_API_SECRET",
    "XFYUN_TTS_VOICE",
    "XFYUN_TTS_FALLBACK_VOICE",
    "LAW_EMBEDDING_API_KEY",
    "LAW_EMBEDDING_API_BASE_URL",
    "LAW_EMBEDDING_MODEL",
    "LAW_RERANKER_API_KEY",
    "LAW_RERANKER_API_BASE_URL",
    "LAW_RERANKER_MODEL",
    "JWT_SECRET",
)


def sync_local_env_from_external(
    source: Path,
    *,
    target: Path = ROOT_ENV_PATH,
) -> tuple[str, ...]:
    """Copy an allowlisted runtime config into a Git-ignored local .env.

    This is intentionally opt-in because it writes secrets. Values are never
    returned or printed; tests and callers receive only the written key names.
    """

    resolved = Path(source).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    env = read_env_file(target)
    apply_grouped_model_config(env, resolved)
    apply_iflytek_config(env, resolved)
    apply_hybrid_rag_config(env, resolved)
    env.setdefault("XFYUN_TTS_VOICE", "x4_yezi")
    env.setdefault("XFYUN_TTS_FALLBACK_VOICE", "xiaoyan")
    env.setdefault("JWT_SECRET", secrets.token_urlsafe(48))
    required = (
        "OPENAI_API_KEY",
        "OPENAI_API_BASE_URL",
        "OPENAI_MODEL_NAME",
        "XFYUN_APP_ID",
        "XFYUN_API_KEY",
        "XFYUN_API_SECRET",
    )
    missing = [name for name in required if not str(env.get(name) or "").strip()]
    if missing:
        raise RuntimeError(f"External config is missing required runtime groups: {', '.join(missing)}")
    rows = [
        "# Local LegalWorld runtime secrets. Git ignored; do not share or commit.",
        "# Generated only after explicit user authorization.",
    ]
    written = []
    for name in LOCAL_ENV_ALLOWLIST:
        value = str(env.get(name) or "").strip()
        if not value:
            continue
        if any(char in value for char in ("\r", "\n", "\x00")):
            raise RuntimeError(f"Unsafe newline in local environment value: {name}")
        rows.append(f"{name}={json.dumps(value, ensure_ascii=False)}")
        written.append(name)
    destination = Path(target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.tmp")
    temporary.write_text("\n".join(rows) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return tuple(written)


def build_backend_env(model_config: Path | None = None) -> dict[str, str]:
    # Explicit process environment wins over repository .env and grouped file.
    env = {**read_env_file(ROOT_ENV_PATH), **os.environ}
    if model_config is not None:
        apply_grouped_model_config(env, model_config)
        apply_iflytek_config(env, model_config)
        apply_hybrid_rag_config(env, model_config)

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    database_path = (RUNTIME_DIR / "legalworld-local.db").resolve().as_posix()
    hybrid_manifest = ROOT / ".codex-artifacts" / "hybrid-rag-index-v1" / "index_set_manifest.json"
    env.setdefault("SIMLAW_HYBRID_RAG_ENABLED", "1" if hybrid_manifest.is_file() else "0")
    env.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{database_path}")
    env.setdefault("JWT_SECRET", secrets.token_urlsafe(48))
    env.setdefault("SIMLAW_PLAYER_LAWYER_MODE", "defendant")
    env.setdefault("SIMLAW_SANDBOX_DATA_DIR", str((RUNTIME_DIR / "sandboxes").resolve()))
    env.setdefault("SIMLAW_SANDBOX_SEED_DIR", str((BACKEND_DIR / "sandbox_seed_data").resolve()))
    env.setdefault("SIMLAW_ENABLE_DEBUG_UI", "false")
    env.setdefault("SIMLAW_ENABLE_LEGACY_SIMULATION_API", "false")
    env.setdefault("SIMLAW_ALLOW_WS_QUERY_TOKEN", "false")
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _safe_endpoint_label(url: str) -> str:
    parsed = urlsplit(str(url or ""))
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else "not configured"


def _spawn(command: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.Popen[Any]:
    process = subprocess.Popen(command, cwd=str(cwd), env=env)
    processes.append(process)
    return process


def cleanup(*_: object) -> None:
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 5
    for process in reversed(processes):
        if process.poll() is None:
            try:
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                process.kill()


def _ensure_frontend_dependencies() -> str:
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if not npm:
        raise RuntimeError("npm is not available; install Node.js or use the bundled runtime")
    vite = FRONTEND_DIR / "node_modules" / ".bin" / (
        "vite.cmd" if sys.platform == "win32" else "vite"
    )
    if not vite.exists():
        print("Installing frontend dependencies once (npm ci)...")
        subprocess.run([npm, "ci"], cwd=str(FRONTEND_DIR), check=True)
    return npm


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-config", type=Path)
    parser.add_argument(
        "--sync-env-from",
        type=Path,
        help="copy allowlisted model/speech values into the Git-ignored .env before starting",
    )
    parser.add_argument("--no-adaptive", action="store_true")
    parser.add_argument("--no-frontend", action="store_true")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, lambda *_: cleanup())
    signal.signal(signal.SIGTERM, lambda *_: cleanup())
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, lambda *_: cleanup())

    if args.sync_env_from is not None:
        written = sync_local_env_from_external(args.sync_env_from)
        print(f"Synced {len(written)} allowlisted runtime settings into Git-ignored .env")
    env = build_backend_env(args.model_config.resolve() if args.model_config else None)
    backend_host = env.get("BACKEND_HOST", DEFAULT_BACKEND_HOST)
    backend_port = env.get("BACKEND_PORT", DEFAULT_BACKEND_PORT)
    adaptive_port = env.get("ADAPTIVE_PORT", DEFAULT_ADAPTIVE_PORT)
    frontend_port = env.get("FRONTEND_PORT", DEFAULT_FRONTEND_PORT)
    npm = _ensure_frontend_dependencies() if not args.no_frontend else ""

    if not args.no_adaptive:
        adaptive_env = dict(env)
        adaptive_env["PYTHONPATH"] = str((ADAPTIVE_DIR / "src").resolve())
        adaptive_env.setdefault(
            "SIMLAW_ADAPTIVE_DB_PATH", str((RUNTIME_DIR / "adaptive.db").resolve())
        )
        adaptive_env.setdefault(
            "SIMLAW_ADAPTIVE_DATA_DIR", str((ADAPTIVE_DIR / "data").resolve())
        )
        shared_key = adaptive_env.setdefault(
            "SIMLAW_ADAPTIVE_API_KEY", secrets.token_urlsafe(32)
        )
        env["SIMLAW_ADAPTIVE_API_KEY"] = shared_key
        env["SIMLAW_ADAPTIVE_API_BASE_URL"] = f"http://127.0.0.1:{adaptive_port}"
        _spawn(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "edubrain_adaptive.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                adaptive_port,
            ],
            cwd=ADAPTIVE_DIR,
            env=adaptive_env,
        )

    _spawn(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "ws_server:app",
            "--host",
            backend_host,
            "--port",
            backend_port,
        ],
        cwd=BACKEND_DIR,
        env=env,
    )

    if not args.no_frontend:
        frontend_env = dict(env)
        frontend_env["BACKEND_URL"] = f"http://{backend_host}:{backend_port}"
        _spawn(
            [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", frontend_port],
            cwd=FRONTEND_DIR,
            env=frontend_env,
        )

    print("=" * 64)
    print("LegalWorld local stack started")
    print(f"Frontend:  http://127.0.0.1:{frontend_port}" if not args.no_frontend else "Frontend:  disabled")
    print(f"Backend:   http://{backend_host}:{backend_port}")
    print(
        f"Adaptive:  http://127.0.0.1:{adaptive_port}"
        if not args.no_adaptive
        else "Adaptive:  disabled"
    )
    print(
        "Primary:   "
        f"{env.get('OPENAI_MODEL_NAME') or 'not configured'} @ "
        f"{_safe_endpoint_label(env.get('OPENAI_API_BASE_URL', ''))}"
    )
    print(
        "Fallback:  "
        f"{env.get('SIMLAW_FALLBACK_MODEL_NAME') or 'not configured'} @ "
        f"{_safe_endpoint_label(env.get('SIMLAW_FALLBACK_MODEL_API_BASE_URL', ''))}"
    )
    speech_configured = all(
        str(env.get(name) or "").strip()
        for name in ("XFYUN_APP_ID", "XFYUN_API_KEY", "XFYUN_API_SECRET")
    )
    print(
        "Speech:    iFlytek ASR/TTS credentials configured"
        if speech_configured
        else "Speech:    iFlytek ASR/TTS not configured"
    )
    print("Local SQLite/runtime data:", RUNTIME_DIR)
    print("Press Ctrl+C to stop. No API keys are printed or written.")
    print("=" * 64)

    try:
        while True:
            for process in processes:
                code = process.poll()
                if code is not None:
                    print(f"A local service exited with code {code}; stopping the stack.")
                    cleanup()
                    return int(code)
            time.sleep(0.5)
    except KeyboardInterrupt:
        cleanup()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
