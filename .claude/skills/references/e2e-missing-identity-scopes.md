# Local E2E — missing Identity scopes (temporary workaround)

This file is **only** for missing **OAuth ApiScopes** in Identity’s seed (`storefront:admin` etc.). It cannot register **backend permission keys** (`core.calendar_events.read`) — those need an Identity catalog PR (`references/identity.md`, Notion [Adding New Permissions](https://app.notion.com/p/apaleo/Adding-New-Permissions-34104b9ee10b804b9ccfdb84881a65d7)).

Identity’s **fresh seed** (current `apaleo-identity:master-latest`) does not always include every scope the E2E client requests (`ensureNewAccountCreated` → `createCredentialsAsync` → `allowedScopes`).

Migrated services take that client setup from `@apaleo/e2e-sdk-lib`. `development/src/config.ts` is not on development master. Do not recreate it, and do not commit a patch of the SDK or of `node_modules`. Payment still reads `development/src/lib/kernel/config.ts`. The helper script `e2e-local-scope-workaround.sh` still looks for the old `development/src/config.ts` path and will not find it. A missing scope on a migrated suite is an Identity seed or e2e-sdk fix, not a local file to commit.

Classic failure after a **local Postgres recreate** (wipes the Identity DB, then Identity re-seeds):

```text
HttpError 422: You requested scopes that do not exist: storefront:admin
```

That dies in `beforeAll`, before any product assertions. `npm run setup` does **not** seed IdentityServer `ApiScopes`. Connecting to staging Postgres is unrelated (different host/volume).

`storefront:admin` is the known example (2026-08): Identity seed has `bookingcom:admin` / `siteminder:admin` but **not** `storefront`. Local compose does not run a storefront service. Calendar and most core specs do not need the scope.

The **lasting** fix is an Identity-repo seed PR, or a change in `e2e-sdk` when the requested list itself is wrong.

## What to do

When localhost E2E fails with `You requested scopes that do not exist: <names>`:

1. Confirm the failure is account/client setup (`ensureNewAccountCreated`), not a product assertion.
2. If the ticket does not need those scopes, record the names in the test report and continue with the rest of the evidence. Do not edit `@apaleo/e2e-sdk-lib`, `node_modules`, or `development/src/lib/kernel/config.ts` to hide them.
3. If the ticket needs those scopes → `PIPELINE_INPUT_REQUIRED`. The fix is the Identity seed or e2e-sdk, not a local strip.
4. Do not recreate `development/src/config.ts`. `e2e-local-scope-workaround.sh apply` still targets that old path and cannot fix a migrated suite.

### Never commit or push

A scope strip must not appear in a commit, a push, or a PR.

- `/commit` and `/commit-and-push` restore any leftover local strip before staging.
- `implement-pipeline.sh` restores **before** `commit-and-push` / `draft-pr` and on **EXIT**.
- Do not “fix” Identity by deleting scopes from a config file unless the ticket’s AC explicitly changes that list.

If a previous run left a strip behind:

```bash
$ROOT/.claude/skills/references/e2e-local-scope-workaround.sh restore --root "$ROOT"
```

State/backup live under `$ROOT/.local/e2e-scope-workaround/` (not git).

## Prevention (schema drift)

Do **not** recreate the whole `db` container to fix an apaleo migration collision. Drop/recreate only the `apaleo` database so Identity’s DB (and its `ApiScopes`) stay intact. See `e2e-stack.md`.
