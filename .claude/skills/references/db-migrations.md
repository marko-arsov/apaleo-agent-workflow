# DB migrations — Apaleo two-PR (and multi-PR) conventions

Canonical facts for the personal pipeline. Verified against recent `apaleo/apaleo` PRs and `development/jenkins-helpers.groovy` `runDatabaseMigrationCheck`.

## PR count — use the minimum (rule `db-migration-minimum-pr-split`)

| Change | PRs |
|---|---|
| Add a table/column | **2**: `[DB-MIGRATION]` schema + entity → feature code |
| Drop a column/table | **2**: code stops using it and removes the entity property → `[DB-MIGRATION]` drop |
| Replace a column (new type/meaning + backfill) | **3**: `[DB-MIGRATION]` add + backfill + entity → code switch + remove old properties → `[DB-MIGRATION]` drop |
| Rename a column still in use | **3**: code stops using it → `[DB-MIGRATION]` rename → map the entity to the new name (HC-3156) |

Do not add PRs for dual-write windows or rollback safety unless the user asks. State the trade-off
instead (e.g. "old pods during rollout / a rollback do not see rows written by new code"). Make the old
column nullable in the first migration and have the code it ships tolerate NULLs, so the code switch can
stop writing it without an extra PR.

## Why

Production deploys are rolling. Schema that the **new** code needs must exist **before** (or with) that code. Destructive changes must not remove columns the **old** code still reads. Hence schema and application code are often split across PRs.

## Additive changes (new tables / new columns) — **2 PRs**

**Deploy-ahead-of-code** (example: HC-3273 `#12862` then `#12863`; HC-3244 `#12858` then HC-3245 `#12877`).

### PR 1 — `[DB-MIGRATION]` (schema + entity)

| | |
|---|---|
| **Title** | `[DB-MIGRATION] HC-<id> <imperative summary>` |
| **Goal** | Land schema on master and get it applied in environments **before** app code that depends on it |
| **E2E** | `N/A — schema-only` (no development companion required) |
| **What to commit** | The EF artifacts under `src/Apaleo.Data/Migrations/` (`*Migration*.cs`, `*.Designer.cs`, `ApaleoContextModelSnapshot.cs`) **plus** the matching `Data/Entities` properties and entity type builder changes, and only the minimal compile fixes those force. No API/domain feature code. |
| **Local workflow** | Add/adjust entities + builders → `task ef:add-migration -- <Name>` → commit migration, snapshot, entities and builders together. `dotnet ef migrations has-pending-model-changes` must report no changes. |
| **Why not migration-only** | A snapshot ahead of the model breaks design-time `dotnet ef` on master (`PendingModelChangesWarning`), and a teammate's next `migrations add` would drop the new columns. Precedent: `#12858`. Seen in SL-145. |
| **PR body** | Link ticket; state schema-only; link **Follow-up** app PR if known; include the flattened SQL and the **Production apply** recommendation |
| **Apply** | Local: `task ef:update-database`. Staging: startup, no manual step. Production: see **Production apply** |

## Flatten manual SQL (PR review copy)

`task ef:migration-script` runs `dotnet ef migrations script -i`. With `-i`, Npgsql does **not** emit `CREATE TABLE IF NOT EXISTS`. It wraps **each** statement in:

```sql
DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '…') THEN
        -- one CREATE / INSERT
    END IF;
END $EF$;
```

That means “skip this whole migration if it is already in history,” not “create this object if missing.” One migration with four statements → four identical `DO $EF$` blocks — noisy and harder to review.

**Do not paste that raw output into the PR.** Rewrite the manual script into simpler idempotent Postgres (same idea as HC-3327 `#12938` / `ai-plans/.../migration.sql`):

| Prefer | Instead of |
|---|---|
| `CREATE SCHEMA …` in one small `DO` only if the schema has no `IF NOT EXISTS` on older Postgres | Per-statement `DO $EF$` history checks |
| `CREATE TABLE IF NOT EXISTS …` (DDL must match `Up()`) | `CREATE TABLE` inside `DO $EF$` |
| `CREATE [UNIQUE] INDEX IF NOT EXISTS …` | Index create inside `DO $EF$` |
| One `INSERT INTO "__EFMigrationsHistory" … SELECT … WHERE NOT EXISTS (…)` | Repeated history `IF NOT EXISTS` wrappers |

**Hard requirements:**

1. DDL (table/columns/FKs/indexes/names) stays **identical** to the migration `Up()`.
2. History row uses the **exact** `MigrationId` and `ProductVersion` from the EF migration.
3. Script remains safe to re-run (native `IF NOT EXISTS` / `WHERE NOT EXISTS`).
4. Save the flattened script under `ai-plans/<branch>/migration.sql` and paste that into the PR body — not the raw `-i` dump.

`task ef:migration-script` is the **source of truth for DDL** when flattening the PR review copy. It passes `-i`. The production file does not: `/migration-script` follows the runbook and runs `dotnet ef migrations script <last-applied> --output Migration.sql` with no `-i`.

## Production apply

Rule `db-migration-production-apply`. Staging applies EF migrations at service startup. There is no manual staging step.

