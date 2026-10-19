#!/usr/bin/env python3
"""Generate a small, dependency-free workflow reference page."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().with_name("index.html")

STAGES = [
    ("implement-tests", "Task policy", "Model + effort from specification", "Test-only assertion-level red phase."),
    ("implement", "Task policy", "Model + effort from specification", "Product work plus internal verify/fix."),
    ("review", "Task policy", "Optional; independent model preference", "Fresh review with the live rule inventory and a post-fix scan."),
    ("commit-and-push", "Script", "no model", "Commit and push every worktree repo."),
    ("draft-pr", "Script", "no model", "Create and verify draft PRs."),
]


def latest_status() -> dict:
    candidates = sorted(
        (ROOT / ".local" / "pipeline-runs").glob("live-*.status.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            return value
    return {}


def main() -> int:
    status = latest_status()
    stage_cards = "\n".join(
        f"""<article class=\"stage\"><span class=\"num\">{index}</span>
        <h3>/{html.escape(name)}</h3><p>{html.escape(summary)}</p>
        <div class=\"route\">{html.escape(provider)} · <code>{html.escape(model)}</code></div></article>"""
        for index, (name, provider, model, summary) in enumerate(STAGES, 1)
    )
    if status:
        live = f"""<div class=\"live\"><span class=\"pulse\"></span><div>
        <small>Latest worker event</small><strong>{html.escape(str(status.get('task', 'unknown')))}</strong>
        <span>/{html.escape(str(status.get('stage', 'unknown')))} · {html.escape(str(status.get('message', '')))}</span>
        <em>{html.escape(str(status.get('updated', '')))}</em></div></div>"""
    else:
        live = """<div class=\"live muted\"><div><small>Latest worker event</small>
        <strong>No local run yet</strong><span>Start with /implement-pipeline &lt;task&gt;</span></div></div>"""
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    page = f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Apaleo implementation pipeline</title><style>
:root{{--ink:#15211b;--muted:#66756d;--paper:#f5f2e9;--card:#fffdf7;--line:#d9d3c5;--green:#286248;--lime:#b9d96a;--blue:#315f7d;--amber:#a96d2a}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 ui-sans-serif,system-ui,-apple-system,sans-serif}}
main{{max-width:1120px;margin:auto;padding:56px 24px 80px}}header{{display:grid;grid-template-columns:1.4fr .8fr;gap:40px;align-items:end;border-bottom:1px solid var(--line);padding-bottom:34px}}
.kicker{{font:700 12px/1.2 ui-monospace,monospace;letter-spacing:.16em;text-transform:uppercase;color:var(--green)}}h1{{font-size:clamp(42px,7vw,78px);line-height:.94;letter-spacing:-.055em;margin:14px 0 20px;max-width:780px}}header p{{font-size:20px;color:var(--muted);max-width:700px}}
.live{{background:var(--ink);color:white;border-radius:18px;padding:20px;display:flex;gap:14px;box-shadow:0 18px 40px #15211b22}}.live div{{display:grid;gap:3px}}.live small,.live em{{color:#b8c2bc;font-style:normal}}.live strong{{font-size:20px}}.pulse{{width:10px;height:10px;border-radius:50%;background:var(--lime);margin-top:7px;box-shadow:0 0 0 6px #b9d96a22}}.live.muted{{background:#e5e1d7;color:var(--ink)}}
section{{margin-top:52px}}h2{{font-size:30px;letter-spacing:-.025em;margin:0 0 18px}}.intro{{max-width:760px;color:var(--muted)}}
.flow{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}.stage{{position:relative;background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px;min-height:185px}}.stage .num{{position:absolute;right:18px;top:14px;color:#aaa08d;font:700 13px ui-monospace,monospace}}.stage h3{{margin:28px 0 8px;font-size:21px}}.stage p{{color:var(--muted);margin:0}}.route{{position:absolute;bottom:18px;left:22px;right:22px;border-top:1px solid var(--line);padding-top:11px;font-size:13px;color:var(--blue)}}code{{font-family:ui-monospace,SFMono-Regular,monospace}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}.panel{{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:24px}}.panel h3{{margin-top:0}}pre{{background:#17221c;color:#edf4ef;border-radius:12px;padding:18px;overflow:auto;font-size:13px}}ul{{padding-left:20px}}li{{margin:8px 0}}.tag{{display:inline-block;border:1px solid var(--line);border-radius:100px;padding:4px 10px;margin:3px;font-size:13px}}footer{{margin-top:60px;border-top:1px solid var(--line);padding-top:20px;color:var(--muted);font-size:13px}}
@media(max-width:820px){{header,.grid{{grid-template-columns:1fr}}.flow{{grid-template-columns:1fr 1fr}}}}@media(max-width:560px){{main{{padding:34px 16px 60px}}.flow{{grid-template-columns:1fr}}}}
</style></head><body><main>
<header><div><div class=\"kicker\">Apaleo · implementation system</div><h1>Plan clearly. Run smoothly.</h1><p>A revisable specification that challenges flawed assumptions, fresh test-first boundaries, and deterministic implementation evidence before publishing.</p></div>{live}</header>
<section><h2>The lanes</h2><p>Use <code>/update-models</code> to review machine or project defaults. Every specification evaluates model and effort offline; approved task routes remain fixed.</p><p class=\"intro\">For a small follow-up or isolated deterministic bugfix, use <code>/specify</code> then <code>/implement</code>. Bugfixes reproduce the failure, prove a regression check red, then fix it green in the same session. Use the staged runner when the cause is unclear, the defect is higher-risk, or you want independent review or automated publishing.</p><div class=\"flow\">{stage_cards}</div></section>
<section class=\"grid\"><article class=\"panel\"><h3>Run from any chat</h3><pre># simple manual lane
/specify HC-3333
/implement HC-3333

# full pipeline
/implement-pipeline HC-3333 --dry-run
/implement-pipeline HC-3333

# reconnect without a model
/implement-pipeline HC-3333 --status
/implement-pipeline HC-3333 --watch</pre><p>The detached watcher emits structured updates and a heartbeat about every 90 seconds.</p></article>
<article class=\"panel\"><h3>Failure contract</h3><ul><li>Health probes run before implementation tokens are spent.</li><li>Temporary provider failures get one fresh retry.</li><li>Recoverable in-stage blocks resume autonomously in the same session.</li><li>Docker is started/waited for and transient registry failures retry.</li><li>Permanent model-limit failures advance to the next confirmed fallback.</li><li>Fallbacks are suggested during specification and run only once confirmed.</li><li>Review, report, and budget issues are advisory; secrets, Tier-1 convention violations, and invalid write scope remain enforced.</li></ul></article></section>
<section class=\"grid\"><article class=\"panel\"><h3>Fresh boundaries, continuous stages</h3><p>Every stage, provider retry, and fallback starts fresh. Review sees the confirmed plan, tests, actual diff, and the current <code>/add-rule</code> inventory—not the implementation conversation. Pipeline review applies safe in-plan improvements with narrow verification, then repeats the deterministic convention/secret scan; Tier-1 violations must be fixed. Manual <code>/review &lt;branch&gt; [focus]</code> is check-only and asks for confirmation if its plan or solution basis is ambiguous. Only a genuine user-input pause resumes the exact same provider session after <code>--answer</code>.</p></article><article class=\"panel\"><h3>After the draft</h3><span class=\"tag\">/address-pr-comments</span><span class=\"tag\">--bugbot</span><span class=\"tag\">--draft-bugbot-replies</span><span class=\"tag\">/diagnose-ci</span><span class=\"tag\">/test-on-staging</span><p>These flows are invoked manually and stay outside the main lane. Once invoked, <code>/test-on-staging</code> checks the Jenkins pipelines and staging deployment for one or several issues and PRs, runs a few focused Apaleo MCP, API, browser, and read-only SQL checks, and ends with one production verdict: safe to deploy, quick fix first, revert, or wait.</p><h3>Support rotation</h3><span class=\"tag\">/support-rotation</span><p>Verifies the cloud support agent's Outcome claim by claim, reproduces on staging when that decides it, and drafts the Slack, Linear, and team-memory updates. Nothing is posted without a yes.</p></article></section>
<footer>Generated {generated} · Source: .claude/skills/WORKFLOW.md and references/pipeline-stages.md</footer>
</main></body></html>"""
    OUT.write_text(page, encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
