# Staging smoke policy and playbook

After a PR merges to `master`, Jenkins builds and deploys to staging. “Good to go” means the merged
behavior was observed on a sufficiently fresh staging deployment and the relevant smoke passed. A
healthy endpoint or a repeated local test is not enough.

The engineer has staging VPN and read access to staging core Postgres. Use that access through existing,
unambiguous sessions or profiles; never discover, print, or persist secrets.

## Staging surfaces

| Surface | URL |
|---|---|
| UI | https://app.apaleo-staging.com |
| API health | https://api.apaleo-staging.com/health |
| API / Swagger | https://api.apaleo-staging.com/swagger/index.html |
| API base | https://api.apaleo-staging.com |
| Identity | https://identity.apaleo-staging.com |

The UI/API are public endpoints. VPN is normally needed for Jenkins/AWS operational surfaces and DB
access, not for opening the app.

## API surfaces: MCP, then helper

For API checks and test-data setup, use the first surface that covers the operation:

1. **Apaleo MCP** (staging). Call `GetCurrentAccount` first and record the account code. In gateway
   mode only `search_tools` and `get_schema` are listed: discover the operation, read its schema,
   then call it. Prefer the MCP: it holds no local secret and its schemas cost few tokens.
2. **`$ROOT/.claude/skills/references/staging-api.sh`** for endpoints the MCP does not expose
   (for example `v0-nsfw` routes) or when a response field the MCP drops is needed.

   ```bash
   staging-api.sh whoami                      # account and claims, never the token
   staging-api.sh GET  '/booking/v1/blocks/BER-X?expand=timeSlices'
   staging-api.sh PUT  /booking/v1/block-actions/BER-X/amend '<json>'
   staging-api.sh logout                      # delete the cached token
   ```

   It uses the client-credentials flow. Credentials, first match wins:
   `APALEO_STAGING_CLIENT_ID` + `APALEO_STAGING_CLIENT_SECRET`, or
   `$ROOT/.local/staging-api/staging-client.json` with `clientId` and `clientSecret` (mode 600,
   untracked). The token is cached at `$ROOT/.local/staging-api/.token`. The body goes to stdout,
   `HTTP <code>` to stderr, and it exits 1 on a status of 400 or above.
3. **curl with an existing token**, then the browser, as described below.

**Test account.** The engineer's disposable staging account is `staging.testAccount` in the
per-user config (see "Per-user configuration" below), with `staging.testProperty` as the default
property. Both the MCP and the helper client are bound to it. Automatic reversible
writes are allowed only when the active account is that test account. Any other account is
read-only unless the engineer confirms. When a check needs data the test account lacks (a country,
a fiscal setup, a flag state), create it there under the reversible-data rules, or name the
missing setup in one checkpoint.

## Per-user configuration

Values that belong to one engineer live in `$ROOT/.local/user-config.json`, never in the
repository. `.local/` is untracked. The template is `references/user-config.example.json`;
`references/user-config.sh get <key>` reads a value, and `user-config.sh init` creates the file.

| Key | Meaning |
|---|---|
| `staging.testAccount` | The engineer's disposable staging account. Automatic reversible writes are allowed only there |
| `staging.testProperty` | Default property in that account for test data |
| `staging.dbUser` | Optional IAM database user when it differs from the AWS user name with `.` → `_` |

Secrets are never stored there. The staging API client lives in `.local/staging-api/` and Jenkins
credentials in the shell or `~/.config/jenkins.env`. When `staging.testAccount` is missing, ask
once for the account code, create the file with `user-config.sh init`, and fill in the value after
the engineer confirms. Until then, run only reads; `staging-api.sh` refuses writes without it, and
refuses them when the token's account is a different one.

## Non-negotiable boundaries

- Do not run `npm test`, `npm run test:file`, or Jest with `-e staging` / `-e production`. Shared
  staging is smoke-tested with focused UI/API/SQL checks, not the local E2E suite.
- Never take credentials from `development/src/config.ts`, shell history, logs, or tracked files.
- Never expose Bearer tokens, client secrets, cookies, connection strings, or sensitive response
  fields in chat, commands shown to the user, screenshots, or `ai-plans/`.
- Never run staging SQL that can write: no modifying CTE, function with side effects, DML, DDL,
  maintenance command, or stored procedure. Use a server-enforced read-only transaction.
- Do not silently change feature flags, roles, permissions, shared configuration, or real/customer-
  like data.
