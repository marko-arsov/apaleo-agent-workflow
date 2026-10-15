---
name: e2e-test-overview
description: >-
  Explains all Jest E2E scenarios added by an Apaleo feature branch in clear,
  product-focused language, then recommends evidence-backed coverage additions.
  Use to understand E2E coverage before deciding which additional tests to implement.
disable-model-invocation: true
model: sonnet
effort: medium
argument-hint: "[branch | HC-#### | PR URL | #PR]"
---

# E2E test overview

Give a fast, read-only explanation of the E2E coverage introduced by a feature branch. The
reader should understand what the tests prove without needing to read TypeScript. Do **not** write,
edit, run, or commit tests in this skill. After the recommendations, wait for the user to select
what to implement; use `/e2e-test-engineering-development` for that later work.

Read first:

- `$ROOT/AGENTS.md`
- `$ROOT/.claude/skills/references/worktrees.md`
- `$ROOT/.claude/skills/references/e2e-development.md`
- `$ROOT/.claude/skills/references/identity.md` only when the changed flow has authorization,
  role, or permission-catalog behaviour

## Model gate

Preferred host: **Cursor Grok** — `e2e-test-overview-cursor` (model per
`references/model-routing.md`). Do not hand off to Claude Code or use Cursor on-demand Claude.

## Scope and branch resolution

Accept a full branch, HC shorthand, PR URL, `#PR`, or an explicit development PR. Resolve it with
`resolve_feature_branch` from `$ROOT/.claude/skills/pipeline/root.sh`. If it is ambiguous, stop
and ask for the full branch name.

Fetch `development` and `apaleo` with `git fetch --prune origin`; do not pull, switch branches, or
create a worktree. Resolve the head ref in each repo, preferring `origin/<branch>` and then the
local `<branch>` ref. Compare each available ref using the merge-base-aware range:

```bash
git -C <repo> diff --stat origin/master...<head>
git -C <repo> diff --no-ext-diff --no-renames --unified=80 origin/master...<head> -- <paths>
```

`development` is required. If the branch has no development ref, report that no E2E branch was
found and stop; do not infer tests from an apaleo-only change. Use the apaleo diff when available
only to judge whether the E2E scenarios cover the changed product behaviour.

## What counts as an added test

Inspect `development/src/tests/**/*.ts` in the diff and the surrounding complete specs. Count a
scenario only when its Jest declaration (`it`, `test`, or their focused/skipped variants) was
introduced by the branch. A new spec file contributes each scenario it contains. Do not mistake
new setup, assertions inside an existing scenario, renamed files, comments, or helper code for a
new test.

Also report, separately and briefly:

- **Changed existing tests** — existing scenarios whose setup or assertions changed.
- **E2E support changes** — relevant helpers, builders, fixtures, config, or generated proxy
  changes. Never describe generated proxy churn as coverage.

Read each added scenario, its enclosing `describe`, and only the helper/production code needed to
state the tested behaviour accurately. Do not run Jest: this is an overview, not verification.

## Coverage assessment

Build recommendations from concrete branch evidence: changed API behaviour, validation branches,
authorization boundaries, data states, and error handling in the apaleo diff, plus what the added
E2E scenarios already assert. Recommend a test only when it would cover a meaningful uncovered
outcome. Do not pad the report with a generic checklist or recommend tests already covered by the
same scenario.

Rank recommendations:

- **Recommended** — an important behaviour or risk shown by the branch is not E2E-covered.
- **Optional** — a useful edge case with lower user or regression impact.

For each, give a minimal scenario, why it matters, and the exact changed file/symbol that supports
the recommendation. Clearly label inferences as such. If the apaleo branch is unavailable, say
that recommendations are limited to evidence in `development`.

## Output

Keep the prose concise and non-technical first; paths remain available for a developer who wants
to inspect details.

```text
Branch: <branch>
Compared: development origin/master...<head>; apaleo <range|not found>
E2E coverage: <n> scenarios added in <n> spec files; <n> existing scenarios changed.

## What this branch now tests
| Area | Scenario | What it proves | Location |
|---|---|---|---|

## Supporting E2E changes
<only if present; short bullets>

## Coverage to consider next
1. Recommended — <short test name>
   - Scenario: <minimal setup → expected outcome>
   - Why: <concrete risk or behaviour>
   - Evidence: <path:symbol or line>

2. Optional — ...

## Bottom line
<two short sentences: strongest covered behaviour and the main remaining risk.>

Which numbered recommendations should I implement? I will wait for your selection.
```

If no scenarios were added, say so plainly, list only relevant changed test/support files, and
assess coverage from the product diff if available. Never claim a test has passed unless the user
asked to run it and it was actually executed under the E2E stack-lock rules.

