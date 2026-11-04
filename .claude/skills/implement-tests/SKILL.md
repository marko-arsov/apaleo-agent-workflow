---
name: implement-tests
description: >-
  Implements the complete plan-specified test suite before product code, with
  E2E coverage as the priority and a recorded TDD red phase. Use only after
  /specify has written pipeline.json and before /implement.
disable-model-invocation: true
argument-hint: "[branch-name]"
context: fork
background: false
model: opus
effort: high
---

# Implement tests

Implement every test required by the confirmed plan before any product implementation. This is
the TDD red stage. It runs in a fresh session and must not share an agent session with `/implement`.

## Model gate

**Default route:** Cursor Claude Sonnet 5.5 high (`claude-sonnet-5-5-high`). With a current
catalogue, `/specify` records Sonnet 5.5 medium for an ordinary suite and Cursor Opus 5.5 high
for four or more planned test files or a substantial expected diff (300+ lines), including one
large test file. The matching Claude Code model is the first fallback. Any valid
provider/model route may be shared with implementation and review when confirmed in `pipeline.json`
or supplied as an explicit `/implement-pipeline --route` override; diversity is a suggestion, never a gate.

## Load

1. `$ROOT/AGENTS.md`
2. The branch's `product.md`, `implementation.md`, and `pipeline.json`
3. `$ROOT/.claude/skills/references/worktrees.md`
4. `e2e-test-engineering-development` before any `e2e/` edit, and before any `development/` edit (payment)
5. The existing test neighbors cited by the plan

Do not read `prompt.md`, product source paths named by `allowed_paths`, recovery packets, or prior
implementation attempts. The harness supplies the current complete plan and test conventions.

Resolve the branch and worktrees exactly as `/implement` does. Parked mains remain on `master`.

## Test-only boundary

- Change only paths listed in `pipeline.json.test_paths`.
- Do not edit application code, generated production clients/contracts, migrations, or runtime configuration.
- E2E scenarios are the priority. Also add unit, policy, integration, contract, or regression tests explicitly required by the plan.
- Implement every acceptance-criterion row and every exact E2E scenario/command from the plan. Do not leave test design to `/implement`.
- Reuse existing fixtures and helpers before creating new ones. A test helper still must live under an approved `test_paths` glob.
- Never weaken, skip, quarantine, comment out, or loosen an assertion.

If an essential test requires a path missing from `test_paths`, stop with numbered questions. Do
not silently expand the plan.

## Red phase

When any acceptance criterion has `red_required: true`, run the narrowest useful checks that prove
those tests are discovered and fail for the intended missing product behavior. For localhost E2E,
acquire the FIFO stack lock from `references/e2e-stack.md`; never run against staging or production.
An expected product failure is success for this stage. Compilation, type-check, missing-symbol,
syntax, fixture, import, environmental, and unrelated failures are not valid red. A `red_required`
test must be discovered and reach an assertion/status comparison that fails specifically because
the planned behavior is absent.

When every criterion has `red_required: false` because the tests name product types, members, or
generated-client fields that do not exist yet, do not force an assertion failure and do not edit
`red_required`. Write the tests, record `Failure level: none`, and name the missing members in
words. Do not paste compiler or type-check output. Assertion-level evidence for those criteria, when
the plan still wants it, belongs to `implement` after the skeleton exists.

### Speed and local-E2E discipline

- Author the complete test suite first; then run each plan-named command once to collect the red
  evidence. Do not rerun a command that already produced valid current assertion-level red unless a
  later test edit invalidated that evidence.
- Acquire the local E2E lock once for the final E2E evidence pass and release it immediately after.
  Do not perform broad stack archaeology, control-spec investigations, service trimming, or
  background Docker probes inside this stage. Those actions belong to the runner's bounded recovery
  path, not a test-authoring session.
- Every Docker command must have an explicit finite timeout. If a required E2E command is unhealthy,
  use the established lock-preserving recovery once, then rerun only the affected command. Record a
  remaining environmental failure with its exact evidence; never spend the stage repeatedly
  diagnosing unrelated services.
- Missing planned product symbols are expected before `/implement`. Record that boundary precisely;
  do not repeatedly clean/rebuild test projects solely to rediscover the same missing symbols.

Write `$ROOT/ai-plans/<branch>/red-proof.md`. For every new or changed test, record:

- acceptance criterion and scenario;
- files changed, each cited as a `$ROOT`-relative path in backticks
  (`` `apaleo/e2e/tests/...` ``, `` `apaleo/test/...` ``, `` `identity/e2e/tests/...` ``,
  `` `development/src/tests/payment/...` ``). Do not list
  repo-relative leftovers such as `` `test/...` `` under an `apaleo:` heading —
  the runner greps for the workspace-relative string;
- command actually run;
- discovered test count, or why discovery cannot run yet;
- `Failure level: assertion` when any criterion is `red_required`, otherwise `Failure level: none`;
- for assertion-level red: the exact failing assertion/status, its output, and why product
  implementation should make it green;
- checks not run and the concrete reason.

Write a new `$ROOT/ai-plans/<branch>/tests-implementation-<n>.md`; never overwrite an earlier report.
Include the exact line `New product/architectural decisions: none`.
Append one concise entry to `progress.md`. Do not commit or push.

Before success, run:

```bash
python3 "$ROOT/.claude/skills/pipeline/verification.py" <branch> --root "$ROOT" --red-proof
```

Record any newly discovered decision in the complete plan set so a later run can rebind to it; do
not block solely because the plan was revised during this task.

## Complete

End headless execution with exactly:

```text
PIPELINE_STAGE_OK: implement-tests
```

Exhaust test-only fixes and established-pattern research first. If progress is truly impossible
without user input, end with `PIPELINE_INPUT_REQUIRED` and the minimum numbered questions; the
runner resumes this exact session after the answer. Never emit `PIPELINE_STAGE_SKIPPED`.
