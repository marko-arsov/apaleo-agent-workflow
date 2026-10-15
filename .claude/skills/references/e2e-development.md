---
name: e2e-test-engineering-development
description: >-
  Local specialization of Apaleo's e2e-test-engineering for the apaleo/development
  Jest suite: concrete paths, commands, auth, Docker localhost targeting, and
  cross-repo branch rules. Use when writing or modifying E2E specs under
  development/, when implement/test-and-fix touch development, or on
  /e2e-test-engineering-development. Prefer this over upstream e2e-test-engineering
  for this workspace. Not for apaleo xUnit tests.
argument-hint: "[test directory under src/tests] [task]"
---

# E2E Test Generation — development specialization

> Arguments: $ARGUMENTS
> Upstream process skill: `e2e-test-engineering@apaleo` (keep structure/voice). See `references/UPSTREAM.md`.

Create or modify end-to-end tests in **`development/`** while preserving nearby conventions.

Read the argument as the test suite directory (under `src/tests/…`) plus the task. That directory tree is the primary search scope. If either is missing, ask before searching.

## Modes

**Generate** (default) — Discovery, then TDD workflow.

**Review-only** — Discovery, then report departures from the convention table. Do not rewrite unless asked.

---

# Local facts (specialization — read first)

These replace generic “discover the runner” guesses for this repo. Still run Discovery for *nearby* style.

| Fact | Value |
|---|---|
| Repo | `$ROOT/development` |
| Runner | Jest **27** + ts-jest; TypeScript 4.x; Node **20**; Yarn lockfile |
| Specs | `src/tests/<domain>/**/*-spec.ts` (kebab-case `*-spec.ts`) |
| Helpers | `src/lib/helpers/builders/*`, `ensureCreatedFactories/*`, domain helpers |
| Proxies | `src/proxy/*-nsfw/` — generated; do not hand-edit |
| Cursor rules | `.cursor/rules/{testing-patterns,api-testing,code-style}.mdc` |
| Full suite | `npm test` — **never run locally** |
| One file | `npm run test:file -- ./src/tests/core/<area>/<file>-spec.ts` |
| CI gate (apaleo Jenkins) | `npm run test:core` |
| Auth | `APALEO_TEST_CREDENTIALS=RANDOM` → `ensureNewAccountCreated(__filename)` |
| Default env | **localhost / Docker Compose** |
| Shared envs | staging/production scripts exist — **confirm before use; never unattended** |
| Per-test timeout | 10 minutes (`setupTestFramework.ts`) |
| Cross-repo | Same branch name as `apaleo` when specs/helpers/proxies change. Same name as `identity` when permission catalog / role mapping changes (`references/identity.md`) |
| API under test | Prefer locally built `apaleo-ui-api:wt-<slug>` (see `references/e2e-stack.md`); not `master-latest` |
| Identity under test | When the ticket changes Identity catalog/mappings: `apaleo-identity:wt-<slug>` + `IDENTITY_IMAGE` (`references/identity.md`). Else compose `master-latest` |
| Flaky / quarantine | No framework; OPA authz race after recreate — wait for bundle or re-run; do not add skips to greenwash |
| Secrets | Never copy passwords from `src/config.ts` into plans or commits |
| Shared stack lock | `$ROOT/.local/e2e-stack.lock` before rebuild/recreate/run — `references/e2e-stack.md` |
| Missing Identity scopes | `You requested scopes that do not exist` after a local DB reset → `references/e2e-missing-identity-scopes.md`. Strip only scopes the ticket does not need; **never commit** `src/config.ts` `allowedScopes` patches |

### Domain → folder map (heuristic)

| apaleo area | `src/tests/…` |
|---|---|
| Booking / reservation / offers | `core/booking/`, availability/offers nearby |
| Finance / folio / charges | `core/finance/` |
| Taxes | `core/taxes/` |
| Rate plans / rates / inventory | `core/rate-plan/`, `rates/`, `inventory/` |
| Account / settings / policies | `core/account/`, `settings/`, `policies/` |
| Other services | top-level domains: `payment/`, `identity/`, `webhook/`, `fiscal-*`, … |

### ADDITION — destructive / shared-env gate

Before any command with `-e staging`, `-e production`, or smoke/load/seed against non-localhost: stop and ask. Default pipeline E2E is localhost only.

### ADDITION — E2E stack lock (multi-worktree)

Before rebuilding the UI API image, writing `UI_API_IMAGE`, recreating `api`, or running `npm run test:file` / `test:core` against localhost:

1. Read `$ROOT/.claude/skills/references/e2e-stack.md`.
2. Prefer deferring the green run to `implement`'s verify/fix subphase. If you must run here (TDD), **wait** on the queue:

   ```bash
   $ROOT/.claude/skills/references/e2e-stack-lock.sh acquire --wait \
     --branch "<branch>" --worktree "$WT" --skill e2e-test-engineering-development
   ```

