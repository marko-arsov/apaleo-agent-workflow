---
name: e2e-test-engineering-development
description: >-
  Local specialization of Apaleo's e2e-test-engineering for the apaleo/development
  Jest suite: concrete paths, commands, auth, Docker localhost targeting, and
  cross-repo branch rules. Use when writing or modifying E2E specs under
  development/, during implement's verify/fix or manual test-and-fix, or on
  /e2e-test-engineering-development. Prefer this over upstream e2e-test-engineering
  for this workspace. Not for apaleo xUnit tests.
argument-hint: "[test directory under src/tests] [task]"
---

# E2E Test Generation — Development Specialization

Create or modify E2E tests in `development/` while preserving nearby conventions.

Read first:

- `$ROOT/.claude/skills/references/e2e-development.md` — canonical local specialization
- `$ROOT/.claude/skills/references/e2e-stack.md`
- `$ROOT/.claude/skills/references/e2e-missing-identity-scopes.md`
- `$ROOT/.claude/skills/references/identity.md` when permission catalog / role mapping changes

## Hard rules

- If the test directory or task is missing, ask before searching.
- Discover 2–3 nearby `*-spec.ts` examples before writing or changing tests.
- Prefer `npm run test:file -- ./src/tests/.../<spec>.ts`; never run full `npm test` locally.
- Stop before any staging/production/shared-env command unless the user confirms.
- Do not hand-edit `src/proxy/**`.
- Do not skip, weaken, quarantine, or filter tests to go green.
- Use the E2E stack lock before local Docker API rebuild/recreate/run.
- Missing Identity scopes after local DB reset may use the documented local-only `config.ts` strip only when the ticket does not need those scopes; never commit it.

## Workflow

Follow `references/e2e-development.md`: discovery report, RED, confirm RED, GREEN, refactor, independent verification. State paths loaded, commands run, files touched, and verification result.
