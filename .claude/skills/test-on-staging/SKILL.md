---
name: test-on-staging
description: >-
  After one or more Apaleo PRs merge, decides whether they are safe to deploy to
  production: checks the Jenkins master pipelines and the staging deployment for
  those commits, runs a few focused smoke checks per change (not the E2E suite)
  through the Apaleo MCP, API, browser, and read-only SQL, and ends with one
  verdict: safe to deploy, quick fix first, revert, or wait. Use for
  /test-on-staging, staging smoke, or "is this good to go to prod?".
disable-model-invocation: true
argument-hint: "[branch | HC-id | SL-id | PR url | 'the thing that just merged'] [more ids or PRs…]"
model: sonnet
effort: medium
---

# Test on staging (is it safe for production?)

Answer one question with observed evidence: **can these merged changes go to production?** Three
things decide it, in this order: the pipelines for those commits passed, staging runs a revision
that contains them, and the changed behaviour works on staging. This is a smoke, not a regression
run: a few focused checks per change, never a replay of the E2E suite. It is an execution skill:
finish every safe check available to the current host before asking Marko to do anything.

Read `$ROOT/.claude/skills/references/staging-smoke.md` first. Load `feature-flags.md` only when the
change is gated.

## Host and capability routing

Preferred host: **Cursor Grok** — `test-on-staging-cursor` (`grok-4.7-high`). Direct
invocations in Codex or Claude Code stay in the current host; do not hand off merely to run this
skill. Never use Cursor on-demand Claude. Read `references/model-routing.md` for routing policy.

Inspect the tools already available in the current host before declaring a step manual:

- use terminal, GitHub, connected CI/observability, and browser/computer-control tools directly;
- if a browser or tab was mentioned, use that surface and its existing authenticated session;
- let the user take over only for sign-in, MFA, CAPTCHA, a missing secret, or a genuinely subjective
  visual/business judgment, then resume the smoke;
- never ask the user to run a command, open a page, or copy data that the agent can handle itself.

## Autonomy and authorization

A direct request to run `/test-on-staging` authorizes:

- local/repository/PR inspection, fetches, public probes, deployment-metadata lookup, and
  read-only Jenkins API calls through `references/jenkins-readonly.sh`;
- authenticated read-only HTTP requests and read-only staging SQL when an existing unambiguous
  session/profile is available;
- browser navigation and read-only UI inspection in an existing session;
- low-risk, reversible test writes only when all of these are true: the proof requires the write,
  the target is an unmistakable DEMO/test account or property, the data gets a unique smoke marker,
  no money/PII/external communication/security/admin/shared configuration is involved, and cleanup
  is known and verified;
- writing the local `staging-smoke.md` evidence artifact.

Do not pause for an option menu or confirmation for those actions. Before anything outside that
boundary, finish the safe work and ask **once** with the exact action set, target, side effects,
cleanup, and reason. Always require that checkpoint for destructive operations, shared feature-flag
or configuration changes, real/customer-like accounts, payments, emails/webhooks/external
integrations, permission changes, or uncertain cleanup. Never mutate the staging database.

If the user requested “instructions only”, do not perform authenticated or mutating checks; public
readiness probes and local evidence inspection remain safe unless they also opted out of those.

## 1. Resolve the merged changes

Accept one or more branches, issue ids, PR URLs/numbers, or “the thing that just merged”, in any
mix (for example `SL-126 SL-122 apaleo/apaleo#13219`). Each resolves to one **target**.

1. Resolve each explicit input with `resolve_feature_branch` from
   `$ROOT/.claude/skills/pipeline/root.sh`. An issue resolves to every linked PR across
   repositories; a PR resolves to its companions with the same head branch.
