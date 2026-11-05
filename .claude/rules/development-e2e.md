---
paths:
  - "worktrees/**/development/**/*"
  - "worktrees/**/e2e/**/*"
---

# Service E2E paths

- Load `/e2e-test-engineering-development` before editing.
- Migrated services: specs in `<service>/e2e/tests`, generated clients in `e2e/proxy/<module>`. One file: `yarn test -- tests/<area>/<file>-spec.ts` from `e2e/`. Never run the full `yarn test` locally.
- Payment is the exception: `development/src/tests/payment`, `npm run test:file -- ./src/tests/payment/<file>-spec.ts`.
- Never run unattended destructive tests against staging or production.
- Never commit a `.npmrc` token, an Identity-scope strip, or a patch of `@apaleo/e2e-sdk-lib`. Do not recreate `development/src/config.ts`.
- Use the shared E2E stack lock and restore the prior owner/image on exit.
- In `*-spec.ts`, do not add ticket-id, AC-id, or implementation-journal comments (`// SL-29:`, `// AC-1`, “no generated proxy yet”, why a fixture is dedicated). The `it()` title and code carry the why. If a generated proxy method exists, call it instead of raw `fetch`.
- `*-data-authz-spec.ts` covers filtered GET/list data for callers who can hit the route. Write-endpoint 403s (split, fork, PUT, DELETE) belong in the matching `*-authz-spec.ts`.
