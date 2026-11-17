---
name: review
description: >-
  Fresh-context code review of a feature branch, done like a strong PR reviewer. Tier 1 hunts
  bugs, security/tenancy holes, and performance problems; Tier 2 enforces repository rules and
  polishes the diff into clean, DRY, neighbour-consistent code. Pipeline review fixes what it
  verifies; direct /review reports first and applies what the user picks.
disable-model-invocation: true
argument-hint: "[branch-name] [bugs|polish] [focus, e.g. security/performance/DRY]"
context: fork
background: false
model: opus
effort: high
---

# Review

Review a diff you did not write the way the best reviewer on the team would: first find what
will break in production, then leave the code cleaner than the author did. Every finding is
verified. If you cannot back a Tier 1 finding with a concrete failure scenario, or a Tier 2 change
with a rule or neighbour citation, drop it. Never commit or push.

| Mode | Edits | Ends with |
|---|---|---|
| Pipeline (`/implement-pipeline`) | Fixes verified findings and polishes within manifest paths | `review-<n>.md`, then `PIPELINE_STAGE_OK: review` |
| Direct `/review [branch] [bugs\|polish] [focus]` | None until the user picks | `review-<n>.md` and a numbered list of findings to apply |

`bugs` runs Tier 1 only and `polish` runs Tier 2 only; the default is both. A focus adds scrutiny
to its area and never replaces Tier 1.

## Model gate

Pipeline: use the fresh route in `pipeline.json`. Direct: any valid route, always a new session —
never the implementation session. See `$ROOT/.claude/skills/references/model-routing.md`.

## Cursor chat title

On Cursor, rename this chat once the branch is known. Status `review`, then `waiting` or `done`.
Follow `references/cursor-chat-title.md`.

## Setup

1. Resolve the branch and `$WT=$ROOT/worktrees/<branch>/` per `references/worktrees.md`. Parked
   mains stay on `master`.
2. The diff is `origin/<base>...HEAD` plus uncommitted changes in every in-scope repo. `base` is
   `pipeline.json.base_branch`, else `master`.
3. Read the newest plan's `product.md` and `pipeline.json` (`allowed_paths`, `test_paths`,
   `test_commands`). Read `implementation.md` or `deferred-scope.md` only when a finding depends on
   intent or scope. Do not read `prompt.md`, `progress.md`, stage reports, or provider output:
   your independence from the author is the point. Do read `api-samples.md` and `ui/` when they
   exist: they are recorded output, not rationale. Without a plan, review against the PR or commit
   intent and say so.
4. Read every changed file in full, not only the hunk. For each changed public member, find its
   callers (Graphify per `references/graphify.md`, else `rg`).
5. Check test edits made after the test stage. The pipeline prompt lists them with a diff command
   for each. In direct mode, take the `implement-tests` SHAs from
   `$ROOT/ai-plans/<branch>/stage-commits.json` when that file exists, and diff `test_paths` against
   them. The runner already restores skips, removed tests, and changed assertions. You judge what a
   pattern cannot: changed inputs, mock returns, fixtures, or expected values moved into helpers
   or constants. An edit that makes a test easier to pass is a High finding; in the pipeline,
   restore the original lines.

## Tier 1 — bugs, security, performance

Hunt through the diff with each lens. When your host can start subagents, give each lens to its
own subagent with the diff and plan, then merge and verify their candidates yourself.

**Security and authorization**
- Every new or changed route has `[Scope]`/OPA and a matching `endpoint_permissions` entry, list
  and GET included. Permission keys follow the sibling naming (`.read`/`.manage`).
- Property-level request models implement `IPropertyLevelRequestModel`, PUT included. Writes
  authorize old ∪ new property ids. Property ids never come from a PATCH body. `[null]`, empty,
  archived, deleted, and orphaned property ids are rejected or filtered.
- Account data is filtered by `AccountCode` via `IScopeContext`. Nothing returns ids from another
  account, or from properties the caller cannot see.
- The default `core/decision` is reused unless it would be wrong; no near-duplicate rego files.
- New input is validated. No interpolated raw SQL. No secrets or guest PII in logs or errors.

**Logic and data**
- Null, empty, and default values; enum defaults; off-by-one errors; inclusive vs exclusive
  ranges; `LocalDate` arithmetic, time zones, DST; `TimeRange.IsPrimarilyWithin` vs `Overlaps`.