2. Read the matching `ai-plans/<branch>/` artifacts, then merged PR body/diff and changed tests.
   A target without a plan here (someone else's PR, an issue with no local branch) is derived from
   the issue text, the PR body and diff, and its tests.
3. For “the thing that just merged”, inspect recent merged PRs authored by Marko in every relevant
   repository and correlate them by head branch and plan. Select the single clear match.
4. Ask only when an input stays ambiguous; show a short numbered list with repo, PR, title, head
   branch, and merge time.
5. An unmerged PR is not on staging: mark that target **WAIT** with the reason and continue with the
   others.

Fetch/prune remotes as needed. Never switch a parked checkout, create a worktree, or edit product
repositories.

## 2. Build the minimum proof

Derive claims in this order: current plan → merged PR → diff/contracts → changed E2E names. Map each
user-visible claim to the smallest staging check that can prove it. Budget: **one to three checks
per target**, usually one happy path plus one reject or regression path. The E2E tests already ran
in CI; their names only tell you what matters, they are not a list to execute. Never replay a local
test matrix against shared staging.

With several targets, follow “Several targets in one run” in `staging-smoke.md`: one claim map per
target, shared readiness and fixtures, and an integration check wherever targets touch the same
entity, endpoint, screen, or flag.

Before execution, know:

- the affected repositories/services and merge SHA for each;
- whether frontend/proxy and backend deployments must both be present;
- required flag, account/property, scopes, and seed data;
- exact UI/API/SQL checks, their side effects, cleanup, and Pass/Fail signals.

## 3. Pipelines and deployment

Run independent read-only checks in parallel where practical. Jenkins needs the VPN; use
`$ROOT/.claude/skills/references/jenkins-readonly.sh` (GET only, never prints the token):

1. Confirm every relevant PR is merged to `master` and its merge SHA is on `origin/master`.
2. **Pipeline for each merge.** `jenkins-readonly.sh build-for <repo> <merge-sha>` gives the first
   master build that contains it; `builds <repo> 10` gives what came after. A green master build
   deploys to staging. Record per repository:
   - the first build with the commit and its result;
   - the latest master build and its result (a later green build can still ship a commit whose
     first build failed; a later red build can block it);
   - for any red build, `console <repo> <build> 120`, and whether the failure comes from these
     PRs, from another commit, or from infrastructure (flaky test, agent, network).
   Also read the merge commit's GitHub checks (`gh api repos/apaleo/<repo>/commits/<sha>/status`
   and `check-runs`).
3. **Staging freshness.** The newest green master build containing the merge proves it reached
   staging. When the pipeline cannot be read, fall back to deploy metadata or to behaviour that
   could not exist before the merge, marked as inferred.
4. **What production runs.** `jenkins-readonly.sh prod <param>` for each affected service
   (`apiVersion` for `apaleo`, `uiVersion` for the UI, `identityVersion`, …) gives the commit in
   production. A production deploy ships **every** commit between that and the candidate, not only
   these PRs: list the other commits in that range (`git log <prod>..<candidate> --oneline`) and
   flag `[DB-MIGRATION]` commits, other teams' changes, and anything already known to be broken.
5. Probe UI, `/health`, API base, and Swagger; retry transient `502`/`503`/network failures twice
   with bounded backoff without involving the user.
6. Confirm each required flag state without changing shared configuration automatically.

A successful GitHub check or a reachable `/health` alone does **not** prove freshness.

If staging is older or unavailable, stop behavioral writes and return **WAIT**. If freshness remains
unknown after the evidence search, continue any non-mutating proof that is still valid and return
**PARTIAL**, with one exact step for resolving the unknown. Never label the change ready from
reachability alone.

## 4. Execute the smoke

Use the strongest available surface:

1. Use controlled browser/UI testing for user-visible behavior. Capture screenshots when they add
   evidence. UI is not automatically “human only”.
2. Use the Apaleo MCP for API checks and test-data setup, then `references/staging-api.sh` for
   endpoints the MCP lacks (“API surfaces: MCP, then helper” in `staging-smoke.md`). Check the active
   account first; automatic reversible writes are allowed only on Marko's test account (`ZGMD`
   unless he names another). Use the API contract and exact endpoint for API-only guards rather
   than asking the user to operate Swagger.
3. Use authenticated GETs automatically through the MCP, the helper, or an existing token/session,
   without exposing credentials. For mutation-capable requests, apply the autonomy boundary above.
4. When the expected behavior depends on a feature flag, record its per-environment state for the
   test account before judging the result. A flag that differs from production makes a staging
   PASS conditional; say so in the verdict.
