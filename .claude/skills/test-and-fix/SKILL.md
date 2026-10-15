---
name: test-and-fix
description: >-
  Reusable verification/fix procedure for build, unit, filtered integration,
  and plan-scoped E2E. It is loaded inside /implement and may also be invoked
  manually after PR-comment fixes; it is not a top-level implementation stage.
disable-model-invocation: true
argument-hint: "[branch-name]"
context: fork
background: false
model: opus
effort: medium
---

# Test and Fix procedure

Get the suite green **for the right reasons**.

**Defining constraint:** without the plan, a failing test and the code are two conflicting claims — the cheapest wrong fix is changing the test. Refuse to proceed if no plan resolves; ask for branch or plan path.

**Cursor note:** fork/model/effort are Claude Code-only; use the matching Cursor subagent or run
in-session.

**Checkpoint note:** forked edits are outside `/rewind` — use git.

When loaded by `/implement`, stay in the same provider session and use its already-loaded immutable
plan, red proof, current filesystem, and failing output. Do not read `prompt.md`, prior provider
rationale, or launch another agent. For a manual post-PR invocation, resolve the current complete plan and
read only the specific handoff/report needed to understand the new edits. The `## Validation and
Test Strategy` table is the tiebreaker. Load `e2e-test-engineering-development` before modifying
anything under `development/`. Read `$ROOT/.claude/skills/references/worktrees.md`.

**Worktree:** ensure `$WT` for the plan branch via `worktree-start` if needed; run all builds/tests under `$APALEO` / `$DEV` / `$IDENTITY`; mains stay on `master`; `move_agent_to_root` → `$WT`.

State loaded skills/paths + plan path + worktree paths in output.

## Model gate

This procedure has no pipeline route. Inside `/implement`, it uses the existing implementation
session and therefore adds no model call. A direct manual invocation uses the current session.


## Execution order (cheapest signal first)

1. **Build** every worktree repo that exists (AGENTS.md commands from `$APALEO` / `$DEV` / `$IDENTITY`). Fix build before trusting tests.
2. **Unit tests** in `apaleo` — full: `dotnet test Apaleo.sln -c Debug --no-build` (build first if needed).
3. **Integration** in `apaleo` — **filtered** to touched projects / name filters from the plan (decision 5B). Start required infra per AGENTS if those tests need it. Escalate to broader runs only if the user asks or failures demand it.
4. **E2E** in `development` — specs from the E2E Test Plan plus specs touching affected flows. Prefer `npm run test:file -- <path>`. Use `npm run test:core` when the change is broad or the user asks. **Never** full `npm test` locally. State which command ran.

   **Stack lock + wait queue (mandatory before localhost E2E):**

   1. Finish build/unit/integration **first** (no lock — safe across worktrees).
   2. Read `$ROOT/.claude/skills/references/e2e-stack.md`.
   3. Acquire with **wait** (do not stop if another worktree holds the seat):

      ```bash
      $ROOT/.claude/skills/references/e2e-stack-lock.sh acquire --wait \
        --branch "<target>" --worktree "$WT" --skill test-and-fix
      ```

      Print waiting lines to the user. On timeout (exit 4) → stop and report queue status.
   4. Use the `image=` from acquire (`apaleo-ui-api:wt-<slug>`), rebuild/repoint/recreate `api` only while holding the lock. If `$WT/identity` exists and this branch changes Identity, also use `identity_image=` (`apaleo-identity:wt-<slug>`), build from `$WT/identity`, pin `IDENTITY_IMAGE` in gitignored `development/apaleo/.env`, recreate `identity` — `references/identity.md`. Run E2E.
   5. In `finally`-style cleanup, restore the prior image/configuration and verify its health. Then always
      release when the E2E phase ends (unless user asks to keep the seat). Release removes the unused
      branch-scoped image and caps BuildKit cache; it does not touch containers or volumes:

      ```bash
      $ROOT/.claude/skills/references/e2e-stack-lock.sh release --branch "<target>"
      ```

   `/e2e-stack-status` shows owner + queue anytime.

   **Missing Identity scopes (local-only workaround):** if `ensureNewAccountCreated` fails with `You requested scopes that do not exist: …`, read `$ROOT/.claude/skills/references/e2e-missing-identity-scopes.md`. When the ticket does **not** need those scopes, strip them from `$DEV/src/config.ts` via `e2e-local-scope-workaround.sh apply` and re-run the same E2E command. **Never commit or push that patch.** Restore before leaving this stage if you will not run commit next; `implement-pipeline.sh` also restores on EXIT and before `commit-and-push`. If the feature **does** need the missing scopes → `PIPELINE_INPUT_REQUIRED` (Identity seed, not this file). Do not recreate the whole `db` container to fix apaleo schema drift (drops Identity).

