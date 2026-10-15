---
paths:
  - "worktrees/**/development/**/*"
---

# Development/E2E paths

- Load `/e2e-test-engineering-development` before editing.
- Prefer `npm run test:file -- <spec>`; never run local full `npm test`.
- Never run unattended destructive tests against staging or production.
- Never commit the local Identity-scope workaround in `development/src/config.ts`.
- Use the shared E2E stack lock and restore the prior owner/image on exit.
- In `*-spec.ts`, do not add ticket-id, AC-id, or implementation-journal comments (`// SL-29:`, `// AC-1`, “no generated proxy yet”, why a fixture is dedicated). The `it()` title and code carry the why. If a generated proxy method exists, call it instead of raw `fetch`.
- `*-data-authz-spec.ts` covers filtered GET/list data for callers who can hit the route. Write-endpoint 403s (split, fork, PUT, DELETE) belong in the matching `*-authz-spec.ts`.