- Every field travels through request → model → entity → response on create, PUT (full
  replace), PATCH, fork/copy, and audit paths. Owned or JSON values are not cleared or replaced
  by accident on update.
- Money uses `decimal` with `IsoCurrency`, is rounded at the established step, and has its
  column precision mapped.
- Errors: the right status code in the neighbour's order (for example 404 before 422/501).
  Helpers do not throw on deleted or archived referenced entities in list or GET.
- Feature flags use the right key, and both the on and off paths behave.
- Transactions and partial failure, idempotency, check-then-act races, and copy-paste slips
  (wrong variable, id, or sibling).

**Performance and reliability**
- No queries or OPA, feature-flag, or settings calls inside loops. The same data is not fetched
  twice, recurrences are not re-expanded per item, and lookups are not O(n²).
- No loading whole aggregates or tables to use one field, no `ToList` before filtering, list
  endpoints are paged or bounded, reads use `AsNoTracking`, and new filters or sorts have an index.
- `CancellationToken` is propagated. No `.Result`, `.Wait()`, `async void`, or swallowed exceptions.

**Contract, migrations, intent**
- Behaviour that contradicts or omits a `product.md` acceptance criterion.
- Public v1 contract, machine-readable enum wire values, nullability, status codes, and Swagger
  text that matches the behaviour. Regenerated Swagger or proxies contain only this branch's changes.
- Migrations: entity nullability matches the column, unique indexes handle NULLs, decimal
  precision is set, backfills are idempotent, and the change is deploy-ahead safe
  (`references/db-migrations.md`).
- Tests that would pass on the wrong behaviour: a `not 403` assertion that also passes on 400 or
  500, or an expected status that contradicts the plan.
- `api-samples.md`: the real responses match the Examples and the Swagger (enum wire values, date
  formats, null vs missing fields, status codes, field names).

**Host accelerators (optional).** If your host has a native diff reviewer, run it from each
changed repo against the base and add its output to your candidate list. Examples: Claude Code's
bundled `/code-review` (at `high`, without `--fix` or `--comment`) and `/security-review`, or
Codex `/review`. Skip it quietly when it is unavailable. It never replaces the lenses above or the
verification below.

### Verify, then fix

For each candidate:

1. Write the failure scenario: input or state → `repo/path:line` → wrong outcome. If you cannot
   write one, drop the candidate.
2. Prove it. For behaviour, prefer a new failing test or test case in a `test_paths` file; never
   edit an existing assertion. For performance or code paths you cannot test cheaply, trace the
   exact path with a citation for each step.
3. Rate it. **High**: security or tenancy leak, wrong money or persisted data, data loss, a crash or
   5xx on a supported path, or a broken public contract or migration. **Medium**: wrong behaviour on
   an edge path, a real performance problem at production volume, or a test that cannot catch its
   own regression. **Low**: anything else worth changing.
4. Pipeline: fix it the smallest way that matches the neighbour pattern, within `allowed_paths` and
   `test_paths`. Rerun the proving test and the narrowest relevant `test_commands` entry. If a fix
   still fails after three attempts, revert it. Items that are genuinely deferred under
   `references/deferred-scope.md` are recorded, not fixed; its veto list is never deferred.

Pause for the user only when a **High** finding truly cannot be fixed: the right behaviour is a
product choice the plan does not settle, the fix needs a path outside the manifest, or three
verified attempts failed. Finish everything else in both tiers first, write the report, then end
with `PIPELINE_INPUT_REQUIRED` and numbered options, recommendation first. The runner resumes this
session with the answer. Any other unfixed finding goes under **Open** and the run continues.

## Test strength

After the Tier 1 fixes, run the targeted mutation check in
`$ROOT/.claude/skills/references/test-strength.md`. Take 3–5 plausible wrong implementations from
the diff (the fallback source, the rejected alternative, a dropped branch, a skipped flag or
permission check), apply them one at a time, and confirm a test fails. For every mutant that
survives, add a hardening test with data that separates the right code from the mutant, and record
it as a fix. Prefer unit-level checks; at most two mutants may use E2E under the stack lock. In
direct mode, list the surviving mutants and proposed tests under **Open** instead.

## Tier 2 — rules and polish

Run Tier 2 after the Tier 1 fixes, so you polish the final code. Load `clean-code`, the scoped
`.claude/rules/*.md` for the changed paths, and the `/add-rule` registry (the pipeline prompt
carries this inventory). Then make the changes this team's reviewers ask for most, in this order:

1. **Reuse before you write.** If an existing service, validator, helper, builder, or policy already
   does the job, call it. Examples: the create service for a fork, the default OPA decision instead
   of a new rego override, one policy instead of three near-identical files, a shared test helper
   instead of copied mock setup. Search (`rg`/Graphify) before accepting any new responsibility.
2. **Simplify expressions and allocations.** No nested ternaries. Compose predicates. Make one call
   where Exists-then-Get makes two. Don't create objects only to discard them. Size lists when the
   count is known, pass `[]`, and prefer a generic method over a loop with casts.
3. **Match the neighbour.** File-scoped namespaces, primary constructors with `Check.NotNull`,
   `Check.NotNull` instead of ad-hoc throws, `nameof`, and the sibling action's layering and
   `data.json` naming.
4. **Put responsibilities where they belong.** One response creator per response shape. Extract a
   cohesive type (an index or scope) once a service grows its logic. Use a command or parameter
   record for three or more primitives. Models never depend on services.
5. **Comments.** Delete comments that restate the code, ticket or acceptance-criterion ids, and stale
   red-phase notes. Keep only the "why".
6. **Tests.** In existing test files, polish only setup, helpers, and names (for example a shared
   helper instead of copied mock setup). Never change an assertion, a test declaration, or a skip
   marker there: the runner restores the whole file from the implement-tests commit if you do.
   Report weak tests under **Open** instead: a spec that re-tests another spec's concern, or one value
   reused across fields so that a swapped mapping still passes.
7. **Names and magic values.** Use domain words, and named constants for bounds.
8. **Leftovers.** Remove unused usings, parameters, and variables, dead code, debug output, and stray
   files (`.gitignore`, unrelated generated churn).

Boundaries:
- Keep behaviour the same. Polish only lines the branch adds or changes, plus the helper you extract
  or reuse to remove a duplication. Reviewers flag convention edits on untouched lines as scope
  creep. No public contract renames, and no abstraction with a single use.
- Prefer the established neighbour's shape over your own taste, and cite it.
- Tier 1 registry rules must end clean. Judge Tier 2 and Tier 3 matches case by case.
- Afterwards, run the affected unit and integration `test_commands` once (E2E only within the
  test-strength exception), then the scan below. Revert any polish whose checks fail instead of
  debugging it.

```bash
python3 "$ROOT/.claude/skills/pipeline/verification.py" <branch> --root "$ROOT" --precommit
```

Claude Code's bundled `/simplify` may propose polish. Inspect its edits as if they were your own,
and revert anything outside these boundaries.

## Report

Write `$ROOT/ai-plans/<branch>/review-<n>.md` using the next free `n`. Keep it short:

```markdown
# Review <n> — <branch>

New product/architectural decisions: none

## Fixed
| ID | Sev | Area | Where | Problem → fix | Proof |

## Test strength
| Mutant | Where | Result |

## Polished
- <change> — `repo/path:line` (rule id or neighbour `repo/path:line`)

## Open
| ID | Sev | Where | Problem and failure scenario | Why not fixed |

## Checks
- `<command>` → <result>

Convention compliance: passed|fixed|findings — <scoped rule files and registry ids applied; final --precommit result>
Reuse/DRY audit: passed|fixed|findings — <the rg/Graphify searches behind the strongest reuse decision>
```

Write `none` under an empty heading. Leave out acceptance-criterion matrices, lists of loaded
files, and suggested next stages.

**Direct mode** writes the same report, but every finding goes under **Open** with a concrete
proposed fix and a stable number, and polish appears as proposals. End by listing the numbers and
asking which to apply (`1,3`, `all`, or `none`). Whichever session receives the answer applies
exactly those fixes, runs the narrow checks, and appends `## Applied` to the same report. Ask
first, as decision options, when a fix needs a product or behaviour choice.

## Never

- Skip, delete, quarantine, or loosen a test or assertion. The runner restores such edits from the
  implement-tests commit.
- Comment on formatting, or on style that no rule or neighbour backs.
- Make a new product or architecture decision; ask instead.
- Commit, push, or run destructive shared-environment tests. Switch E2E images only for the two
  E2E mutants that the test-strength check allows, under the stack lock, and restore the prior
  image afterwards.
- Leave a mutant in the code. `git diff` shows none before you finish.
- Emit `PIPELINE_STAGE_SKIPPED`.