If the suite would hit a shared environment → confirm before the first run in the session. Never run plan-flagged destructive cases without approval.

Report actual command and result every step. A run you did not execute is not a pass.

## Classify before fixing

| Classification | Action |
|---|---|
| Code wrong — test asserts what the plan requires | Fix code |
| Test wrong — asserts old behaviour the plan deliberately changed | Update test; cite AC or `D#` |
| Test badly written (fixture/setup/timing) | Fix per `e2e-test-engineering-development` / `clean-code`; explain |
| Environmental (infra, shared data, known flaky) | Do not "fix" product code or tests. Report evidence. **Exception:** missing Identity `ApiScopes` after a local DB reset — local `config.ts` strip only if the ticket does not need those scopes (`e2e-missing-identity-scopes.md`). Never commit that strip. |
| Ambiguous — plan does not settle it | Stop and ask |

## Absolute prohibitions

- Never delete/skip/`[Ignore]`/comment out/quarantine/filter out a failing test to greenwash.
- Never weaken assertions or widen tolerances to accommodate wrong code.
- Never change a test to match behaviour the plan does not authorize.
- Never mark flaky to avoid diagnosis — leave failing and report evidence.
- Never reduce coverage silently.
- Never commit the local Identity-scope `config.ts` strip (`e2e-missing-identity-scopes.md`).

## Loop

After each fix: narrowest re-run that proves it → full level it belongs to → continue. If a later level breaks an earlier one, restart from the earliest broken level. Cap **five** fix-and-rerun cycles overall. Same test failing after three different fixes → stop (diagnosis wrong).

## Output

Write `$ROOT/ai-plans/<branch>/test-report-<n>.md`; print condensed version.
For a legacy pipeline report, include `New product/architectural decisions: none`; otherwise stop
with a plan defect.

Per level: command, pass/fail counts; per failure: classification, root cause, change, re-run result.
Leftover failures with why. Verdict: `All green — continue to <next selected stage|pipeline
complete>` | `Not green — <n> failing: …` | `Blocked — needs your decision on <ids>`.

Append one line to `progress.md`. Never commit or push.
## Execution inside `/implement-pipeline`

- The implementation verification subphase fails closed. Recover environmental blockers autonomously first;
  after recovery is exhausted, stop with evidence or request the concrete user-only action. They
  never become a skipped stage followed by a draft PR.
- Known flake (OPA authz race right after container recreate): re-run that one spec once before
  calling it red. Never add a skip to greenwash — use `PIPELINE_INPUT_REQUIRED` only if user action
  is genuinely necessary.
- Retry transient Docker registry, image-pull, daemon, compose, and network failures with bounded
  exponential backoff in this same session. Keep the lock/previous-image restoration safe while
  retrying; do not return control merely to ask the user to “try again.”
- A product failure you cannot fix inside the plan's scope requires `PIPELINE_INPUT_REQUIRED` with
  evidence only when user direction is necessary.
- Never emit `PIPELINE_STAGE_SKIPPED`.
- Run `pipeline/verification.py <branch> --root "$ROOT" --force`; the runner verifies its
  fingerprinted JSON/Markdown evidence. Write `test-report-<n>.md` only when executing a legacy v1
  manifest that originally selected the retired top-level stage.

## Logs to the model

Never paste raw `dotnet build` / `dotnet test` / `npm run test:file` output into the transcript.

1. Write the full log to `$ROOT/.local/pipeline-runs/<run>/logs/<stage>-<n>.log` (or `$LOG_DIR/logs/`).
2. Feed it through `python3 $ROOT/.claude/skills/pipeline/summarize_output.py --mode dotnet-build|dotnet-test|jest <logfile>`.
3. Give the model the summary + the log path. Grep the log only when the summary is insufficient.

If `$LOG_DIR/scope.json` exists, prefer filtered `dotnet test` on touched test projects and
`test:file` for mapped Jest specs. A selected stage is never skipped; risk flags require the broader
plan-specified suite.
