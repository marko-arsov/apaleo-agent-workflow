# Local E2E — missing Identity scopes (temporary workaround)

This file is **only** for missing **OAuth ApiScopes** in Identity’s seed (`storefront:admin` etc.). It cannot register **backend permission keys** (`core.calendar_events.read`) — those need an Identity catalog PR (`references/identity.md`, Notion [Adding New Permissions](https://app.notion.com/p/apaleo/Adding-New-Permissions-34104b9ee10b804b9ccfdb84881a65d7)).

Identity’s **fresh seed** (current `apaleo-identity:master-latest`) does not always include every scope that `development/src/config.ts` requests when creating a RANDOM E2E client (`ensureNewAccountCreated` → `createCredentialsAsync` → `allowedScopes`).

Classic failure after a **local Postgres recreate** (wipes the Identity DB, then Identity re-seeds):

```text
HttpError 422: You requested scopes that do not exist: storefront:admin
```

That dies in `beforeAll`, before any product assertions. `npm run setup` does **not** seed IdentityServer `ApiScopes`. Connecting to staging Postgres is unrelated (different host/volume).

`storefront:admin` is the known example (2026-08): Identity seed has `bookingcom:admin` / `siteminder:admin` but **not** `storefront`. Local compose does not run a storefront service. There are no `src/tests/**` storefront specs. Calendar and most `test:core` specs do not need the scope.

The **lasting** fix is an Identity-repo seed PR (not this team). Until then, the pipeline may apply a **local-only** workaround.

## Workaround (mandatory rules)

When localhost E2E fails with `You requested scopes that do not exist: <names>`:

1. **Safe to strip** those names from `$DEV/src/config.ts` `allowedScopes` **only if** the current ticket does **not** require them:
   - New/changed specs do not import `src/proxy/storefront` (or whichever API owns the scope).
   - `product.md` / `implementation.md` / ACs do not require that API or those scopes.
   - Failure is account/client setup (`ensureNewAccountCreated`), not a product assertion.
2. **Unsafe** → do **not** strip. `PIPELINE_INPUT_REQUIRED`: feature needs the scope; Identity seed is the real fix.
3. Apply via the helper (do not hand-edit if the script can do it):

   ```bash
   $ROOT/.claude/skills/references/e2e-local-scope-workaround.sh apply \
     --dev "$DEV" --scopes storefront:admin
   ```

4. Re-run the same `npm run test:file` (or `test:core`) command.
5. Record in `test-report-<n>.md`: scopes stripped, why safe, that this is **not** committed.

### Never commit or push

This patch is **machine-local**. It must not appear in a commit, a push, or a PR.

- `/commit` and `/commit-and-push` **restore first**, then stage. Refuse to commit `src/config.ts` while the workaround is applied.
- `implement-pipeline.sh` restores **before** `commit-and-push` / `draft-pr` and on **EXIT** (success, block, or crash).
- Do not “fix” Identity by deleting scopes from `config.ts` as a product change unless the ticket’s AC explicitly changes that list.

Restore:

```bash
$ROOT/.claude/skills/references/e2e-local-scope-workaround.sh restore --root "$ROOT"
```

State/backup live under `$ROOT/.local/e2e-scope-workaround/` (not git).

## Prevention (schema drift)

Do **not** recreate the whole `db` container to fix an apaleo migration collision. Drop/recreate only the `apaleo` database so Identity’s DB (and its `ApiScopes`) stay intact. See `e2e-stack.md`.