- Do not approve production, deploy, merge, or post “good to go” as the user.

## Capability-first execution

Check the current host before assigning work to the user.

| Need | Agent behavior |
|---|---|
| Terminal/GitHub | Run the inspection directly; summarize useful evidence instead of pasting stdout. |
| Browser/computer control | Open the staging URL, reuse the existing session, navigate, inspect, and capture evidence. |
| Login/MFA/CAPTCHA | Navigate to the prompt, ask the user to complete only that prompt, then resume. |
| Apaleo MCP / `staging-api.sh` | Check the account first; run API checks and test-data setup directly. |
| Existing Bearer token | Check presence without echoing it; make the scoped request and redact sensitive output. |
| Missing token | Give one secure local setup step; never ask for the token in chat. |
| Staging VPN connected (`staging-sql.sh --check` passes) | Run focused read-only SQL directly ("Read-only staging SQL"). |
| VPN down, or helper unavailable | Ask once for the VPN; fall back to the Rider MCP; never guess a host, database, or password. |
| Subjective visual/business judgment | Capture what can be captured, then ask one precise question with Pass/Fail criteria. |

Browser testing is agent work whenever browser automation is available. Swagger is a discovery or
fallback UI, not mandatory manual labor; prefer an exact API request when practical.

## Action policy

Run these without a confirmation menu after the user asks for a staging smoke:

- repository/plan/PR inspection, fetches, deployment-metadata lookup, HTTP GET/HEAD probes;
- authenticated GET/HEAD through an existing session or token;
- read-only browser navigation and inspection;
- focused `SELECT`/`SHOW`/catalog queries in a server-enforced read-only transaction;
- test writes in the engineer's `staging.testAccount` that affect nobody else ("Reversible staging
  data" below);
- creation of local smoke evidence.

Group everything else into one checkpoint after the safe work. Show the exact method/UI action,
target account/property, sanitized body, expected side effect, cleanup, and why it is necessary.
Do not ask again unless the action set materially changes.

If a supposedly rejecting request unexpectedly succeeds, treat it as a failure, inspect/clean up
only within the already authorized boundary, and do not try more mutation-capable variants.

## Resolving deployment freshness

Use the strongest available evidence, in order:

1. A deployment record names the merge SHA or a descendant SHA for the affected service. The
   Jenkins master pipeline is that record: `references/jenkins-readonly.sh build-for <repo> <sha>`
   and `builds <repo>` show which green master build (each one deploys to staging) contains the
   commit. Each build checks out the pipeline helpers from `development` as well; the helper picks
   the checkout of the requested repository. Production versions come from `prod <param>`
   (`Deployment/Core`, deployed by hand).
2. A repository-confirmed version/build endpoint or response header identifies a deployed revision;
   verify ancestry with `git merge-base --is-ancestor <merge-sha> <deployed-sha>` when both are Git
   commits.
3. A successful feature-specific check proves behavior that could not exist before the merge. Mark
   this explicitly as inferred deploy evidence.
4. A human confirms the deployed revision from a named Jenkins/Datadog/operations view.

GitHub CI success, membership in `origin/master`, endpoint reachability, and “merged long enough ago”
do not by themselves prove deployment. For a backend + frontend/proxy change, prove freshness for
both or use an integrated behavior that necessarily exercises both.

### Public readiness probes

Run these concurrently when possible:

```bash
curl -sS --max-time 20 -o /dev/null -w '%{http_code}\n' https://app.apaleo-staging.com/
curl -sS --max-time 20 -o /dev/null -w '%{http_code}\n' https://api.apaleo-staging.com/health
curl -sS --max-time 20 -o /dev/null -w '%{http_code}\n' https://api.apaleo-staging.com/swagger/index.html
curl -sS --max-time 20 -o /dev/null -w '%{http_code}\n' https://api.apaleo-staging.com/
```

`200`, redirects, `401`, or `403` may show reachability depending on the route. `000`, `502`, and
`503` require bounded retry or alternate-path evidence. Retry a transient failure at most twice,
with no more than 60 seconds between attempts; report **WAIT** after that rather than looping.

Swagger failure does not end the smoke if the API is healthy: use the repository/OpenAPI contract
and curl. If the API health path remains unavailable, do not run writes.

## Authentication without secret handling

Prefer, in order:

1. the Apaleo MCP session, or `staging-api.sh` with its untracked client file;
2. an existing authenticated browser session;
3. an existing shell token or approved local API client profile;
4. user sign-in/MFA takeover in the opened browser;
5. one local secure-token setup step.

Check only whether a token exists; never print it. If the user must populate one in a shell, instruct
them to use a silent prompt rather than paste it into chat or a command saved in history:

```bash
read -r -s TOKEN && export TOKEN
```

Use the narrow scopes required by the smoke. If the correct staging client/scope is unknown, name
the missing scope or client purpose and direct the user to **Apps → API clients** or `#dev-tech`;
never invent a client secret.

## Read-only staging SQL

**Primary route: `$ROOT/.claude/skills/references/staging-sql.sh`.** It connects to the staging core
cluster as the engineer's IAM database user (`staging.dbUser`, else derived from the AWS identity) with a
15-minute IAM token, and never prints the token. Read-only is enforced three times: the statement
must start with `SELECT`, `WITH`, `EXPLAIN`, `SHOW`, `TABLE`, or `VALUES` (one statement per call);
the session sets `default_transaction_read_only=on`; and the query runs inside
`BEGIN TRANSACTION READ ONLY … ROLLBACK`. Output is CSV with a header row.

```bash
staging-sql.sh --check                                   # VPN, token, login, read-only session
staging-sql.sh 'SELECT "EntityId", "Status" FROM "Reservation"."Block" WHERE … LIMIT 20'
staging-sql.sh -f query.sql
```

Exit codes: `0` ok, `1` query error, `2` refused or usage, `3` network, `4` authentication.

- Exit `3` means the private cluster is unreachable: ask the engineer once to connect the **staging VPN**
  (AWS VPN Client), then retry once.
- Exit `4` means the AWS CLI identity or the IAM database user is missing; name it and stop the SQL
  check.
- It needs `psql` (`brew install libpq`; the helper finds the keg-only binary itself).

**Fallback: the Rider MCP**, only when the helper cannot run (no `psql`, no AWS CLI). Rider's
staging data source uses the same IAM user with its **Read-only** option on;
`list_database_connections`, `test_database_connection`, `execute_sql_query`, and
`fetch_query_result` run without a prompt in Claude Code and the Cursor CLI. Use only a connection
whose name contains `apaleo-staging-aurora-cluster` and whose `readOnly` is `true`. If Rider is not
open, ask once whether to run `/open-rider`, then continue. Rider has been seen to refuse every MCP
query (`User rejected query.`) even with a passing connection test; then mark the SQL check
**NOT RUN**, tell the engineer once, and continue with the other surfaces. Do not loop.

Do not put connection details or tokens on the command line or in evidence. With any route other
than the helper, run the focused query inside a server-enforced read-only transaction and roll it
back even though it should not write:

```sql
BEGIN TRANSACTION READ ONLY;
SELECT ...;
ROLLBACK;
```

Prefer `__EFMigrationsHistory`, `information_schema`, `pg_catalog`, `pg_indexes`, and tightly scoped
business-table lookups. Avoid broad dumps and redact identifiers not needed for the result. Record
the query shape and outcome, not connection details or sensitive rows.

## Derive the right smoke

Use the current plan first, then merged PR body/diff, commit subject, public contract, and changed E2E
scenario names. Each observable claim needs a named check and concrete Pass/Fail signal.

| Change type | Preferred proof |
|---|---|
| UI-visible behavior | Controlled browser path and screenshot/state evidence; API only as supporting evidence. |
| API guard hidden by UI | Exact API request; say why the UI cannot exercise the guard. |
| `[DB-MIGRATION]` / schema-only | Deploy/health plus read-only migration/schema SQL; no invented API flow. |
| Flag-gated | Confirm the existing staging evaluation for the test subject, then exercise behavior; flag changes require a checkpoint. |
| Backend + development/proxy | Prove both deployments or one integrated path that requires both revisions. |
| Authorization/tenancy | Use two deliberately scoped subjects/resources; avoid real data and stop on any unexpected success. |

Prefer the minimum meaningful proof: usually one main/happy path plus one reject path. A smoke should
not recreate the full local automated suite.

## Reversible staging data

Staging is for testing, and `staging.testAccount` belongs to the engineer alone. The line is whether
anyone else is affected, not how big the write is. Inside that account any test is allowed without
asking: creating, amending, cancelling, and deleting test data (services, bookings, folios, charges,
routings, payments recorded on test folios, invoices), night audit on a test property, and the
account's own property or feature settings. Prefer a property whose settings already fit over
changing a setting, and leave email addresses off test bookings so no confirmation mail goes out.

