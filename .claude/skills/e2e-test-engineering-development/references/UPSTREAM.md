# Upstream tracking — e2e-test-engineering-development

- **Source:** `$ROOT/agent-skills/skills/e2e-test-engineering/` (plugin `e2e-test-engineering@apaleo`)
- **Source commit:** `e79b60bebfe360d7bfb9f2b4d16afeecdd17c9f1`
- **Specialized as:** personal skill `e2e-test-engineering-development` (does not shadow upstream in `/`)

## Changes from upstream

- Added **Local facts** table: Jest 27, paths, commands, auth, Docker localhost, cross-repo branches, proxy regen, timeouts.
- Documented **never run the full Jest suite locally**. One file is `yarn test -- tests/<area>/<file>-spec.ts` from the service `e2e/` directory. Payment still uses `npm run test:file`.
- Added **destructive/shared-env gate** for staging/production.
- Specs for migrated services live in `<service>/e2e/tests`. Payment remains `development/src/tests/payment`.
- Marked page-objects/selectors as typically `n/a` for this HTTP API suite.
- Pointed at `development/AGENTS.md` and `.cursor/rules/*.mdc`.
- Wired Confirm RED to the real filtered command.
- Kept Discovery report, convention priority, RED→GREEN→REFACTOR, Phase 6 independent review, Hard Gates spirit.

## Intentionally not removed

- Upstream “page objects” / “selector strategy” axes remain in the table (mark `n/a` when appropriate).
- Generic “do not invent architecture” and scoped-search rules retained.
