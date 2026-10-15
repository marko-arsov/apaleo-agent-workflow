# Staging smoke policy and playbook

After a PR merges to `master`, Jenkins builds and deploys to staging. “Good to go” means the merged
behavior was observed on a sufficiently fresh staging deployment and the relevant smoke passed. A
healthy endpoint or a repeated local test is not enough.

Marko has staging VPN and read access to staging core Postgres. Use that access through existing,
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
| Existing Bearer token | Check presence without echoing it; make the scoped request and redact sensitive output. |
| Missing token | Give one secure local setup step; never ask for the token in chat. |
| Existing staging DB profile/session | Run focused read-only SQL directly. |
| Missing/ambiguous DB route | State the exact connection/profile needed; do not guess a host, database, or password. |
| Subjective visual/business judgment | Capture what can be captured, then ask one precise question with Pass/Fail criteria. |

Browser testing is agent work whenever browser automation is available. Swagger is a discovery or
fallback UI, not mandatory manual labor; prefer an exact API request when practical.

## Action policy

Run these without a confirmation menu after the user asks for a staging smoke:

- repository/plan/PR inspection, fetches, deployment-metadata lookup, HTTP GET/HEAD probes;
- authenticated GET/HEAD through an existing session or token;
- read-only browser navigation and inspection;
- focused `SELECT`/`SHOW`/catalog queries in a server-enforced read-only transaction;
- low-risk reversible test writes in an unmistakable disposable account/property when the skill's
  autonomy conditions are all satisfied;
- creation of local smoke evidence.

Group everything else into one checkpoint after the safe work. Show the exact method/UI action,
target account/property, sanitized body, expected side effect, cleanup, and why it is necessary.
Do not ask again unless the action set materially changes.

If a supposedly rejecting request unexpectedly succeeds, treat it as a failure, inspect/clean up
only within the already authorized boundary, and do not try more mutation-capable variants.

## Resolving deployment freshness

Use the strongest available evidence, in order:

1. A deployment record names the merge SHA or a descendant SHA for the affected service.
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

1. an existing authenticated browser session;
2. an existing shell token or approved local API client profile;
3. user sign-in/MFA takeover in the opened browser;
4. one local secure-token setup step.

Check only whether a token exists; never print it. If the user must populate one in a shell, instruct
them to use a silent prompt rather than paste it into chat or a command saved in history:

```bash
read -r -s TOKEN && export TOKEN
```

Use the narrow scopes required by the smoke. If the correct staging client/scope is unknown, name
the missing scope or client purpose and direct the user to **Apps → API clients** or `#dev-tech`;
never invent a client secret.

## Read-only staging SQL

Use an already configured staging-core connection/profile. Do not put its value on the command line
or in evidence. Execute the focused query inside a server-enforced read-only transaction and roll it
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

For an automatically allowed write, all autonomy conditions in the skill must hold. Use a unique
marker such as `staging-smoke-SL-29-20260917T140500Z`. Before sending the write, persist a sanitized
**pending cleanup** entry in the current smoke artifact with the target, marker, and exact reversal.
Afterward, verify the record is gone or restored and mark cleanup complete. Do not automate writes
involving:

- real or customer-like accounts/properties;
- payments, invoices, fiscalization, financial posting, or irreversible workflows;
- outbound emails, webhooks, partner/integration calls, or third-party side effects;
- users, roles, permissions, OAuth clients/secrets, or shared configuration;
- bulk operations, migration/repair jobs, or unclear cascading behavior.

Those require one exact checkpoint, and some may be better left as a manual judgment step.

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

## Evidence artifact

Save `ai-plans/<branch>/staging-smoke.md` (or the next numbered file for a later completed run) with:

1. target, UTC time, PRs, merge SHAs, and affected services;
2. deployment evidence and readiness probe summary;
3. claim → check → sanitized observation → result;
4. disposable data created and cleanup outcome;
5. remaining action, if any;
6. final state and paste-ready “good to go” reply.

Never copy raw command logs, secrets, connection details, full customer rows, or large response
bodies into the artifact.
