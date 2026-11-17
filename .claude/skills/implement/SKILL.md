---
name: implement
description: >-
  Executes an ai-plans/<branch> plan inside the feature worktree. Manual lane: writes the tests
  first, builds the plan's steps, verifies with the full test-and-fix loop plus API samples, and
  reviews its own diff (bugs, test strength, polish). Pipeline: builds against the committed tests
  and verifies; the review stage does the independent review. Mains stay on master. Does not
  commit or push.
disable-model-invocation: true
argument-hint: "[branch-name | PlanFile path]"
model: sonnet
effort: medium
---

# Implement

Execute the plan with minimal drift. Never commit, push, or edit the plan files (`product.md`,
`implementation.md`, `prompt.md`).

| Lane | Phases this skill runs |
|---|---|
| Manual (`/specify` → `/implement`) | 1 Tests first → 2 Build → 3 Verify → 4 Self-review |
| Pipeline (`/implement-pipeline`) | Red after skeleton → 2 Build → 3 Verify; the review stage replaces 4 |

## Model gate

Host: Cursor Grok 4.7 via `implement-cursor` (`grok-4.7-high`); never Cursor Claude. Claude Code:
`sonnet` at medium. `model`/`effort` frontmatter applies only in Claude Code. The plan was written
on a stronger model for exactly this route; follow it rather than re-planning. See
`$ROOT/.claude/skills/references/model-routing.md`.

## Cursor chat title

On Cursor, rename this chat once the plan resolves: status `implement` while working, `waiting`
when you stop for the user, and `done` when verification finishes (`references/cursor-chat-title.md`).

## Setup

**Plan.** Accept an explicit path, `PlanFile:`, a branch name, or the current worktree branch, and
resolve `$ROOT/ai-plans/<branch>/` (the highest complete five-file set; prefer `vN/`). Read
`product.md`, `implementation.md`, `deferred-scope.md`, and `pipeline.json`, plus `red-proof.md`
in the pipeline. Never read `prompt.md`. If nothing resolves, stop and ask. The plan folder name is
the target branch.

**Load.** `references/existing-patterns.md` (the primary constraint), `clean-code`,
`references/worktrees.md`, and `e2e-test-engineering-development` before touching `e2e/` or
`development/`. Load these when the plan touches their area:
- `references/api-endpoint-patterns.md` for API actions;
- `references/identity.md` for authorization;
- `references/db-migrations.md` for schema;
- `references/feature-flags.md` for flags (remind the user of the ConfigCat and local setup
  before calling the feature testable);
- `references/api-enum-wire-values.md` for enums.

Before broad search in apaleo, use Graphify per `references/graphify.md`; skip it cleanly when it
is missing. Never auto-invoke `setup-new-service`.

**Worktree failsafe**, before any write:
1. Parked mains stay on `master`; never switch a branch in `$ROOT/<repo>`.
2. Ensure `$WT=$ROOT/worktrees/<target>` with `worktree-start` in existing-branch mode only. Never
   create from master here. Attach only the repositories the plan names:
   - `development` only for payment E2E or another file that still lives there;
   - `identity`, `agent-skills`, or `angular-api-proxy` only when `pipeline.json` paths or
     `implementation.md` need them.

   A new repository need is a plan defect.
3. Pipeline: the implement-tests commit holds the tests, and they are the contract. Uncommitted
   changes are acceptable only inside `test_paths` from an interrupted handoff; any other
   pre-existing changes mean stop.
4. Each in-scope repository is on `<target>`. Re-check immediately before the first write in it.
   Edit only under `$WT/**` (Cursor: `move_agent_to_root` → `$WT`).
5. If a required worktree fails, stop with questions. No partial implementation.

**Linear (manual lane, first pass only):** take the issue id from the branch name and ask before
moving it to In Progress via `keep-linear-updated`. A pipeline stage never changes Linear.

## Authority

1. Existing repo patterns and `AGENTS.md` (root and nearest): match the cited neighbour.
2. The user's explicit instructions, and `clean-code` as that neighbour applies it.
3. `implementation.md` for technical execution.
4. `product.md` for product intent and the acceptance criteria.

Plan files that conflict with each other, or repo evidence that contradicts the plan: stop with
numbered questions. Do not "improve" the neighbour.

Use the plan the way it is written for you:
- Copy the shapes in `## Read first` before searching more widely.
- Work through `## Steps` in order. Confirm each step's done-when check before the next.
- Treat every `## Traps` entry as a known failure mode, and avoid it.
- `## Decisions` and `## Assumptions` are settled; do not revisit them.
- `product.md` `## Examples` hold the exact expected values.
- A choice the plan does not settle (a name, placement, status code, or behaviour) is a plan
  defect. Manual lane: ask. Pipeline: report `PLAN_DEFECT`, never a new decision.

## Phase 1 — Tests first

