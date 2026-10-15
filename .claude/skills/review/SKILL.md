---
name: review
description: >-
  Fresh-context review of a branch/diff against its confirmed plan, tests,
  repository rules, conventions, and semantic reuse/DRY. Pipeline review applies
  safe in-plan improvements; direct review is advisory and plans follow-up.
disable-model-invocation: true
argument-hint: "[branch-name] [focus, e.g. DRY/refactoring/security]"
context: fork
background: false
model: opus
effort: high
---

# Review (fresh, adversarial, two-mode)

Review a diff you did not write. Treat the confirmed specification—not the implementation, its
tests, or a prior agent's explanation—as the source of truth. It always starts in a fresh context
and never commits or pushes. Its behavior depends on how it is invoked:

- **Pipeline review:** apply unambiguous, plan-authorized correctness fixes and same-behavior
  convention/DRY improvements within the manifest paths. Run the narrowest affected named checks,
  record the result, and continue: findings, environment trouble, report defects, and provider
  failures are advisory and never hold up later selected stages.
- **Direct `/review`:** check-only and advisory. It never edits code, tests, generated files, plans,
  or configuration. It writes a report/plan for follow-up and asks for confirmation whenever the
  review basis or solution is ambiguous.

`/review <branch> [focus]` is valid at any time, including after the simple `/specify` →
`/implement` lane. A focus such as `DRY`, `refactoring`, `clean code`, `security`, or a user-supplied
concern narrows the extra inspection; it never replaces the baseline spec, test, correctness, and
rules checks.

## Model gate

For `/implement-pipeline`, use the fresh route recorded in `pipeline.json`. `/specify` offers the
point-based recommendation in `references/model-routing.md`; it is not a gate. A direct manual
review starts a new session and may use any explicitly selected valid route. Never transfer or
resume the implementation session. Read `$ROOT/.claude/skills/references/model-routing.md`.

## Direct review: ambiguity and confirmation gate

Direct invocation is analysis-only, modelled on `/address-pr-comments`:

1. Resolve the branch, diff, and the newest complete plan. The review basis is the confirmed plan,
   current diff, available test output, and the optional focus.
2. If the plan is missing, its acceptance criteria do not cover the changed behavior, the requested
   focus changes product behavior/scope, or two sound interpretations remain, do **not** guess or
   review as if one were correct. Explain the ambiguity with code/plan evidence, offer concise
   numbered options with a recommendation, and stop for confirmation.
3. After confirmation, use `/specify` to create or revise the complete plan when behavior, scope,
   architecture, contract, or tests change. Then use `/implement` (or the selected pipeline stage)
   to make the confirmed change. `/review` itself remains check-only on both the first pass and any
   follow-up.

Do not ask questions when repository evidence and the confirmed plan settle the matter. Never treat
"go ahead" as approval for an unstated behavioral choice.

## Fresh-context preflight

1. Load only the newest complete `product.md`, `implementation.md`, `deferred-scope.md`, and
   `pipeline.json` from `$ROOT/ai-plans/<branch>/`. Do not read `prompt.md`, `progress.md`, test or
   implementation stage reports, recovery packets, provider output, or prior-agent rationale.
2. Load root `AGENTS.md`, the nearest repository `AGENTS.md` / `CLAUDE.md`, every path-scoped
   `.claude/rules/*.md` covering a changed file, and the full `/add-rule` inventory:
   `.claude/conventions/registry.json`, its referenced rule metadata, and `allowlist.json`. In a
   pipeline run that inventory is supplied in the review prompt; confirm it still matches the
   files on disk. Tier 1 rules are blocking and must be repaired in pipeline mode; Tier 2 matches
   require a concrete applicability/false-positive assessment; Tier 3 statements require a
   semantic inspection of the affected responsibility.
3. Read `references/worktrees.md`; work only in `$ROOT/worktrees/<branch>/`. Confirm parked mains
   remain on `master`. Review uncommitted implementation work as well as `origin/master...HEAD`.
4. Read available named-test output and test files. Do not treat passing tests as proof of behavior;
   they are evidence for the test-gap pass. Never rerun destructive shared-environment tests.
5. For changed C# symbols, use Graphify per `references/graphify.md` before broad search when
   available. For direct review without deterministic scan evidence, run the read-only command:

   ```bash
   python3 "$ROOT/.claude/skills/pipeline/verification.py" <branch> --root "$ROOT" --precommit
   ```

## Review order

Complete each section in order. If it has findings, record them, then continue only when doing so
adds useful independent evidence; do not turn the review into a style sweep.

### 1. Specification violations

