---
name: implement
description: >-
  Executes an ai-plans/<branch> implementation plan inside the feature worktree
  (apaleo ± development) with minimal drift, the complete verify/fix loop, and
  evidence parsed from named commands. Ensures the worktree exists; mains stay on master. Use when the user
  invokes /implement or asks to implement from the current plan. Does not commit
  or push.
disable-model-invocation: true
argument-hint: "[branch-name | PlanFile path]"
model: sonnet
effort: medium
---

# Implement

Execute the plan. Minimal drift. No commits, no pushes, never edit plan files (`product.md` / `implementation.md` / `prompt.md`).

**Cursor note:** `model` / `effort` are Claude Code-only; under Cursor this runs on the session model.

## Model gate

**Host: Cursor** — **Grok 4.7** via `implement-cursor` (`grok-4.7-high`). Never Cursor Claude.
Claude Code (optional): `model: sonnet` / medium if you implement there instead.
Read `$ROOT/.claude/skills/references/model-routing.md`.



## Graphify (apaleo)

Before broad codebase search in `$APALEO`, follow `$ROOT/.claude/skills/references/graphify.md`: merge graphs if needed, then `graphify query|path|explain`. After meaningful C# edits, `graphify update .` when the CLI is available (AST-only). Skip cleanly if Graphify is missing.

## When to run

After `/specify`. In the simple manual lane, this is the only execution command. For a bugfix,
default to: reproduce → add/update the regression check → prove it fails for the original defect →
fix → rerun it green → run the plan's named checks. Do not create a separate `implement-tests`
stage. For other manual follow-ups, author the needed tests first where practical, then implement
and verify in this same session. Invoking `/implement` directly after `/specify` selects this
manual lane. In the full pipeline, it follows `/implement-tests` when that stage is selected.
Not for planning, the independent review, commit, or push. This stage owns implementation plus the
complete plan-scoped verification/fix loop.

## Adopted skills

- **Existing patterns first:** `$ROOT/.claude/skills/references/existing-patterns.md` — the primary implementation constraint. Cite the neighbor before adding a file or type.
- When the plan changes an API action, load `$ROOT/.claude/skills/references/api-endpoint-patterns.md` and execute its action matrix. Re-check the resource's sibling actions before changing controller naming, request contracts, authorization, or service layering.
- Load `clean-code` at start (invoke or file-read). Apply while writing C# **as the local neighbor already does**.
- **New C# files:** file-scoped namespaces only (`namespace X.Y;`) — see `$ROOT/AGENTS.md` Conventions. Do not introduce classic `namespace { }` blocks in new files.
- **Hard precondition:** load `e2e-test-engineering-development` **before** touching any file under `development/`.
- Worktree rules: `$ROOT/.claude/skills/references/worktrees.md`.
- If the plan includes schema: follow `$ROOT/.claude/skills/references/db-migrations.md`. If the plan includes a ConfigCat / Features API flag: follow `$ROOT/.claude/skills/references/feature-flags.md` — add constant + `IFeatureSettingsProvider` gate + E2E helper; **remind the user** with filled Setup for humans (ConfigCat + local config) before claiming the feature is testable. Prefer finishing/committing the **`[DB-MIGRATION]`** slice (migration + snapshot; entities only if the plan says so) **before** API/domain that depends on it — often a separate branch/PR. Never Drop*/Rename* in the same PR as removing entity properties.
- If the plan adds or changes API routes: register **each** action in OPA `endpoint_permissions` (`references/identity.md` — list, by-id, and write routes). Mirror the sibling entries in the same resource `data.json`.
- For property-association mutations, authorize **old ∪ new** in OPA (`[ResourceMetadata]` +
  `IPropertyLevelRequestModel` + custom `every` on concat `property_ids`). Do not add an API wrapper
  service for that. PUT bodies are full replace. Details: `references/api-endpoint-patterns.md`.
- Never auto-invoke `setup-new-service`.
- **Linear (manual invocation only):** if `prompt.md` has a Linear id and this is the first manual
  implement pass, ask before `keep-linear-updated` → **In Progress** or assignment. An automated
  `/implement-pipeline` stage never changes Linear or speaks as the user.

State loaded skills/paths and resolved plan path in the output.

## Plan resolution

Accept: explicit paths, `PlanFile:` only, branch name, or current worktree branch → `$ROOT/ai-plans/<branch>/` (highest complete five-file plan; prefer `vN/` if present). Read `product.md`, `implementation.md`, `deferred-scope.md`, and `pipeline.json`; do not read `prompt.md`/the specification transcript. When the full pipeline authored tests first, read `red-proof.md`. If nothing resolves → stop and ask.

The plan folder name is the **target branch**. Do not start coding until the worktree failsafe below passes.

## Branch / worktree failsafe (before any code change)

After plan resolution:

1. Confirm mains on `master`. Never `git switch` feature branches in `$ROOT/apaleo`, `$ROOT/development`, `$ROOT/identity`, `$ROOT/agent-skills`, or `$ROOT/angular-api-proxy`.
2. Ensure `$WT=$ROOT/worktrees/<target>` via **`worktree-start`** if no in-scope feature repo is present or on the wrong branch (existing-branch mode only — never create from master here). Team-plugin-only plans use `$WT/agent-skills` and Angular-client-only plans use `$WT/angular-api-proxy`; neither requires `$WT/apaleo`.
3. **development:** if `pipeline.json` paths or `implementation.md` require development/E2E work → ensure `$WT/development`. Otherwise do not force a worktree; if a new need appears, report a plan defect.
4. **identity:** if `pipeline.json` paths or `implementation.md` require Identity work → ensure `$WT/identity`. Otherwise do not force a worktree; if a new need appears, report a plan defect (`references/identity.md`).
5. **agent-skills:** if `pipeline.json` paths or `implementation.md` require team-plugin work → ensure `$WT/agent-skills`. Otherwise do not force a worktree; never edit the parked `$ROOT/agent-skills` clone.
6. **angular-api-proxy:** if `pipeline.json` paths or `implementation.md` require Angular API client or generator work → ensure `$WT/angular-api-proxy`. Otherwise do not force a worktree; never edit the parked `$ROOT/angular-api-proxy` clone. Regenerate `modules/**` with the canonical flow; never hand-edit generated clients.
6. In `/implement-pipeline`, dirty files matching `pipeline.json.test_paths` are the expected TDD
   handoff from `/implement-tests`; preserve them and continue. Any other pre-existing dirt → stop.
