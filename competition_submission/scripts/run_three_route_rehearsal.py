"""Run three browser-visible XH-202620 rehearsal routes on one local stack.

This orchestration is intentionally local-first and Docker-free.  It starts
``start.py``, waits for backend/adaptive/frontend health, runs the existing
Playwright-Core browser scripts sequentially, validates their machine output,
and writes one public, secret-free audit.  Student inputs and accounts are
synthetic; this proves reproducible software behaviour, not learning effect or
real-user approval.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import urlopen


REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend"
DEFAULT_JSON = REPO / "competition_submission" / "03-Demo" / "THREE_ROUTE_REHEARSAL_AUDIT.json"
DEFAULT_MARKDOWN = REPO / "competition_submission" / "03-Demo" / "THREE_ROUTE_REHEARSAL_AUDIT.md"
DEFAULT_ARTIFACT_ROOT = REPO / "output" / "playwright" / "competition-rehearsal"
SERVICE_URLS = {
    "backend": "http://127.0.0.1:8000/api/status",
    "adaptive": "http://127.0.0.1:8010/health",
    "frontend": "http://127.0.0.1:5173/",
}
SERVICE_PORTS = (8000, 8010, 5173)


class RehearsalError(RuntimeError):
    pass


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def repo_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return resolved.name


def sanitize_result_paths(value: Any, key: str = "") -> Any:
    """Convert local artifact paths in child smoke output to public relative paths."""

    if isinstance(value, dict):
        return {
            str(child_key): sanitize_result_paths(child_value, str(child_key))
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [sanitize_result_paths(item, key) for item in value]
    path_keys = {
        "artifact_dir",
        "screenshot",
        "analytics_screenshot",
        "student_subjective_screenshot",
        "subjective_queue_screenshot",
        "subjective_dialog_screenshot",
        "subjective_after_screenshot",
        "student_teacher_feedback_screenshot",
    }
    if key in path_keys and isinstance(value, str) and value:
        return repo_relative(Path(value))
    return value


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def wait_http(url: str, *, timeout: float = 120.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:  # noqa: S310 - fixed localhost URL
                if 200 <= response.status < 400:
                    return
                last_error = f"HTTP {response.status}"
        except (OSError, URLError) as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RehearsalError(f"service did not become ready: {url} ({last_error})")


def parse_last_json(stdout: str, stderr: str) -> dict[str, Any]:
    for stream in (stdout, stderr):
        for raw in reversed(stream.splitlines()):
            line = raw.strip()
            if not line.startswith("{"):
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
    raise RehearsalError("browser script did not emit a JSON result")


def zero_browser_errors(payload: dict[str, Any]) -> bool:
    keys = (
        "console_errors",
        "page_errors",
        "http_errors",
        "request_failures",
        "private_leaks",
        "privacy_leaks",
        "subjective_privacy_leaks",
    )
    return all(not payload.get(key) for key in keys)


def validate_cognitive(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    expected = {
        "knowledge_rows": 10,
        "orcdf_versions": 3,
        "heatmap_cells": 48,
        "path_nodes": 7,
        "knowledge_graph_nodes": 10,
        "knowledge_graph_edges": 10,
        "argument_template_nodes": 6,
        "model_routes": 4,
        "media_capabilities": 5,
        "media_proof_rows": 3,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            failures.append(f"{key} expected {value}, got {payload.get(key)!r}")
    if "未连接" not in str(payload.get("model_status", "")):
        failures.append("model_status does not preserve the fine-tune not-connected boundary")
    if "not_connected" not in str(payload.get("media_status", "")):
        failures.append("media_status does not preserve the provider not-connected boundary")
    if not zero_browser_errors(payload):
        failures.append("browser/private error arrays are not empty")
    return failures


def validate_rag(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if len(payload.get("questions") or []) != 3:
        failures.append("trusted RAG did not render exactly three typical questions")
    if payload.get("automated_gate") != "3/3":
        failures.append("automated question gate is not 3/3")
    if payload.get("expert_review") != "pending":
        failures.append("expert review boundary is not pending")
    rejected = payload.get("rejected_bad_citations")
    rejected_count = rejected if isinstance(rejected, int) else len(rejected or [])
    if rejected_count != 2:
        failures.append("bad citation rejection is not 2/2")
    if not zero_browser_errors(payload):
        failures.append("browser/private error arrays are not empty")
    return failures


def validate_teacher(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    required_true = (
        "teacher_role_entry_visible",
        "subjective_student_gate_visible",
        "revision_feedback_visible",
        "revision_prefilled_original",
        "revised_student_gate_visible",
        "student_approval_visible",
        "review_event_recorded",
        "subjective_review_event_recorded",
    )
    for key in required_true:
        if payload.get(key) is not True:
            failures.append(f"{key} is not true")
    expected = {
        "subjective_queue_before": 1,
        "subjective_queue_after_revision_request": 0,
        "subjective_queue_before_approval": 1,
        "subjective_queue_after": 0,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            failures.append(f"{key} expected {value}, got {payload.get(key)!r}")
    metrics = payload.get("metrics_after_subjective_approval") or []
    if len(metrics) < 3 or str(metrics[2]) != "3":
        failures.append("teacher approval did not increase the class event count to 3")
    if not zero_browser_errors(payload):
        failures.append("browser/privacy error arrays are not empty")
    return failures


def route_specs(artifact_root: Path, run_id: str, teacher_email: str) -> list[dict[str, Any]]:
    cognitive = artifact_root / "01-cognitive-path"
    rag = artifact_root / "02-trusted-rag"
    teacher = artifact_root / "03-teacher-hitl"
    return [
        {
            "route_id": "cognitive_path_and_adapters",
            "title": "认知诊断—ORCDF—七步路径—知识图—Model/Media Adapter",
            "script": FRONTEND / "scripts" / "smoke-cognitive-dashboard.mjs",
            "timeout": 300,
            "env": {"COGNITIVE_ARTIFACT_DIR": str(cognitive)},
            "validate": validate_cognitive,
            "video_segment": "第2—3段；第7段技术状态",
            "ppt_pages": "5—7、10",
            "scoring": "技术实现、技术先进、创意实用、完成度",
        },
        {
            "route_id": "trusted_rag_three_questions",
            "title": "三个典型问题—权威Evidence—错误引用拒绝",
            "script": FRONTEND / "scripts" / "smoke-trusted-rag.mjs",
            "timeout": 240,
            "env": {"RAG_ARTIFACT_DIR": str(rag)},
            "validate": validate_rag,
            "video_segment": "第4段",
            "ppt_pages": "4、11",
            "scoring": "内容质量、技术实现、可信安全",
        },
        {
            "route_id": "teacher_subjective_hitl",
            "title": "学生主观稿—教师退回—原文修订—批准—画像事件",
            "script": FRONTEND / "scripts" / "smoke-teacher-dashboard.mjs",
            "timeout": 720,
            "env": {
                "TEACHER_SMOKE_EMAIL": teacher_email,
                "TEACHER_STUDENT_EMAIL": f"student-{run_id}@example.com",
                "TEACHER_CLASS_NAME": f"刑法彩排班-{run_id[-6:]}",
                "TEACHER_RESULT_JSON": str(teacher / "result.json"),
                "TEACHER_SCREENSHOT": str(teacher / "01-overview.png"),
                "TEACHER_ANALYTICS_SCREENSHOT": str(teacher / "02-analytics.png"),
                "TEACHER_SUBJECTIVE_SCREENSHOT": str(teacher / "03-queue.png"),
                "TEACHER_SUBJECTIVE_AFTER_SCREENSHOT": str(teacher / "04-after.png"),
                "TEACHER_SUBJECTIVE_DIALOG_SCREENSHOT": str(teacher / "05-dialog.png"),
                "STUDENT_SUBJECTIVE_SCREENSHOT": str(teacher / "06-student-draft.png"),
                "STUDENT_TEACHER_FEEDBACK_SCREENSHOT": str(teacher / "07-student-feedback.png"),
            },
            "validate": validate_teacher,
            "video_segment": "第5段",
            "ppt_pages": "8",
            "scoring": "教学创新、Human-in-the-loop、隐私安全",
        },
    ]


def run_route(spec: dict[str, Any], base_env: dict[str, str]) -> dict[str, Any]:
    env = {**base_env, **spec["env"]}
    started = time.monotonic()
    result = subprocess.run(
        ["node", str(spec["script"])],
        cwd=FRONTEND,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=spec["timeout"],
        check=False,
    )
    duration = round(time.monotonic() - started, 3)
    payload = sanitize_result_paths(parse_last_json(result.stdout, result.stderr))
    failures = list(spec["validate"](payload))
    if result.returncode != 0:
        failures.append(f"browser script exit code {result.returncode}")
    return {
        "route_id": spec["route_id"],
        "title": spec["title"],
        "status": "passed" if not failures else "failed",
        "duration_seconds": duration,
        "script": repo_relative(spec["script"]),
        "video_segment": spec["video_segment"],
        "ppt_pages": spec["ppt_pages"],
        "scoring": spec["scoring"],
        "failures": failures,
        "result": payload,
    }


def stop_stack(process: subprocess.Popen[Any], log_handle: Any) -> None:
    if process.poll() is None:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    log_handle.close()


def markdown(audit: dict[str, Any]) -> str:
    rows = [
        "# XH-202620三案例浏览器彩排审计",
        "",
        f"- 源commit：`{audit['source_git_commit']}`",
        f"- 彩排结果：**{audit['routes_passed']}/{audit['route_count']}通过**",
        f"- 浏览器错误总数：**{audit['browser_error_total']}**",
        f"- 总耗时：{audit['duration_seconds']}秒",
        "- 数据身份：合成`example.com`演示账号与确定性学生输入",
        "",
        "| 演示案例 | 结果 | 视频 | PPT | 评分映射 |",
        "|---|---|---|---|---|",
    ]
    for route in audit["routes"]:
        rows.append(
            f"| {route['title']} | {route['status']} / {route['duration_seconds']}s | "
            f"{route['video_segment']} | {route['ppt_pages']} | {route['scoring']} |"
        )
    rows.extend(
        [
            "",
            "## 证据边界",
            "",
            "- 本审计证明三条真实浏览器UI路线可在同一套本地SQLite + adaptive + Vite服务上顺序执行。",
            "- 它不证明真实目标用户认可、学习增益、路径因果最优、专家法律正确性或正式成绩效度。",
            "- ORCDF仍是MOOCCubeX民法/宪法shadow实验；微调和云媒体Provider仍保持`not_connected`。",
            "",
        ]
    )
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-config", type=Path)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    args = parser.parse_args()

    occupied = [port for port in SERVICE_PORTS if port_open(port)]
    if occupied:
        raise RehearsalError(
            f"ports already in use: {occupied}; stop the existing local stack before rehearsal"
        )
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_root = args.artifact_root.resolve() / run_id
    artifact_root.mkdir(parents=True, exist_ok=True)
    stack_log = artifact_root / "stack.log"
    teacher_email = f"teacher-{run_id.lower()}@example.com"
    env = dict(os.environ)
    env["SIMLAW_TEACHER_EMAILS"] = teacher_email
    env["PYTHONUNBUFFERED"] = "1"
    command = [sys.executable, str(REPO / "start.py")]
    if args.model_config:
        command.extend(["--model-config", str(args.model_config.resolve())])
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    log_handle = stack_log.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=REPO,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    started = time.monotonic()
    routes: list[dict[str, Any]] = []
    try:
        for url in SERVICE_URLS.values():
            wait_http(url)
        for spec in route_specs(artifact_root, run_id, teacher_email):
            routes.append(run_route(spec, env))
            if routes[-1]["status"] != "passed":
                break
    finally:
        stop_stack(process, log_handle)

    lingering_ports = [port for port in SERVICE_PORTS if port_open(port)]
    browser_error_total = 0
    for route in routes:
        result = route.get("result") or {}
        for key in ("console_errors", "page_errors", "http_errors", "request_failures"):
            browser_error_total += len(result.get(key) or [])
    all_passed = (
        len(routes) == 3
        and all(route["status"] == "passed" for route in routes)
        and browser_error_total == 0
        and not lingering_ports
    )
    audit = {
        "schema": "xh-202620-three-route-browser-rehearsal-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_git_commit": git_output("rev-parse", "HEAD"),
        "route_count": 3,
        "routes_executed": len(routes),
        "routes_passed": sum(route["status"] == "passed" for route in routes),
        "all_routes_passed": all_passed,
        "browser_error_total": browser_error_total,
        "duration_seconds": round(time.monotonic() - started, 3),
        "service_urls": SERVICE_URLS,
        "services_stopped_after_run": not lingering_ports,
        "lingering_ports": lingering_ports,
        "artifact_root": repo_relative(artifact_root),
        "stack_log": repo_relative(stack_log),
        "model_config_supplied": bool(args.model_config),
        "routes": routes,
        "boundaries": [
            "synthetic example.com accounts and deterministic student inputs",
            "software rehearsal only; not target-user approval or learning-effect evidence",
            "ORCDF remains an uncalibrated civil/constitutional shadow experiment",
            "fine-tuned and cloud media providers remain truthfully not_connected",
        ],
    }
    json_path = args.json.resolve()
    markdown_path = args.markdown.resolve()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown(audit), encoding="utf-8")
    print(
        json.dumps(
            {
                "all_routes_passed": all_passed,
                "routes_passed": audit["routes_passed"],
                "browser_error_total": browser_error_total,
                "duration_seconds": audit["duration_seconds"],
                "services_stopped_after_run": audit["services_stopped_after_run"],
                "json": str(json_path),
                "markdown": str(markdown_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