5. For schema/migration or data-state proof, run only focused `SELECT` queries with
   `references/staging-sql.sh` (IAM login, read-only session and transaction; "Read-only staging
   SQL" in `staging-smoke.md`). If it reports no network, ask once for the staging VPN. Fall back to
   the Rider MCP only when the helper cannot run; if that is refused too, mark the check
   **NOT RUN** and continue. Do not reveal connection details.
6. Before any allowed write, add its marker, sanitized target, and cleanup action to the evidence
   artifact as **pending**. Tag disposable records `staging-smoke-<issue>-<UTC>`, verify cleanup, and
   then mark it complete. Record leftovers as a failure or explicit cleanup action; never silently
   abandon them.

Classify each check from observed output: **PASS**, **FAIL**, **NOT RUN**, or **INCONCLUSIVE**. A
request that was expected to reject but unexpectedly succeeded is a failure and may require cleanup;
do not continue similar writes.

## 5. Production verdict

Combine pipeline, deployment, and smoke results into exactly one recommendation:

| Verdict | When |
|---|---|
| ✅ **Safe to deploy to production** | Every target PASS; the pipelines that ship them are green; staging runs a revision containing them; nothing in the shipped range is broken or unreviewed for risk |
| 🔧 **Quick fix first** (default when something is broken) | The cause is understood, the fix is small and low risk, the damage is contained (no data corruption, money, fiscal, or security impact), and nothing else urgent waits on `master` |
| ⏪ **Revert** | Data corruption, money, fiscal, security, or tenancy impact; widespread errors; cause unclear; the fix is not small; a bad migration; or the breakage blocks other teams' production deploys while a fix is prepared |
| ⏳ **Wait** | Not merged, pipeline still running, or staging not yet on the revision |
| 🚫 **Blocked** | Required access is missing and no valid proof remains |

With **Safe**, give the exact production input: Jenkins `Deployment/Core`, the parameter per
service with the 7-character SHA, the other commits that ship with it, migrations to watch (the
30-second startup limit), and what to watch afterwards (#operations, Datadog errors for the changed
endpoints). Never trigger the deployment; Marko or the release owner does.

With **Quick fix**, name the failing behaviour, the suspected cause with evidence, the smallest fix,
and that it goes through `/specify` and `/implement` like any bugfix. With **Revert**, give the
merge commit, the revert plan (`git revert -m 1 <merge-sha>` on a new branch in a worktree, then a
PR; never push to `master`), and who to tell. Create no branch, commit, or PR without an explicit
yes.

## 6. Persist evidence

Write `$ROOT/ai-plans/<branch>/staging-smoke.md`; use `staging-smoke-<n>.md` for a later distinct
smoke so completed evidence is not overwritten. A target without a local plan, and the batch summary
of a multi-target run, go under `$ROOT/.local/staging-smoke/` as described in `staging-smoke.md`.
Include:

- change/PRs, merge SHAs, target, time, and deploy-freshness evidence;
- claim-to-check mapping and sanitized observed results;
- created data and verified cleanup;
- remaining human action, if any, with no secrets;
- pipeline and production-range evidence;
- final state: **PASS**, **PARTIAL**, **WAIT**, **FAIL**, or **BLOCKED**, and the production verdict.

On continuation, read the newest smoke artifact first. Resolve any **pending cleanup** before a new
write, reuse still-current evidence, and rerun only time-sensitive readiness or unfinished checks.
Do not make the user repeat the branch, approval, sign-in state, or completed observations.

## Chat presentation

Render normal Markdown, never raw command output, ANSI, or a transcript. Use clickable URLs and file
links; in Codex use absolute local paths and open the completed evidence artifact in the Codex panel
when useful. Attach/embed screenshots when the host supports them and they materially prove the
result.

```markdown
## Production verdict — ✅ Safe to deploy | 🔧 Quick fix first | ⏪ Revert | ⏳ Wait | 🚫 Blocked

<One sentence why.>

| Check | Result | Evidence |
|---|---|---|
| Pipeline (`<repo>` master #<n>) | PASS | first build with `<sha>`: #<n> SUCCESS; latest #<m> SUCCESS |
| Staging deployment | PASS | #<n> deployed `<sha>` … |
| Main behavior | PASS | … |
| Reject path | PASS | … |

### Ships with it
Production runs `<prod-sha>`; deploying `<candidate-sha>` also ships: <commits, migrations flagged>.

### Deploy to production (only when safe)
Jenkins `Deployment/Core`: `<param>` = `<7-char sha>`. Watch #operations and <Datadog view>.

### Completed
- …

### Action needed
1. First remaining action. (Omit this section when none remains.)
2. Next action, only when needed.

**Pass:** …
**Fail:** …

### Verdict
Ready / not ready, and why.

**Paste-ready:** “Safe to deploy — …”, “Not yet, quick fix first — …”, or “Reverting — …”
**Evidence:** `<absolute clickable staging-smoke.md path>`
```

With several targets, put a summary table first, then one section per target in the format above,
then the integration checks and the shared cleanup ledger:

```markdown
## Production verdict — <overall verdict> (<n> targets)

| Target | PRs | Pipeline | Staging | Smoke | Key evidence |
|---|---|---|---|---|---|
| SL-126 | apaleo#… | #185 SUCCESS | deployed | PASS | … |
| SL-122 | apaleo#… | running | not yet | WAIT | … |

### Integration checks
| Check | Result | Evidence |
|---|---|---|
```

Do not show an “offer” block after checks have run. Keep status commentary brief and reserve the
full table for the final result.