7. **Double-check:** the in-scope worktree(s) are on `<target>`. For product work, `git -C $APALEO branch --show-current` equals `<target>` (and `$DEV` / `$IDENTITY` / `$AGENT_SKILLS` when required). Re-check immediately before the first write in each repo.
8. Cursor: `move_agent_to_root` → `$WT`. Edit only under `$WT/**`. Plans append to `$ROOT/ai-plans/<branch>/progress.md`.
9. Report paths in the output. If a required worktree fails → blocked (questions only); no partial implementation.

## Authority

1. **Existing repo patterns** (`references/existing-patterns.md`) + `$ROOT/AGENTS.md` / nearest `AGENTS.md` — match the cited neighbor
2. User explicit instructions and `clean-code` as applied to that local pattern
3. `implementation.md` — technical execution
4. `product.md` — product intent and AC

If plan docs conflict with each other → stop with minimal numbered questions. If the plan invents a shape the repo does not have, or repo evidence contradicts the plan → explain and get direction before changing scope. Do not “improve” the neighbor.

## Rules

- Implement only in-scope work. No opportunistic refactors.
- API enums: follow the plan `D#` / Contracts table. Default is CLR member names (`references/api-enum-wire-values.md`). Do not invent display-string `JsonConverter`s if the plan is silent — stop and ask.
- **Reuse before create** — search, cite `repo/path:line`, record the search in `progress.md`. A new type needs one line why the existing one does not fit.
- Prefer LSP for symbol questions; say when falling back to text search.
- Cite `repo/path:line` for non-obvious claims (paths relative to repo root inside `$WT`).
- In the simple manual lane, a bugfix regression check must demonstrate the original bad behavior
  before the product fix, then pass afterward. Record that concise before/after evidence in
  `progress.md`. A check that only executes the changed code is not enough. If automation is
  genuinely impractical, the plan must already name why and the strongest repeatable alternative
  (focused API/script check, fixture, or local repro). For other manual work, add or update tests
  before product code where practical. No `red-proof.md` or separate `/implement-tests` handoff is
  needed. In the full pipeline, treat supplied red tests as the independent contract. In both
  lanes, never weaken, skip, delete, quarantine, or loosen an assertion.
- Product/generated files may be edited only within `pipeline.json.allowed_paths`. If implementation
  needs another path, update the complete plan first; do not expand scope silently.
- After product construction, progressively load and execute
  `$ROOT/.claude/skills/test-and-fix/SKILL.md` **inside this same session**. Do not launch another
  agent or top-level stage. Run every `pipeline.json.test_commands` entry and fix plan-authorized
  failures until the deterministic parser is green.
- Use `python3 $ROOT/.claude/skills/pipeline/verification.py <branch> --root "$ROOT" --force` for
  the final pass. It records command output, AC traceability, diff budget, convention/secret scans,
  and optional mutation evidence. A command not executed and parsed is not a pass.
- Localhost E2E, Swagger/proxy generation, and branch-image switching use the E2E stack lock. Always
  restore the prior image/owner in `finally`-style cleanup.
- After each implementation step, append to `$ROOT/ai-plans/<branch>/progress.md`: step #, what changed, files, checks + results, plan mistakes discovered.
- Behind on master? For a manual `/implement`, suggest `/sync-master`; do not merge unattended.
  `/implement-pipeline` performs its own clean-worktree synchronization before this fresh stage.

## Blocked

Output only numbered questions. Stop.

## Automated execution (`/implement-pipeline`)

This stage is selected and therefore required. The plan is expected to contain every decision.
Exhaust safe in-scope work, retries, mechanical corrections, and reversible local recovery. Only
emit `PIPELINE_INPUT_REQUIRED` when progress is impossible without a decision or action solely the
user can provide, followed by the minimum numbered questions. The runner resumes this exact session
after the answer. Never emit `PIPELINE_STAGE_SKIPPED`. Provider retries/fallbacks remain fresh.

If a hard decision is missing, record it in the complete plan set through `/specify` or the active
planning flow. The runner will automatically rebind to that revision; do not rely on a chat-only
answer that later fresh sessions cannot see.
No stage report may introduce a product or architectural decision. Report the missing choice as
`PLAN_DEFECT`; do not record a new `PIPELINE_DECISION`.

## Output contract (complete)

```
Skills loaded: <list>
Plan: <resolved path>
Branch: <target>
Worktree: $ROOT/worktrees/<target>
  apaleo:      ok | started | blocked
  development: ok | started | not required | blocked
Mains: apaleo=master | development=master
Behaviour: <short>
Decisions: <key D# or deviations — none if none>
Built: <bullets mapped to plan sections>
Checks: <command → parsed result + evidence path>
Bugfix: <red evidence → green evidence | n/a>
Traceability: <AC → named test → command → pass>
Next: manual lane complete | <next selected pipeline stage>
```

Do not perform the formal review or write `review-<n>.md` here. If `review` was selected, the runner
starts it in a separate fresh session so it has no implementation-session context or bias.
