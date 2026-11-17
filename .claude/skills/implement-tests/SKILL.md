---
name: implement-tests
description: >-
  TDD red stage. Writes the plan's complete test suite before any product code (E2E first, plus
  the unit/policy tests the plan names), designs each test to catch wrong implementations, and
  proves the new tests fail for the missing behaviour. Use only after /specify has written
  pipeline.json and before /implement.
disable-model-invocation: true
argument-hint: "[branch-name]"
context: fork
background: false
model: opus
effort: high
---

# Implement tests

Write the tests that define "done" for this branch, before the product code exists. You are the
independent author of the contract `/implement` must satisfy, so write tests a sceptical reviewer
would trust, not tests that are easy to pass. This runs in a fresh session and never shares one
with `/implement`.

## Model gate

Use the route confirmed in `pipeline.json`. The default is Cursor Claude Sonnet 5.5; `/specify`
records Opus for four or more test files or roughly 300+ changed lines. Details:
`$ROOT/.claude/skills/references/model-routing.md`.

## Load

1. `$ROOT/AGENTS.md`, the branch's `product.md`, `implementation.md`, and `pipeline.json`, and
   `references/worktrees.md`. Resolve the branch and worktrees the way `/implement` does; parked
   mains stay on `master`.
2. `e2e-test-engineering-development` before any edit under `e2e/` or `development/`.
3. The test neighbours the plan cites under `## Read first`. Copy their structure, builders, and
   helpers. `product.md` `## Examples` hold the expected values. `implementation.md` `## Tests`
   names each file, the literal test name the acceptance check searches for, and the command; use
   those names verbatim.
4. On Cursor, `references/cursor-chat-title.md`; rename this chat as a stage session with status
   `implement-tests`.

You may read the signatures, constructors, and models of existing product types your tests must
call or mock, so the tests compile on the first try. Do not read method bodies under change,
`prompt.md`, recovery packets, or earlier implementation attempts. Never derive an expected value
from production code: expected values come from the plan.

## Boundary

- Change only `pipeline.json.test_paths`, test helpers included. No product code, generated
  clients or contracts, migrations, or runtime configuration. If an essential test needs another
  path, stop with numbered questions.
- Implement every acceptance criterion and every exact E2E scenario and command in the plan.
  `/implement` does not design tests.
- E2E comes first for externally visible behaviour. Add the unit, policy, integration, or
  contract tests the plan names.
- Never skip, quarantine, comment out, or loosen an assertion.

## Write tests that catch wrong implementations

Before writing each test, ask: *which plausible wrong implementation would still pass this?*
Then close that gap.

- Assert observable behaviour with exact values from the plan: status code, response fields,
  persisted state, audit entries. A `not 403`, `toBeDefined`, or `NotNull` check is never the only
  assertion, because it also passes on 400 or 500. The expected status must match `product.md`.
- Choose data that separates the right source from every plausible wrong one. When a value can
  come from several places (stored per-night rate, flat block rate, rate-plan price, fallback), give
  each a different number, so pricing from the wrong source changes the result. Use distinct
  values per field and entity (distinct dates, ids) so a swapped or dropped mapping fails.
- Assert the specific effect, not only a total that might coincide: for example, the surcharge
  itself as well as the final price.
- Cover the edges that the plan or an established neighbour already settles: missing permission
  or another property's resource, not found, validation errors, empty or null input, boundary
  dates and ranges, feature flag off, and a repeated call. These are extra tests, not
  `red_required`. Do not invent an outcome the plan leaves open; list that edge under
  `Unspecified edges` in the report so review sees it.
- One behaviour per test, named for that behaviour. Arrange/Act/Assert. Reuse builders and
  helpers. Use independent data per test, poll helpers instead of sleeps, and mocks only at
  boundaries. No ticket or criterion ids in comments.

## Red phase

- Write the whole suite first, then run each command the plan names once.
- `red_required: true`: the test must be discovered and fail at an assertion or status
  comparison, specifically because the planned behaviour is absent. Compile, type, import,
  fixture, environment, and unrelated failures are not red.
- When every criterion is `red_required: false` because the tests use planned members that do not
  exist yet, do not force a failure and do not edit `red_required`. Write `Failure level: none`
  and name the missing members in words. `/implement` records the assertion-level red once its
  skeleton compiles.
- Local E2E: take the stack lock from `references/e2e-stack.md` once for the final evidence pass
  and release it right afterwards. Give every Docker command a finite timeout. Use the
  lock-preserving recovery once, then record any remaining environmental failure with its
  evidence. No stack archaeology, and never run against staging or production.

## Reports

`$ROOT/ai-plans/<branch>/red-proof.md`, for each new or changed test:
- the criterion and scenario;
- the file as a `$ROOT`-relative path in backticks: `` `apaleo/e2e/tests/...` ``,
  `` `apaleo/test/...` ``, `` `identity/e2e/tests/...` ``, `` `development/src/tests/payment/...` ``.
  The runner greps for exactly this form;
- the command run, and the discovered test count or why discovery cannot run yet;
- `Failure level: assertion` (any `red_required` criterion) or `Failure level: none`;
- for assertion-level red, the failing assertion or status output and why the product change
  should turn it green;
- checks not run, with the reason. Never paste compiler or type-check output.

Also write a new `tests-implementation-<n>.md` (never overwrite an earlier one) with the files
changed, criterion → tests, `Unspecified edges`, and the exact line
`New product/architectural decisions: none`. Append one entry to `progress.md`. Do not commit or
push.

Before finishing, run:

```bash
python3 "$ROOT/.claude/skills/pipeline/verification.py" <branch> --root "$ROOT" --red-proof
```

## Complete

End with exactly `PIPELINE_STAGE_OK: implement-tests`. Only when progress is impossible without the
user, end with `PIPELINE_INPUT_REQUIRED` and the minimum numbered questions; the runner resumes this
session. Never emit `PIPELINE_STAGE_SKIPPED`.