Assume the author misunderstood the specification until the diff proves otherwise. Map every AC to
`Satisfied`, `Not satisfied`, or `Not verifiable`, with `repo/path:line` evidence. Flag behavior the
diff adds without plan support and behavior an AC requires but the diff omits. Respect real deferred
scope only when `references/deferred-scope.md` proves it is absent-not-wrong, outside the ACs, and
owned by a named later ticket/plan line. Never defer tenancy/property authorization, money/tax,
data loss, migration safety, public contract breakage, secrets, or an AC-path crash.

### 2. Test gaps

For every AC, identify the behavioral test that proves it and its observed output. Flag missing
coverage, tests that only prove an implementation detail, and tests that do not exercise meaningful
negative/error paths. Tests are not the definition of correctness.

### 3. Correctness

Inspect null/empty/boundary behavior; async/cancellation; transactions and partial failures;
idempotency/concurrency; authorization, tenancy, and property scoping; money/time/locale; migration
safety; public-contract compatibility; and changed endpoint `endpoint_permissions` registration.

### 4. Rules, conventions, and semantic reuse/DRY

Check every changed file against loaded instructions, focused references, and
`.claude/conventions/registry.json` plus its metadata and exact allowlist. Audit every added responsibility (type, helper, validator,
mapper, query, authorization check, fixture, or non-trivial block) against the relevant repository
using targeted `rg`/Graphify. Look for an established owner or simpler same-behavior approach; do
not require speculative abstractions or raise style opinions unsupported by a rule. Apply the
optional focus here as additional scrutiny.

For pipeline review, run the deterministic scan after the final repair (and before declaring
completion):

```bash
python3 "$ROOT/.claude/skills/pipeline/verification.py" <branch> --root "$ROOT" --precommit
```

It is the enforcement check for Tier 1 rules and secrets; a Tier 1 finding must be fixed within
the approved paths, not reported as advisory. Tier 2 warnings remain advisory only after the
review records why the match is acceptable or why it was refactored away. The runner repeats this
scan after the stage, so a report cannot substitute for actual compliance.

## Evidence and output

- Do not comment on formatting, naming, or generic style.
- In direct mode, do not propose fixes or write code. State only the problem, the violated AC/rule
  where relevant, and a concrete failure scenario. When a solution choice is needed, provide
  decision options rather than an unconfirmed implementation plan.
- In pipeline mode, repair only the unambiguous plan-authorized finding after the full finding pass;
  do not make a new product/architecture decision, expand scope, or treat a refactor as license to
  change behavior. Run the narrowest affected named checks after each repair. Record `Fixed` with
  file:line, verification command, and output. Limit repair/verify cycles to three; record any
  remaining finding as advisory and continue rather than pausing delivery.
- Every finding has an ID, severity, section, `repo/path:line`, and concrete failure scenario.
  Discard unsupported suspicions.
- Write `none` for a section with no findings. Record all ACs and the strongest convention/DRY
  searches, even when clean.

Write `$ROOT/ai-plans/<branch>/review-<n>.md` when a plan exists; never overwrite a prior report.
Include:

```text
New product/architectural decisions: none
Convention compliance: passed|fixed|findings — <loaded instruction sources and deterministic scan evidence>
Reuse/DRY audit: passed|fixed|findings — <repository searches and strongest matching paths>
```

The convention declaration must name the applicable scoped rule files and registry rule IDs (or
`none`), then include the final `--precommit` result. For every repaired rule/DRY finding, list
the before/after responsibility and the narrow verification command. Do not claim a rule was
checked merely because an earlier implementation scan passed.

Finish with `Advisory — <finding IDs or none>; next: <review complete | /specify for a confirmed
revision | /implement after plan confirmation>`. Never commit or push. Direct review never changes
the diff; pipeline review may make only the recorded plan-authorized changes and never blocks a
pipeline stage.

## Automated execution (`/implement-pipeline`)

- Start a fresh provider session. The only shared material is the confirmed plan, current worktree,
  tests/test evidence, applicable rules, the `/add-rule` convention inventory, and git diff. Apply
  safe in-plan corrections and same-behavior improvements; verify narrowly after each change and
  run the final deterministic convention scan. Tier-1 convention compliance is required; only
  findings that need a new plan/product decision remain advisory.
- Do not ask the user to resolve a plan defect during the autonomous review stage; record it in the
  report as advisory and allow the runner to continue.
- Always write `review-<n>.md` when possible. Missing reports, incomplete audit evidence, provider
  failure, and environment failure are advisory. Never emit `PIPELINE_STAGE_SKIPPED`.
