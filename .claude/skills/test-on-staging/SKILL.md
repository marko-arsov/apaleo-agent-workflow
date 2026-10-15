---
name: test-on-staging
description: >-
  After an Apaleo PR merges, autonomously resolves the change, proves staging
  readiness, runs the safe browser/API/SQL smoke checks the current host can
  perform, and leaves only irreducible login, high-impact mutation, or human
  judgment as concise numbered steps. Use for /test-on-staging, staging smoke,
  or deciding whether a merged change is good to go.
disable-model-invocation: true
argument-hint: "[branch | HC-id | SL-id | PR url | 'the thing that just merged']"
model: sonnet
effort: medium
---

# Test on staging (execution-first post-merge smoke)

Answer “good to go?” with observed staging evidence. This is an execution skill, not an
instruction generator: finish every safe check available to the current host before asking Marko
to do anything.

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

- local/repository/PR inspection, fetches, public probes, and deployment-metadata lookup;
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

## 1. Resolve the merged change

Accept a branch, issue id, PR URL/number, or “the thing that just merged”.

1. Resolve explicit input with `resolve_feature_branch` from
   `$ROOT/.claude/skills/pipeline/root.sh`.
2. Read the matching `ai-plans/<branch>/` artifacts, then merged PR body/diff and changed tests.
3. For “the thing that just merged”, inspect recent merged PRs authored by Marko in every relevant
   repository and correlate them by head branch and plan. Select the single clear match.
4. Ask only when several plausible merged changes remain; show a short numbered list with repo, PR,
   title, head branch, and merge time.

Fetch/prune remotes as needed. Never switch a parked checkout, create a worktree, or edit product
repositories.

## 2. Build the minimum proof

Derive claims in this order: current plan → merged PR → diff/contracts → changed E2E names. Map each
user-visible claim to the smallest staging check that can prove it. Prefer one happy path and one
reject path when both are meaningful; do not replay a local test matrix against shared staging.

Before execution, know:

- the affected repositories/services and merge SHA for each;
- whether frontend/proxy and backend deployments must both be present;
- required flag, account/property, scopes, and seed data;
- exact UI/API/SQL checks, their side effects, cleanup, and Pass/Fail signals.

## 3. Prove readiness autonomously

Run independent read-only checks in parallel where practical:

1. Confirm every relevant PR is merged to `master` and its merge SHA is on `origin/master`.
2. Probe UI, `/health`, API base, and Swagger; retry transient `502`/`503`/network failures twice
   with bounded backoff without involving the user.
3. Exhaust available deploy evidence: CI/deploy status, browser-accessible Jenkins or observability,
   service version/build metadata confirmed by repository evidence, or the new behavior itself when
   it could not exist before the merge. A successful GitHub check or reachable `/health` alone does
   **not** prove freshness.
4. Confirm each required flag state without changing shared configuration automatically.

If staging is older or unavailable, stop behavioral writes and return **WAIT**. If freshness remains
unknown after the evidence search, continue any non-mutating proof that is still valid and return
**PARTIAL**, with one exact step for resolving the unknown. Never label the change ready from
reachability alone.

## 4. Execute the smoke

Use the strongest available surface:

1. Use controlled browser/UI testing for user-visible behavior. Capture screenshots when they add
   evidence. UI is not automatically “human only”.
2. Use the API contract and exact endpoint for API-only guards; prefer curl or an API client over
   asking the user to operate Swagger.
3. Use authenticated GETs automatically when an existing token/session is available without
   exposing it. For mutation-capable requests, apply the autonomy boundary above.
4. For schema/migration proof, run only focused `SELECT` queries inside a read-only transaction via
   an existing staging-core profile/session. Do not reveal connection details.
5. Before any allowed write, add its marker, sanitized target, and cleanup action to the evidence
   artifact as **pending**. Tag disposable records `staging-smoke-<issue>-<UTC>`, verify cleanup, and
   then mark it complete. Record leftovers as a failure or explicit cleanup action; never silently
   abandon them.

Classify each check from observed output: **PASS**, **FAIL**, **NOT RUN**, or **INCONCLUSIVE**. A
request that was expected to reject but unexpectedly succeeded is a failure and may require cleanup;
do not continue similar writes.

## 5. Persist evidence

Write `$ROOT/ai-plans/<branch>/staging-smoke.md`; use `staging-smoke-<n>.md` for a later distinct
smoke so completed evidence is not overwritten. Include:

- change/PRs, merge SHAs, target, time, and deploy-freshness evidence;
- claim-to-check mapping and sanitized observed results;
- created data and verified cleanup;
- remaining human action, if any, with no secrets;
- final state: **PASS**, **PARTIAL**, **WAIT**, **FAIL**, or **BLOCKED**.

On continuation, read the newest smoke artifact first. Resolve any **pending cleanup** before a new
write, reuse still-current evidence, and rerun only time-sensitive readiness or unfinished checks.
Do not make the user repeat the branch, approval, sign-in state, or completed observations.

## Chat presentation

Render normal Markdown, never raw command output, ANSI, or a transcript. Use clickable URLs and file
links; in Codex use absolute local paths and open the completed evidence artifact in the Codex panel
when useful. Attach/embed screenshots when the host supports them and they materially prove the
result.

```markdown
## Staging smoke — PASS | PARTIAL | WAIT | FAIL | BLOCKED

| Check | Result | Evidence |
|---|---|---|
| Deployment | PASS | `<sha>` is deployed … |
| Main behavior | PASS | … |
| Reject path | PASS | … |

### Completed
- …

### Action needed
1. First remaining action. (Omit this section when none remains.)
2. Next action, only when needed.

**Pass:** …
**Fail:** …

### Verdict
Ready / not ready, and why.

**Paste-ready:** “Yes — …” or “Not yet — …”
**Evidence:** `<absolute clickable staging-smoke.md path>`
```

Do not show an “offer” block after checks have run. Keep status commentary brief and reserve the
full table for the final result.