**Manual lane.** Write the tests in `## Tests` before product code, following the rules in
`$ROOT/.claude/skills/implement-tests/SKILL.md` ("Write tests that catch wrong implementations"):
- exact values from the Examples;
- data that separates the right source from a plausible wrong one;
- the edges the plan settles;
- literal test names.

Run them and confirm they fail at an assertion because the behaviour is missing. When they cannot
compile yet, add the skeleton first (members and signatures, no logic), then confirm the
assertion-level red. A bugfix follows reproduce → regression check → red for the original defect
→ fix → green. A check that only executes the changed code is not a regression check. Record the
red and green evidence in `progress.md`. No `red-proof.md` is needed.

**Pipeline.** The committed tests are the contract. When `red-proof.md` says `Failure level: none`,
build the skeleton until they run, confirm they fail at their assertions, and append
`## Red after skeleton` to `red-proof.md` (test, command, failing assertion or status; no compiler
output).

Both lanes: never weaken, skip, delete, quarantine, or loosen an assertion. In the pipeline, a test
may change only for a plan-settled fixture or setup defect, and the runner restores anything else.

## Phase 2 — Build

- Follow `## Steps`, copying the `## Read first` neighbours. Implement only in-scope work; no
  opportunistic refactors.
- Reuse before creating. Search, cite `repo/path:line`, and record the search in `progress.md`. A
  new type needs one line on why the existing one does not fit.
- API routes: register every action in OPA `endpoint_permissions`, mirroring the sibling entries.
  Property-association writes authorize old ∪ new property ids through `[ResourceMetadata]` +
  `IPropertyLevelRequestModel`, not a wrapper service. PUT is a full replacement.
- Enums follow the plan's decision; the default is CLR member names. Do not invent a
  display-string converter.
- Migrations: finish the `[DB-MIGRATION]` slice before the code that depends on it. Never
  Drop/Rename in the same PR as removing entity properties.
- Edit product and generated files only within `pipeline.json.allowed_paths`. A needed path outside
  them is a plan defect. Regenerate generated clients with the canonical flow; never hand-edit them.
- Prefer LSP for symbol questions, and say when you fall back to text search.
- After each step, append to `progress.md`: step, files, check and result, and any plan mistake.

## Phase 3 — Verify

Load and execute `$ROOT/.claude/skills/test-and-fix/SKILL.md` in this same session; never launch
another agent. Run every `pipeline.json.test_commands` entry until the parser is green. While the
branch image still runs:
- capture the **API samples** when the plan changes an HTTP endpoint;
- run the **UI check** when `## Tests` has a `ui` row.

test-and-fix describes both.

Finish with:

```bash
python3 "$ROOT/.claude/skills/pipeline/verification.py" <branch> --root "$ROOT" --force
```

A command that was not executed and parsed is not a pass. Localhost E2E, Swagger/proxy
generation, and branch-image switching use the E2E stack lock, with the prior image restored in
`finally`-style cleanup. Behind master in the manual lane: suggest `/sync-master`; never merge
unattended.

## Phase 4 — Self-review (manual lane only)

The manual lane has no review stage, so review your own diff with the independent reviewer's
method from `$ROOT/.claude/skills/review/SKILL.md`. Act as a sceptic, not the author.
1. **Tier 1 lenses** (security and authorization, logic and data, performance and reliability,
   contract and intent) on the diff. Fix every finding you can back with a failure scenario.
2. **Test strength**: run `references/test-strength.md` and add a hardening test for every mutant
   that survives.
3. **Tier 2 polish** on changed lines only, behaviour unchanged.
4. Re-run the affected commands and `verification.py --force`. Append a short `## Self-review` to
   `progress.md`: what you fixed, the test-strength table, and what you polished.

For security, money, tenancy, schema, or public-contract changes, recommend an independent
`/review <branch>` in a new chat before the PR.

## Pipeline execution (`/implement-pipeline`)

The plan should contain every decision. Exhaust safe in-scope work, retries, mechanical
corrections, and reversible local recovery. Emit `PIPELINE_INPUT_REQUIRED` with the minimum
numbered questions only when progress is impossible without the user; the runner resumes this
session. Report a missing decision as `PLAN_DEFECT`; no stage report introduces a product or
architectural decision. Never emit `PIPELINE_STAGE_SKIPPED`. Do not write `review-<n>.md`: the
runner starts review in a separate fresh session.

## Blocked

Output only numbered questions, then stop.

## Output

```text
Plan: <resolved path> · Branch: <target> · Lane: manual | pipeline
Worktree: $ROOT/worktrees/<target> (apaleo ok · development ok|not required · …) · Mains: master
Built: <bullets mapped to plan steps>
Red → green: <test → failing assertion → passing>
Checks: <command → parsed result, evidence path>
API samples / UI: <path | n/a>
Self-review: <fixed n · mutants k/m killed, h hardening tests · polished p | pipeline: review stage>
Plan mistakes: <none | list>
Next: <manual lane complete | /review <branch> recommended | next pipeline stage>
```
