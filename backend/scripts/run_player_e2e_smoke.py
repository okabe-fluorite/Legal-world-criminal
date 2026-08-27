"""Run one real player-mode case through REST + WebSocket without UI clicks.

This is an integration smoke runner, not a learning outcome evaluation. It
uses deterministic student test responses, never AI-drafted answers, and emits
only a secret-free summary. The server still performs its configured real
agent and teaching-model calls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import websockets


TEST_RESPONSES = {
    "LC": (
        "作为辩护人，我先核实委托关系、案件所处阶段和已采取的强制措施。"
        "当前仅根据已披露材料提出初步意见，不承诺结果；请完整说明吸毒次数、既往反应、"
        "首次碰撞后的行为以及侦查机关已经固定的证据。"
    ),
    "INV": (
        "侦查阶段申请依法会见并调取毒品检测、现场勘验、车辆轨迹、速度鉴定和伤亡鉴定。"
        "重点核实行为人对吸毒后幻觉的既往认识以及首次撞击后继续高速行驶的原因，"
        "并审查讯问、鉴定和证据保全程序；不以案件结果严重为由放弃程序性辩护。"
    ),
    "PR": (
        "审查起诉阶段应区分交通肇事过失与危害公共安全故意。依据《刑法》第十四条、"
        "第十五条，主观方面必须结合既往吸毒体验、短时多次吸毒、首次事故后的加速逃离、"
        "连续冲撞和车速等证据综合判断，不能只凭结果倒推故意。现有公开事实亦不支持虚构不起诉承诺。"
    ),
    "DS": (
        "辩护词\n\n"
        "审判长、审判员：\n"
        "受被告人委托，辩护人依据目前已经披露的案件材料提出如下辩护意见。\n\n"
        "一、应当分段审查首次碰撞与后续连续冲撞的主观方面。\n"
        "依据《中华人民共和国刑法》第十四条、第十五条，故意与过失的区分必须同时考察认识因素和意志因素。"
        "应结合被告人既往吸毒后的体验、短时间内多次吸毒、首次碰撞后加速离开、后续连续冲撞、车辆速度与道路环境，"
        "判断其对危害公共安全结果究竟持希望、放任还是轻信能够避免的态度；不能仅凭四人死亡的严重结果倒推故意。\n\n"
        "二、请对关键证据进行实质审查。\n"
        "毒品检测的取样、保管和检验链条，车辆轨迹与速度鉴定的方法，现场勘验、监控、证人证言及被告人供述之间是否"
        "相互印证，均应在庭审中逐项核验。对首次事故后的行为目的及连续冲撞的时空关系，亦应排除合理怀疑。\n\n"
        "三、罪名与死刑适用应当分别论证。\n"
        "如全案证据足以证明放任危害公共安全结果，法院可依法审查《刑法》第一百一十五条第一款；如只能证明违反交通"
        "运输管理法规的过失，则应依法评价第一百三十三条。即使认定前罪，仍须依据第四十八条独立审查死刑立即执行所需"
        "的事实、情节和程序。辩护人不否认死亡和财产损失，也不把违法自陷吸毒状态当然作为从宽理由。\n\n"
        "综上，请法院坚持证据裁判和罪责刑相适应原则，对主观要件、罪名界分及刑罚适用作出充分说理的判决。\n\n"
        "辩护人：E2E测试辩护人\n"
        "日期：以提交记录为准\n"
        "【起草结束】"
    ),
    "CR": (
        "庭审质证围绕证据真实性、合法性、关联性展开：请公诉方说明毒品检测链条、车速与轨迹鉴定方法、"
        "连续碰撞的时空关系及供述补强证据。罪名判断应依据《刑法》第十四条、第十五条、"
        "第一百一十五条第一款和第一百三十三条区分故意与过失，严禁以危害结果单独替代主观要件证明。"
    ),
    "CRA": (
        "上诉审应重点复核主观故意认定是否达到证据确实充分、交通肇事罪与以危险方法危害公共安全罪的"
        "界分是否逐项回应，以及死刑事实和程序审查是否独立完成。若原判论证只以严重结果倒推放任心态，"
        "应依法纠正；如全案证据能够相互印证，也应在裁判理由中明确排除合理怀疑的过程。"
    ),
}


def _request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = requests.request(method, url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    return body if isinstance(body, dict) else {"data": body}


def _stage_response(stage: str, prompt: str) -> str:
    normalized = str(stage or "").upper()
    base = TEST_RESPONSES.get(
        normalized,
        "请以已披露案件事实和现行有效法源为依据继续；对未披露事实明确保留，不虚构证据、程序或裁判结果。",
    )
    prompt_hint = str(prompt or "").strip().replace("\n", " ")[:120]
    return f"{base}\n\n针对本轮提示（{prompt_hint}），以上为学生独立测试答复。"


async def run(args: argparse.Namespace) -> dict[str, Any]:
    base = args.base_url.rstrip("/")
    parsed = urlparse(base)
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{parsed.netloc}/ws"
    email = args.email or f"e2e-{uuid.uuid4().hex[:12]}@example.com"
    password = args.password or f"E2E-{uuid.uuid4().hex}-Strong"

    auth = await asyncio.to_thread(
        _request,
        "POST",
        f"{base}/api/auth/register",
        payload={"email": email, "password": password},
    )
    token = str(auth["access_token"])
    user_id = str((auth.get("user") or {}).get("id") or "")
    await asyncio.to_thread(_request, "POST", f"{base}/api/sandbox/ensure", token=token)
    cases = await asyncio.to_thread(_request, "GET", f"{base}/api/sandbox/cases", token=token)
    available = {str(row.get("case_id")) for row in cases.get("cases") or []}
    if args.case_id not in available:
        raise RuntimeError(f"case not available: {args.case_id}; available={sorted(available)}")

    events: Counter[str] = Counter()
    stages_seen: list[str] = []
    state_changes: list[str] = []
    runtime_issues: list[dict[str, Any]] = []
    submitted: set[str] = set()
    started_at = time.monotonic()
    deadline = started_at + args.timeout_seconds
    closed = False

    async with websockets.connect(
        ws_url,
        subprotocols=["simlaw-auth", token],
        open_timeout=15,
        close_timeout=5,
        max_size=8 * 1024 * 1024,
    ) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "type": "client_ready",
                    "mode": "player_v2",
                    "capabilities": ["dialogue_turn_gate"],
                }
            )
        )
        await asyncio.to_thread(
            _request,
            "POST",
            f"{base}/api/sandbox/start",
            token=token,
            payload={"case_id": args.case_id},
        )

        while time.monotonic() < deadline and not closed:
            try:
                raw = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                message = json.loads(raw)
                kind = str(message.get("type") or message.get("event") or "unknown")
                events[kind] += 1
                if kind == "dialogue_gate_waiting":
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "dialogue_continue",
                                "gate_id": message.get("gate_id"),
                            }
                        )
                    )
                elif kind == "case_state_change":
                    state = str(message.get("to_state") or message.get("state") or "")
                    if state and (not state_changes or state_changes[-1] != state):
                        state_changes.append(state)
                    closed = state in {"已结案", "closed", "终审"}
                elif kind == "scenario_start":
                    stage = str(message.get("scenario_type") or message.get("stage") or "")
                    if stage and stage not in stages_seen:
                        stages_seen.append(stage)
                elif kind == "case_runtime_issue":
                    runtime_issues.append(
                        {
                            key: message.get(key)
                            for key in ("stage_label", "code", "message", "retryable", "blocking")
                        }
                    )
                    break
            except asyncio.TimeoutError:
                pass

            if runtime_issues:
                break

            runtime = await asyncio.to_thread(
                _request,
                "GET",
                f"{base}/api/sandbox/player-lawyer/runtime?case_id={args.case_id}",
                token=token,
            )
            for pending in runtime.get("pending") or []:
                request_id = str(pending.get("request_id") or "")
                if not request_id or request_id in submitted:
                    continue
                stage = str(pending.get("stage") or "").upper()
                answer = _stage_response(stage, str(pending.get("prompt") or ""))
                await asyncio.to_thread(
                    _request,
                    "POST",
                    f"{base}/api/sandbox/player-lawyer/respond",
                    token=token,
                    payload={
                        "request_id": request_id,
                        "message": answer,
                        "original_message": answer,
                        "assist_mode": "none",
                        "used_ai_polish": False,
                        "hint_ids": [],
                        "skill_card_ids": [],
                    },
                    timeout=60,
                )
                submitted.add(request_id)
                if stage and stage not in stages_seen:
                    stages_seen.append(stage)

            picker = await asyncio.to_thread(
                _request, "GET", f"{base}/api/sandbox/cases", token=token
            )
            case_row = next(
                (
                    row
                    for row in picker.get("cases") or []
                    if str(row.get("case_id")) == args.case_id
                ),
                {},
            )
            closed = closed or str(case_row.get("status") or "") == "closed"

    elapsed = round(time.monotonic() - started_at, 3)
    timed_out = not closed and time.monotonic() >= deadline
    result = {
        "schema_version": "simlaw-real-e2e-smoke-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_host": parsed.netloc,
        "case_id": args.case_id,
        "user_id": user_id,
        "closed": closed,
        "timed_out": timed_out,
        "elapsed_seconds": elapsed,
        "submitted_response_count": len(submitted),
        "stages_seen": stages_seen,
        "state_changes": state_changes,
        "event_counts": dict(events),
        "runtime_issues": runtime_issues,
        "evidence_boundary": (
            "real configured model/runtime execution; deterministic synthetic student inputs; "
            "not evidence of learning efficacy or expert grading validity"
        ),
    }
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--case-id", default="case_1")
    parser.add_argument("--email")
    parser.add_argument("--password")
    parser.add_argument("--timeout-seconds", type=int, default=2400)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args))
    except Exception as exc:
        print(json.dumps({"status": "error", "error": f"{type(exc).__name__}: {exc}"}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    if result["timed_out"] or result["runtime_issues"] or not result["closed"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