Use a unique marker such as `staging-smoke-SL-29-20260917T140500Z`. Before sending the write, persist
a sanitized **pending cleanup** entry in the current artifact with the target, marker, before-state,
and exact reversal. Afterward, verify the record is gone or restored and mark cleanup complete.
Remove services booked on a test reservation before cancelling it: a service that a cancelled
reservation still references cannot be deleted. When the API refuses a delete, neutralise the
leftover (take it off sale, prefix its name `ZZ disposable <ISSUE>`) and list it in the report.

Ask once, with the exact actions, before anything that could reach or affect other people:

- another account, or real or customer-like data;
- staging-wide configuration or feature flags (ConfigCat is shared; the engineer changes it);
- outbound emails, SMS, webhooks, or real partner/integration calls, including payment-provider
  transactions (card authorisations, captures, refunds) and fiscalization submissions, even in
  test mode; payments recorded directly on a test folio are fine;
- users, roles, permissions, or OAuth clients/secrets;
- bulk or load tests that could slow shared staging, or migration/repair jobs;
- a step whose cleanup is impossible.

Never write to production, and never enter real payment details or credentials.

On resume or rerun, read the latest smoke artifact and resolve pending cleanup before making another
write. Preserve still-current results and continue from the first unfinished check instead of
restarting discovery or asking the user to repeat context.

## Result semantics

| State | Meaning |
|---|---|
| **PASS** | Relevant deployment freshness and every required staging behavior are proven; cleanup succeeded. |
| **PARTIAL** | Completed evidence passed, but one irreducible check or freshness fact remains. |
| **WAIT** | Required revision is not deployed, service is transiently unavailable, or a flag rollout is pending. |
| **FAIL** | Staging behavior contradicts the expected result, or cleanup failed. |
| **BLOCKED** | Required access/tooling is unavailable and no valid remaining proof can run. |

Never convert **PARTIAL**, **WAIT**, or **BLOCKED** to “good to go”. Distinguish:

- **Reachable** — an endpoint responds;
- **Fresh** — the relevant merged revision is deployed;
- **Verified** — the ticket-specific behavior passed.

## Human handoff format

Human steps are a fallback, not the default. Complete all other checks first, then provide only the
remaining actions:

```markdown
### Action needed — sign in, then I’ll continue

1. In the browser tab I opened, complete SSO and MFA.
2. Reply `signed in` without sending credentials.

**Pass:** the staging home page opens for the intended test account.
**Fail:** access is denied or the wrong account opens.
```

For a step the user truly must execute, use one action per numbered item, an exact linked URL/menu
path or copyable command/body, placeholders defined once, and bold one-line **Pass**/**Fail** signals.
Do not show a generic option menu, repeat already completed checks, or bury the single needed action
under background explanation.

## Several targets in one run

When the request names more than one issue or PR:

- Run the readiness probes once and reuse them for every target.
- Prove freshness per affected service; one deploy record can cover several merges in the same
  service when the deployed SHA descends from each merge SHA.
- Build the claim map per target, then add one **integration check** when targets touch the same
  entity, endpoint, screen, or flag, because two individually passing changes can still conflict.
- Share disposable fixtures where possible and keep one cleanup ledger for the whole run.
- Each target gets its own state. The run's overall state is the worst one, in the order
  FAIL > BLOCKED > WAIT > PARTIAL > PASS.

## Evidence artifact

Save `ai-plans/<branch>/staging-smoke.md` (or the next numbered file for a later completed run).
A target with no plan of the engineer's (someone else's PR, an issue without a branch here) is saved under
`$ROOT/.local/staging-smoke/<repo>-<pr or issue>/staging-smoke.md`. A multi-target run also writes
`$ROOT/.local/staging-smoke/<UTC>-batch.md` with the per-target table, the integration checks, and the
shared cleanup ledger, and links each target artifact. Each artifact contains:

1. target, UTC time, PRs, merge SHAs, and affected services;
2. deployment evidence and readiness probe summary;
3. claim → check → sanitized observation → result;
4. disposable data created and cleanup outcome;
5. remaining action, if any;
6. final state and paste-ready “good to go” reply.

Never copy raw command logs, secrets, connection details, full customer rows, or large response
bodies into the artifact.
