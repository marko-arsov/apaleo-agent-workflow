# `implement-pipeline` runner

```bash
$ROOT/.claude/skills/pipeline/implement-pipeline.sh <task-or-branch> [options]
```

The runner resolves the latest complete `pipeline.json`, applies ephemeral overrides, preflights, starts each
AI stage in a fresh provider process, verifies postconditions, persists state, and writes a recap.

## Commands

```bash
implement-pipeline.sh HC-3333 --dry-run
implement-pipeline.sh HC-3333 --preflight-only
implement-pipeline.sh HC-3333
implement-pipeline.sh HC-3333 --no-wait
implement-pipeline.sh HC-3333 --status
implement-pipeline.sh HC-3333 --watch
```

If omitted inside a feature worktree, the task resolves from the current non-base branch.

## Selection and routing

```bash
implement-pipeline.sh HC-3333 \
  --stages implement-tests,implement,review,commit-and-push,draft-pr \
  --route implement-tests=cursor:claude-sonnet-5-5-high \
  --fallback implement-tests=claude:sonnet:high \
  --route implement=cursor:grok-4.7-high \
  --route review=cursor:gpt-5.6-sol-high \
  --fallback review=cursor:grok-4.7-high \
  --fallback review=codex:gpt-5.6-sol:high \
  --fallback review=claude:sonnet:high
```

- `implement` is always inserted; `implement-tests` is inserted when tests change.
- `draft-pr` requires `commit-and-push`.
- `test-and-fix` is not a stage; `implement` executes that procedure internally.
- Any valid provider/model may be used for every AI stage. The evaluator suggests a different lab for test authoring and review; that suggestion stays advisory and an explicit route wins.
- `/specify` offers review rather than forcing it. It evaluates model and effort offline, then
  saves an immutable selection snapshot. `/update-models` reviews machine/project defaults;
  read `references/model-policy.md` for its commands and independent settings.
- Codex/Claude reasoning is optional: omission uses the host default, never injected high.
  Cursor reasoning is encoded in the exact model id.
- Repeated fallback assignments define an approved order. `/specify` suggests a chain, which the user
  may keep, edit, or clear; the runner never invents an undeclared fallback.
- Overrides are stored in run evidence, never in the confirmed plan.

## Prompt and context contract

The prefix before `# Stage-specific tail` is byte-identical for every stage of one plan revision:
`AGENTS.md`, `product.md`, `implementation.md`, `deferred-scope.md`, and `pipeline.json`. Dynamic
run data appears only in the tail. Provider-owned tool definitions precede this user prompt.

`pipeline.json.context_contracts` declares reads, denied inputs, and writes. The runner controls
prompt injection and verifies write paths/reports. It does not provide OS-level read isolation;
see `references/security-boundary.md`.

## Verification

Manifest v2 contains exact test argv/parser rows, AC mappings, test/product path globs, diff budget,
risk, and optional diff-scoped mutation command. The runner:

- gates implementation on assertion-level `red-proof.md` (every dirty `test_paths` file must appear as `apaleo/...` / `development/...` or the repo-relative remainder);
- executes/parses every test command inside implementation;
- requires every AC's named test to exist and its observed output to match;
- rejects out-of-plan paths, secrets, blocking conventions, and missing implementation traceability;
  oversized diffs, plan revisions, and review-report issues are recorded as advisories;
- fingerprints the diff so stale evidence cannot be reused;
- pipeline review may apply safe in-plan improvements and reruns only narrow affected checks, never
  the full test/E2E suite; it receives the `/add-rule` registry, metadata, allowlist, and scoped
  rules, then repeats the fast deterministic convention/secret scan after review edits. Tier-1
  convention violations must be repaired; direct review is check-only. Publish runs only a
  fast safety scan because implementation owns named test verification.

Direct `/commit` runs only fast diff-scoped convention/Semgrep and secret/gitleaks checks; it does
not repeat project tests. Mutation testing is opt-in authorization/billing work only.

Version-1 manifests are upgraded in memory and remain immutable on disk.

## Fresh sessions and recovery

- Cursor: new `agent -p`; Codex: new `codex exec`; Claude: new `claude -p`.
- Every stage, retry, and fallback starts fresh.
- A genuine stage question resumes only that exact session via `--answer`.
- Partial edits survive only within manifest paths; a sanitised recovery packet informs a fresh
  retry/fallback.
- Permanent auth/billing/quota/model failures do not retry. Temporary provider failures may retry
  once by default.

## Preflight and limits

Preflight verifies the complete manifest/plan, worktrees and parked mains, publish scripts and `gh`,
Docker for selected E2E, and every approved route. Active route probes cache for ten minutes.

| Flag | Default | Meaning |
|---|---:|---|
| `--max-provider-retries` | 1 | fresh retries per approved route |
| `--max-stage-continuations` | 3 | same-session autonomy challenges |
| `--docker-start-timeout` | 600 | Docker startup/wait seconds |
| `--inactive-warning` | 300 | silence warning seconds |
| `--inactive-timeout` | 600 | silence termination seconds |
| `--stage-timeout` | 5400 | total provider-attempt seconds |
| `--tool-call-grace` | 120 | grace after a provider tool exceeds its declared timeout |
| `--update-every` | 90 | watcher heartbeat seconds |

## Resume, state, and evidence

```bash
implement-pipeline.sh HC-3333 --from review
implement-pipeline.sh HC-3333 --to commit-and-push
implement-pipeline.sh HC-3333 --no-resume
implement-pipeline.sh HC-3333 --reset-progress
implement-pipeline.sh HC-3333 --answer 'the required answer'
```

Rerunning an earlier stage invalidates downstream evidence. Any complete in-place or versioned plan
revision archives/resets state and becomes active automatically.

If a normal `implement-tests` run was interrupted after writing valid current `red-proof.md` and
`tests-implementation-<n>.md`, the next normal resume re-verifies those artifacts and continues at
`implement`; `--no-resume` deliberately disables that recovery.

```text
.local/pipeline-runs/<timestamp>_<task>/
.local/pipeline-state/<task>/progress.json
.local/pipeline-verification/<branch>/<fingerprint>/
```

Exit codes: `0` success, `2` failure, `3` waiting for input, `64` invalid invocation.

## Modules

| File | Responsibility |
|---|---|
| `pipeline_manifest.py` | manifest v2, v1 translation, routes, contracts |
| `pipeline_state.py` | schema-v3 resumable state and audit records |
| `implement_pipeline.py` | orchestration, retries, watcher, stage claims |
| `assemble_prompt.py` | cache-stable prefix and dynamic tail |
| `verification.py` | parsed commands, traceability, budgets, scanners |
| `untrusted_input.py` | sanitise, flag, and delimit external data |
| `rule_registry.py` | rule tiers, metadata, counters, promotion/pruning |
| `workflow_audit.py` | 2026 checkpoints and primary security boundary |
