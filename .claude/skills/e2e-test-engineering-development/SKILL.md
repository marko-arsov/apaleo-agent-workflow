---
name: e2e-test-engineering-development
description: >-
  Local specialization of Apaleo's e2e-test-engineering for service-repo Jest
  E2E. Use when writing or modifying specs under a service repo's e2e/tests,
  or payment specs still under development/, during implement's verify/fix or
  manual test-and-fix, or on /e2e-test-engineering-development. Prefer this
  over upstream e2e-test-engineering for this workspace. Not for xUnit tests.
argument-hint: "[test directory under e2e/tests or payment src/tests] [task]"
---

# E2E Test Generation — service-repo specialization

Create or modify E2E tests in the service repo that owns them, preserving nearby conventions.

Core specs live in `apaleo/e2e/tests`. Identity and the other migrated services use `e2e/tests` in that service repo. Payment stays in `development/src/tests/payment`. Do not open a development companion PR for a migrated service.

Read first:

- `$ROOT/.claude/skills/references/e2e-development.md` — canonical local specialization
- `$ROOT/.claude/skills/references/e2e-stack.md`
- `$ROOT/.claude/skills/references/e2e-missing-identity-scopes.md`
- `$ROOT/.claude/skills/references/identity.md` when permission catalog / role mapping changes

## Hard rules

- If the test directory or task is missing, ask before searching.
- Discover 2–3 nearby `*-spec.ts` examples before writing or changing tests.
- From the service `e2e/` directory, run one file with `yarn test -- tests/<area>/<file>-spec.ts`. Payment: `npm run test:file -- ./src/tests/payment/<file>-spec.ts`. Never run the full suite locally.
- GitHub Packages auth is `NPM_CONFIG_USERCONFIG=$HOME/.npmrc` or a `.npmrc` in that `e2e/` folder. Never commit tokens.
- Stop before any staging/production/shared-env command unless the user confirms.
- Do not hand-edit generated `e2e/proxy/**`.
- Do not skip, weaken, quarantine, or filter tests to go green.
- Use the E2E stack lock before local Docker API rebuild/recreate/run.
- A missing Identity scope after a local DB reset follows `e2e-missing-identity-scopes.md`. Do not commit a scope strip, and do not recreate `development/src/config.ts`.

## Workflow

Follow `references/e2e-development.md`: discovery report, RED, confirm RED, GREEN, refactor, independent verification. State paths loaded, commands run, files touched, and verification result.
