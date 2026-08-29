"""Build public INV/PR audit snapshots from the private frozen case3 runtime."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_one(runtime: Path, name: str) -> tuple[Path, dict]:
    matches = list(runtime.rglob(name))
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one {name}, found {len(matches)}")
    path = matches[0]
    return path, json.loads(path.read_text(encoding="utf-8"))


def excerpt(value: str, limit: int) -> str:
    compact = " ".join(str(value or "").split())
    return compact if len(compact) <= limit else compact[:limit].rstrip() + "…"


def percent(value: object) -> str:
    return f"{float(value or 0) * 100:.0f}%"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--html", type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime.resolve()

    inv_event_path, inv = load_one(runtime, "INV_learning_event.json")
    pr_event_path, pr = load_one(runtime, "PR_learning_event.json")
    pr_result_path, pr_result = load_one(runtime, "PR_result.json")
    decision_path, decision = load_one(runtime, "prosecution_decision.json")
    inv_result_path, inv_result = load_one(runtime, "INV_result.json")
    e2e_path = runtime / "case3-e2e-summary.json"
    e2e = json.loads(e2e_path.read_text(encoding="utf-8"))

    if inv.get("stage") != "INV" or pr.get("stage") != "PR":
        raise SystemExit("learning-event stages are not INV/PR")
    if pr_result.get("scenario_type") != "PR" or decision.get("stage") != "PR":
        raise SystemExit("PR result/decision stage mismatch")

    pr_lawyer = next(
        row["content"] for row in pr_result["dialog_history"] if row.get("role") == "lawyer"
    ).split("\n\n针对本轮提示", 1)[0]
    prosecutor_rows = [
        row["content"] for row in pr_result["dialog_history"] if row.get("role") == "prosecutor"
    ]
    inv_scores = inv.get("capability_scores") or {}
    pr_scores = pr.get("capability_scores") or {}

    public = {
        "schema": "case3-inv-pr-audit-snapshot-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_id": "case_3",
        "case_title": "张那木拉特殊防卫案",
        "source_sha256": {
            "inv_learning_event": sha256(inv_event_path),
            "pr_learning_event": sha256(pr_event_path),
            "pr_result": sha256(pr_result_path),
            "prosecution_decision": sha256(decision_path),
            "case3_e2e_summary": sha256(e2e_path),
        },
        "excluded_source_warning": {
            "file": "INV_result.json",
            "sha256": sha256(inv_result_path),
            "reason": (
                "filename implies INV but embedded scenario_type is "
                f"{inv_result.get('scenario_type')!r}; excluded from INV assertions"
            ),
        },
        "inv": {
            "stage": "INV",
            "knowledge_status": inv["knowledge_verdicts"][0]["status"],
            "knowledge_reason": inv["knowledge_verdicts"][0]["reason"],
            "capability_scores": {
                key: inv_scores[key]["score"]
                for key in ("fact_identification", "procedural_compliance", "rule_retrieval")
            },
            "evidence_quote": inv_scores["fact_identification"]["evidence_quote"],
            "error_tags": inv.get("error_tags") or [],
            "knowledge_gaps": inv.get("knowledge_gaps") or [],
        },
        "pr": {
            "stage": "PR",
            "knowledge_status": pr["knowledge_verdicts"][0]["status"],
            "lawyer_argument": pr_lawyer,
            "prosecutor_response": prosecutor_rows[-1],
            "valid_citation": (pr.get("law_citations") or [])[0],
            "capability_scores": {
                key: {
                    "score": pr_scores[key]["score"],
                    "source": pr_scores[key].get("source"),
                }
                for key in ("rule_retrieval", "subsumption", "claim_construction")
            },
            "decision": {
                "prosecute": decision["prosecute"],
                "reason_excerpt": excerpt(decision["reason"], 260),
                "full_reason_sha256": hashlib.sha256(
                    decision["reason"].encode("utf-8")
                ).hexdigest(),
            },
        },
        "e2e": {
            "elapsed_seconds": e2e["elapsed_seconds"],
            "fixed_response_count": e2e["submitted_response_count"],
            "stages_seen": e2e["stages_seen"],
            "closed": e2e["closed"],
            "agent_despawn_count": e2e["post_close_agent_despawns"],
            "runtime_issue_count": len(e2e.get("runtime_issues") or []),
        },
        "evidence_boundary": (
            "frozen synthetic demo account and deterministic student inputs; LLM judge feedback "
            "is formative; Agent non-prosecution branch is not expert validation or a guaranteed legal outcome"
        ),
    }

    json_path = args.json.resolve()
    html_path = args.html.resolve()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8")

    inv_errors = "".join(f"<li>{html.escape(item)}</li>" for item in public["inv"]["error_tags"])
    inv_gaps = "".join(f"<li>{html.escape(item)}</li>" for item in public["inv"]["knowledge_gaps"])
    scores_inv = public["inv"]["capability_scores"]
    scores_pr = public["pr"]["capability_scores"]
    snapshot_html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>case3 INV/PR 审计快照</title>
<style>
:root{{--paper:#f1eee7;--ink:#0d1110;--panel:#151a18;--line:#39413d;--blue:#1554d1;--amber:#c99b54;--muted:#9da7a1}}
*{{box-sizing:border-box}} html,body{{margin:0;width:100%;height:100%;overflow:hidden;background:#080b0a;color:var(--paper);font-family:"Microsoft YaHei UI","Source Han Sans SC",sans-serif}}
.deck{{display:flex;width:200vw;height:100vh;transform:translateX(calc((var(--slide,1) - 1) * -100vw))}}
.slide{{width:100vw;height:100vh;flex:0 0 100vw;padding:42px 54px 44px;position:relative;display:grid;grid-template-rows:auto 1fr auto;gap:26px;background:radial-gradient(circle at 85% 10%,rgba(21,84,209,.12),transparent 32%),#0a0d0c}}
.top{{display:flex;justify-content:space-between;border-bottom:1px solid var(--line);padding-bottom:18px}} .eyebrow{{font:600 14px/1.2 Consolas,monospace;letter-spacing:.18em;color:var(--muted)}} .title{{font-family:Georgia,"Microsoft YaHei UI",sans-serif;font-size:42px;line-height:1.05;margin:8px 0 0;font-weight:400}} .flag{{background:var(--blue);padding:10px 14px;font-weight:600;font-size:14px;align-self:start}}
.grid{{display:grid;grid-template-columns:1.06fr .94fr;gap:24px;min-height:0}} .panel{{border:1px solid var(--line);background:rgba(21,26,24,.78);padding:24px;min-height:0}} .panel.blue{{border-top:4px solid var(--blue)}} .panel.amber{{border-top:4px solid var(--amber)}} .label{{font:600 13px/1.2 Consolas,monospace;letter-spacing:.16em;color:var(--muted);text-transform:uppercase}} h2{{font-size:25px;margin:10px 0 14px}} p{{font-size:17px;line-height:1.65;margin:0;color:#d9ddd9}} blockquote{{font-size:18px;line-height:1.65;margin:18px 0 0;padding:18px 20px;border-left:3px solid var(--blue);background:#0c100f}}
.scores{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:18px 0}} .score{{border-top:1px solid var(--line);padding-top:10px}} .score b{{display:block;font:300 42px/1 Georgia,serif;color:var(--paper)}} .score span{{font-size:13px;color:var(--muted)}} ul{{margin:12px 0 0;padding-left:20px}} li{{font-size:15px;line-height:1.55;margin:5px 0;color:#cbd1cd}} .decision{{font-size:28px;color:#fff;margin:10px 0}} .no{{color:#7fc2ff}} .source{{font:500 12px/1.4 Consolas,monospace;color:var(--muted);word-break:break-all}} .foot{{display:flex;justify-content:space-between;align-items:end;border-top:1px solid var(--line);padding-top:14px}} .boundary{{font-size:13px;line-height:1.45;color:var(--muted);max-width:1150px}} .page{{font:600 14px Consolas,monospace;color:#7fc2ff}}
</style></head><body><div class="deck">
<section class="slide"><header class="top"><div><div class="eyebrow">CASE 3 · INVESTIGATION · LEARNING EVENT</div><h1 class="title">侦查阶段：证据方向正确，但程序回应不足</h1></div><div class="flag">真实E2E审计快照 · 非用户数据</div></header>
<main class="grid"><article class="panel blue"><div class="label">Student evidence quote</div><h2>固定脚本回答中的证据组织</h2><blockquote>{html.escape(public['inv']['evidence_quote'])}</blockquote><div class="scores"><div class="score"><b>{percent(scores_inv['fact_identification'])}</b><span>事实识别 · LLM形成性</span></div><div class="score"><b>{percent(scores_inv['procedural_compliance'])}</b><span>程序合规 · LLM形成性</span></div><div class="score"><b>{percent(scores_inv['rule_retrieval'])}</b><span>规范检索 · LLM形成性</span></div></div><p>{html.escape(public['inv']['knowledge_reason'])}</p></article>
<aside class="panel amber"><div class="label">Formative audit</div><h2>错误标签</h2><ul>{inv_errors}</ul><h2>下一步知识缺口</h2><ul>{inv_gaps}</ul><div class="label" style="margin-top:18px">SOURCE WARNING</div><p style="margin-top:8px">`INV_result.json`内部scenario_type为LC，未用于本页INV断言；本页只使用stage=INV的LearningEvent。</p></aside></main>
<footer class="foot"><div class="boundary">固定演示账号与确定性学生输入；评分为形成性，不是正式成绩、用户数据或专家法律结论。</div><div class="page">INV · 01 / 02</div></footer></section>
<section class="slide"><header class="top"><div><div class="eyebrow">CASE 3 · PROSECUTION REVIEW · CONDITIONAL BRANCH</div><h1 class="title">审查起诉：法条核验通过，检察官回应后进入不起诉分支</h1></div><div class="flag">真实E2E审计快照 · 固定脚本回答</div></header>
<main class="grid"><article class="panel blue"><div class="label">Defense ↔ Prosecutor</div><h2>学生辩护主线</h2><blockquote>{html.escape(excerpt(public['pr']['lawyer_argument'],260))}</blockquote><h2>检察官最后回应</h2><p>{html.escape(excerpt(public['pr']['prosecutor_response'],260))}</p><div class="scores"><div class="score"><b>{percent(scores_pr['rule_retrieval']['score'])}</b><span>规范检索 · {html.escape(str(scores_pr['rule_retrieval']['source']))}</span></div><div class="score"><b>{percent(scores_pr['subsumption']['score'])}</b><span>要件涵摄 · LLM形成性</span></div><div class="score"><b>{percent(scores_pr['claim_construction']['score'])}</b><span>主张构建 · LLM形成性</span></div></div></article>
<aside class="panel amber"><div class="label">Governed citation</div><h2>《刑法》第二十条</h2><p>{html.escape(excerpt(public['pr']['valid_citation']['content'],190))}</p><div class="label" style="margin-top:18px">AGENT DECISION</div><div class="decision"><span class="no">不起诉</span> · prosecute=false</div><p>{html.escape(public['pr']['decision']['reason_excerpt'])}</p><div class="source" style="margin-top:14px">decision reason SHA-256 · {public['pr']['decision']['full_reason_sha256']}</div></aside></main>
<footer class="foot"><div class="boundary">Agent条件分支不保证法律结论，不等于专家复核；冻结run：{public['e2e']['elapsed_seconds']}秒 / {public['e2e']['fixed_response_count']}次固定回答 / {public['e2e']['agent_despawn_count']} Agent退场 / {public['e2e']['runtime_issue_count']} runtime issue。</div><div class="page">PR · 02 / 02</div></footer></section>
</div><script>const n=Math.max(1,Math.min(2,Number(new URLSearchParams(location.search).get('slide')||1)));document.documentElement.style.setProperty('--slide',n);</script></body></html>"""
    html_path.write_text(snapshot_html, encoding="utf-8")
    print(json.dumps({"json": str(json_path), "html": str(html_path), "source_warning": public["excluded_source_warning"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