Production also applies them at startup, and that step times out after 30 seconds ([How to deploy to production](https://app.notion.com/p/apaleo/How-to-deploy-to-production-51bd31c54da746ccbc47ee02f665aa12)). A migration that can hold a lock or run longer than that is executed on the production database before the deploy ([time-consuming migrations](https://app.notion.com/p/apaleo/How-to-perform-time-consuming-data-migrations-in-production-9cf9eb99b11e452d83bcc181cc926a8a)). The history row the script inserts keeps startup from running it again. Manual production execution is a precaution for locks on hot tables, not the default (Davide Lettieri on apaleo `#12938`).

| Recommend | When |
|---|---|
| **Manual**, before the production deploy | An index on a large table; a table rewrite or row backfill; a lock on a hot request-path table |
| **Startup**, with the deploy | A new empty table; `ADD COLUMN` that is nullable or has a constant default (Postgres 11+ metadata-only, no rewrite) |

`/specify` records the choice under `## Production apply` in `product.md`. The reason names the tables and what the DDL does. Judge from the migration and the table's role; a measured row count is not required. `/draft-pr` copies that section and the flattened SQL into the PR. The flattened script is the review copy for either recommendation.

When the recommendation is manual, generate the file that is executed after the PR has merged:

```bash
/migration-script <issue, PR, or branch>
```

The skill fast-forwards the parked `apaleo` master checkout and runs `dotnet ef migrations script <previous> --output Migration.sql`, plus the project and startup-project flags this repo needs. It does not pass `-i` or an end id, so the file contains every migration after `<previous>` through current `master`. `<previous>` is the migration immediately before this PR's first new migration: the runbook's last-applied id, and the start boundary. Its SQL is not in the file. The skill writes `$ROOT/apaleo/Migration.sql` (gitignored; same path as `migration.sql` on a case-insensitive disk) and puts `SET statement_timeout = 0;` on the first line, without a byte-order mark. Send that file to the person who will run it once on production before the deploy. A second run fails. A failed run rolls back with the transaction. The skill does not execute SQL, commit, or push. It assumes production is already on `<previous>`. Pass `--from <MigrationId>` when production is behind that id. If `--from` is already applied in production, the non-idempotent script errors on that migration.

The migration stays in the repository so dev, CI, and staging still apply it at startup. The history row keeps production startup from applying it again.

### PR 2 — application code

| | |
|---|---|
| **Title** | `HC-<id> …` (no `[DB-MIGRATION]` unless this PR also ships further schema) |
| **Depends on** | PR1 merged (and migration applied in target envs as required). Rebase onto master after PR1. |
| **Contains** | Domain, API, swagger, unit tests, e2e in `development` when needed (entities already shipped in PR1) |
| **Must not** | Re-add the same migration files; snapshot fights if both PRs touch migrations carelessly |

**Specify / plan:** when a feature needs new tables/columns, **split the implementation plan into Migration PR then Feature PR** with explicit merge/apply ordering.

## Destructive / rename changes — **multi-PR** (CI-enforced)

CI (`runDatabaseMigrationCheck`): **fail** if a migration `Up()` contains `DropColumn` / `DropTable` / `RenameColumn` / `RenameTable` **and** the same PR removes/renames lines or files under `Data/Entities`.

Rule of thumb:

1. **Stop using the column in code and remove the entity property** → deploy  
2. **Then** ship the drop/rename `[DB-MIGRATION]` → deploy  
3. Rename only: map the entity onto the renamed column  

No dual-write or "stop writing" PR in between unless the user asks (see **PR count**).

Example rename sequence HC-3156: `#12765` (1/3 code) → `#12767` (2/3 `[DB-MIGRATION]` rename columns) → `#12774` (3/3 map entities to renamed columns).

Never combine “delete property from entity” + “DropColumn in migration” in one PR.

## Business migrations vs EF schema

One-off **data** fixes (`feat: add business migration…`, account-scoped SQL in code) are a different path from `[DB-MIGRATION]` EF schema PRs. Do not confuse them in plans. EF `[DB-MIGRATION]` = schema/history under `Apaleo.Data/Migrations`.

## Pipeline skill checklist

| Skill | When schema is in scope |
|---|---|
| `specify` | Verdict plus the **minimum** PR sequence from **PR count** (2 for add or drop, 3 for replace or rename); name each PR, the flattened SQL, and a `## Production apply` recommendation with the reason. Any extra PR needs an explicit user request. |
| `implement` | Implement/commit PR1 migration slice first when splitting; don’t mix API into migration PR |
| `commit` | PR1 subjects: `[DB-MIGRATION] HC-…` |
| `draft-pr` | PR1: `[DB-MIGRATION]` title, E2E N/A, paste `## Production apply` and the flattened SQL, link follow-up; PR2: Depends on migration PR |
| `migration-script` | After a manual-production migration PR merges; write the gitignored production file from parked master and do not apply it |
| `peer-pr-review` | Flag mixed migration+feature or drop+entity in one PR |
| `implement` verify/fix | Schema-only: no E2E; feature PR: plan-selected validation |

## Commands (local)

```bash
cd $WT/apaleo   # feature worktree
task ef:add-migration -- <Name>
task ef:update-database
task ef:migration-script -- <From> <To>   # raw -i dump; flatten for the PR only
# production file, after merge: /migration-script <issue|pr|branch>
```

See `apaleo/README.md` / `Taskfile.yml`.
