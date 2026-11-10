---
name: implement-pipeline
description: >-
  Runs the plan-confirmed implementation stages in detached fresh sessions,
  with per-stage Codex/Cursor/Claude model routes, health checks, progress updates,
  resume state, and fail-closed verification. Use after /specify.
disable-model-invocation: true
argument-hint: "[task|branch] [--stages ...] [--route ...]"
---

# Implement pipeline

Run the deterministic worker and print its output:

```bash
"$ROOT/.claude/skills/pipeline/implement-pipeline.sh" "$@"
```

The selected stages come from the `/specify`-confirmed `pipeline.json`. `implement` is always
required. `implement-tests` is automatically required when the plan says tests must be added or
updated. `implement` progressively loads the `/test-and-fix` procedure in the same provider session
and always owns named-command verification, fixing, traceability, diff-budget, convention, and
secret gates. `review`, `commit-and-push`, and `draft-pr` are optional; `draft-pr` requires
`commit-and-push`.

Each AI stage and every provider retry/fallback starts in a new provider session with fresh context.
The only continuation exception is a genuine user-input pause inside a stage: the runner persists
that exact session id and resumes it after `--answer`. It never transfers a session between stages,
routes, retries, or fallbacks. The filesystem plan, git diff, and stage reports are the normal handoff.
Implementation and publishing safety checks fail closed. Pipeline review applies safe, in-plan
corrections and same-behavior improvements, but its findings, report, provider, and environment
issues remain advisory and never stop later selected stages. Direct `/review` is check-only.

## Autonomy

The worker should keep moving until an action or decision only the user can supply is required.
It automatically starts/waits for Docker, waits for the E2E lock, retries transient local/provider
failures, challenges premature blocked markers in the same session, and permits reversible
lock-protected local image/container switching with mandatory restoration. Mechanical test-fixture
defects settled by the plan or established contracts are routed to the selected fixing stage, not
escalated as product questions. The orchestrator also rejects an agent's input-required marker when
its stated reason is one of these known-recoverable categories.

A true pause has status `WAITING_FOR_INPUT` and prints the exact question. After the user replies,
continue the same provider session with:

```bash
/implement-pipeline HC-3333 --answer '<verbatim user answer>'
```

Do not use `--answer` to silently change the confirmed product contract; material plan changes still
require a complete `/specify` v2.

## Overrides

Runtime overrides never rewrite the confirmed plan:

```bash
/implement-pipeline HC-3333 \
  --stages implement-tests,implement,review,commit-and-push,draft-pr \
  --route implement=cursor:grok-4.7-high \
  --route review=cursor:gpt-5.6-sol-high \
  --fallback review=cursor:grok-4.7-high \
  --fallback review=codex:gpt-5.6-sol:high
```

Fallbacks are opt-in. Permanent authentication, spend-limit, quota, or invalid-model errors are not
retried. Temporary provider failures get fresh-session retries; in-stage autonomy continuations stay
in that stage's session.

## Progress

In chat/non-TTY use, the worker detaches safely and the foreground watcher prints structured stage,
route, retry, heartbeat, and completion updates (default every 90 seconds). The watcher uses no model.

```bash
/implement-pipeline HC-3333 --status
/implement-pipeline HC-3333 --watch
/implement-pipeline HC-3333 --no-wait
/implement-pipeline HC-3333 --dry-run
/implement-pipeline HC-3333 --preflight-only
```

When `PIPELINE_DETACHED` is printed, report its pid/log/status/watch lines. With the default wait
mode, keep streaming until success, a verified hard failure, or `WAITING_FOR_INPUT`. If input is
required, ask the exact saved question; when the user answers, invoke `--answer` with their response
instead of starting a fresh stage session. With `--no-wait`, return after the tracking lines.

On Cursor, this chat is the pipeline orchestrator. Rename it to the issue and the live stage, and
update that title when the watcher reports a new stage. Follow `references/cursor-chat-title.md`.
The watcher itself stays model-free; one rename per stage change is the only extra step.
