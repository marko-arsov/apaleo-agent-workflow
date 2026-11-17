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
Implementation and publishing safety checks fail closed. Pipeline review fixes verified bugs and
polishes changed lines within the plan's paths. Its report, provider, environment, and unfixed
Medium/Low findings remain advisory and never stop later selected stages. A High finding it truly
cannot fix pauses the run with `PIPELINE_INPUT_REQUIRED`. Direct `/review` reports first and
applies what the user picks.

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

When `PIPELINE_DETACHED` is printed, report its pid/log/status/watch lines. With `--no-wait`,
return after the tracking lines.

## Supervise

This chat is the supervisor; follow `$ROOT/.claude/skills/references/pipeline-supervisor.md`.
1. Run with the default wait mode and `--notify`.
2. When the watcher returns `WAITING_FOR_INPUT` or a failure, diagnose it and take the matching
   playbook action. Answer pending questions that the plan, `AGENTS.md`, or a reference already
   settles with `--answer`, citing the source.
3. Resume. Completed stages are kept.

Escalate to the user only for a real blocker: a product or scope decision, a plan change,
credentials, the user's own files, or a spent recovery budget. Relay a user's answer with
`--answer` verbatim instead of starting a fresh stage session.

The worker already repairs a rejected stage result in the same session (up to two times) before it
stops. The test-edit check (`test_judge`) runs inside the worker after the last test-editing
stage; the supervisor never overrides it.

On Cursor, this chat is the pipeline orchestrator. Rename it to the issue and the live stage, and
update that title when the watcher reports a new stage. Follow `references/cursor-chat-title.md`.
The watcher itself stays model-free; one rename per stage change is the only extra step.