3. Do **not** steal an active lock. Do **not** stop-and-abandon silently — either wait or ask the user to cancel.
4. Use branch-scoped image tag from the script (`image=` line).
5. In `finally`-style cleanup, restore the prior image/configuration and verify health. Then **release**
   when the run finishes; release removes the branch image when unreferenced and caps BuildKit cache:

   ```bash
   $ROOT/.claude/skills/references/e2e-stack-lock.sh release --branch "<branch>"
   ```

True parallel compose stacks are **not** supported — the queue serializes local E2E.

### ADDITION — page objects

This suite is primarily **HTTP API** Jest tests (generated clients), not browser page-objects. Mark the Discovery “page objects” / “selector strategy” axes `n/a` unless the nearby folder is clearly UI/browser-based.

---

# Core Principle

Consistency over creativity.

New tests should look as if they were written by the same developer who authored the surrounding tests.

Prefer existing patterns over new abstractions.

Learn testing conventions from nearby tests before generating code.

---

# Search Scope

You may inspect:

* test files in the current directory tree
* helpers/fixtures/builders referenced by those tests
* shared utilities those tests import (`src/lib/…`)
* `.cursor/rules` listed above
* `development/AGENTS.md`

Do not inspect:

* unrelated domains outside the supplied directory (except a single targeted helper resolution)
* production `apaleo` C# solely to reverse-engineer behaviour — only when a helper/proxy type cannot otherwise be understood, or the user asks

---

# Discovery Process

Before generating code:

## Step 1 — Find Closest Matches

Start with 2–3 `*-spec.ts` files that most closely resemble the requested feature (feature name, workflow, endpoint, resource).

## Step 2 — Extract Conventions

Fill the Discovery Report from those files.

## Step 3 — Expand Only When Necessary

Open additional files only to answer a specific unanswered question (auth helper, builder, cleanup, assertion style). Stop when answered.

---

# Discovery Report

Do not generate code until this report is complete.

**Primary examples:** the 2–3 files the new test will mirror.

## Convention Table

| Axis | What this suite does | Evidence (file) | Status |
|---|---|---|---|
| suite organization | | | known / unknown / n/a |
| test naming | | | |
| scenario structure | | | |
| setup strategy | | | |
| authentication | | | |
| fixtures | | | |
| builders | | | |
| helper functions | | | |
| page objects | | | |
| selector strategy | | | |
| assertion style | | | |
| cleanup strategy | | | |
| reusable abstractions | | | |

Every `known` row needs evidence. Genuine N/A → `n/a` with reason.

## Files Opened

List opens not cited as evidence: question + why unanswered.

## Gate

* ≥2 `unknown` → continue discovery.
* ≤1 `unknown` → state remaining uncertainty; start Phase 1.

---

# Convention Priority

1. Same feature folder  
2. Same business domain  
3. Same directory tree  
4. Shared `src/lib` utilities  
5. `.cursor/rules` + `AGENTS.md`

---

# TDD Workflow

Unless the user states the feature already exists, use TDD.

## Phase 1 — Analysis

Choose reuse from the convention table; name the primary example. Prefer one focused scenario.

## Phase 2 — RED

Write the failing E2E test following conventions. Deterministic; assert observable API behaviour. Explain expected failure. Do not implement the product feature here if that lives in `apaleo` — coordinate with the implementation plan (often RED is “API already changed, spec asserts new contract”).

## Phase 3 — Confirm RED

Execute **only** the new/modified tests:

```bash
cd "$ROOT/development" && npm run test:file -- ./src/tests/.../<spec>.ts
```

Valid RED: compiles, runs, fails on missing behaviour. Invalid RED: syntax, wrong client setup, auth/env, fixture bugs — fix the test first.

## Phase 4 — GREEN

Smallest change to satisfy the failing test (spec and/or `apaleo` per plan). No speculative cleanup.

## Phase 5 — REFACTOR

Remove duplication; preserve behaviour and local conventions. Abstractions only when nearby peers already use them.

## Phase 6 — Independent Verification

Dispatch a **separate** subagent (`general-purpose`) with a self-contained brief: paths changed, convention table summary, what to verify. Reviewer output exactly `Approved` or `Changes Required`.

---

# Hard Gates

* No unscoped search when directory/task missing — ask.
* No full `npm test` locally.
* No shared-env runs without confirmation.
* No hand-editing `src/proxy/**`.
* No skipping/weakening tests to greenwash.
* Never invent suite architecture the neighbours do not use.

## Output

State: skills/paths loaded, discovery gate result, commands run + results, files touched, Phase 6 verdict.

## Feature flags (ConfigCat)

Rollout flags: `src/lib/helpers/config/features.ts` + `$ROOT/.claude/skills/references/feature-flags.md`.
Enable in `beforeAll`, restore in `afterAll`. Not the same as Core property FeatureSettings helpers under `lib/helpers/settings/`.
