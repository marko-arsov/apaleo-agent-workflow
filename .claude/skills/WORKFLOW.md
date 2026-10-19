# Apaleo AI implementation workflow

This is the human map. `AGENTS.md` owns always-on workspace facts, `references/` owns focused
policy, and each `SKILL.md` owns one procedure. Product repositories are outside this workflow's
configuration surface.

## Plan, iterate, then execute

`/specify` is the only plan author and writes no product code. It researches established patterns,
interviews until consequential choices are settled, and confirms stages and routes. The complete
plan set under `ai-plans/<branch>/` is:

- `prompt.md`, `product.md`, `implementation.md`, `deferred-scope.md`;
- validated `pipeline.json` with context contracts, path boundaries, exact test commands,
  acceptance-criterion mappings, risk, and diff budget.

Every acceptance criterion names a test, its path, its command, and observed-output pattern.
Plans may be revised in place while iterating on a task, or captured as complete `v2/`, then `v3/`
snapshots. The runner archives prior state and rebinds automatically to the latest complete plan.
The initial prompt is a hypothesis: `/specify` challenges gaps or flawed logic and proposes the
smallest correct alternative before the definition is confirmed. When that definition materially
changes Linear, it updates the issue after writing the plan files and after action-specific approval.

## Fixed stage order

`/specify` selects a subset without changing this order:

```text
implement-tests? → implement → review? → commit-and-push? → draft-pr?
```

| Stage | Contract |
|---|---|
| `implement-tests` | Required when tests change. Test paths only; produces assertion-level `red-proof.md`. |
| `implement` | Always required. Builds product code, then runs the complete verify/fix procedure and named commands in the same session. |
| `review` | Optional independent fresh-context review against the specification, tests, rules, and semantic reuse/DRY. In the pipeline it receives the current `/add-rule` inventory, applies safe plan-authorized corrections and same-behavior improvements, verifies narrowly, and reruns the deterministic rule scan; Tier-1 violations must be repaired, while plan/behavior findings remain advisory. Direct `/review <branch> [focus]` is check-only and asks for confirmation when the review basis or solution is ambiguous, then hands confirmed changes to `/specify` and `/implement`. |
| `commit-and-push` | Optional deterministic safety scan, commit, and non-force push. |
| `draft-pr` | Optional deterministic draft PR; requires `commit-and-push`. |

`/test-and-fix` remains a reusable procedure loaded by `/implement`, and a manual after-PR tool. It
is not a top-level stage. Version-1 manifests are translated in memory; their files remain unchanged.
Implementation and publish safety gates fail closed; review is advisory.

## Simple manual lane

For a small, contained follow-up—especially an addition to an already-developed issue—use:

```text
/specify <task or HC-id>
/implement <task or branch>
```

This is a first-class lane, not a reduced-quality pipeline run: `/specify` writes a concise,
decision-complete plan and `/implement` owns tests plus implementation in one session. It creates no
`implement-tests` handoff, pipeline run, review stage, or publish queue. `/implement` still follows
the established-pattern, path, authorization, and test rules; it does not commit or push.

## Bugfix posture

Keep the same lanes and stages. A defect plan needs four compact facts:

1. Expected behavior
2. Current observable failure and reliable reproduction
3. Evidence-based suspected cause and affected scope
4. A regression check that fails before the fix and passes afterward

For an isolated bugfix in the manual lane, `/implement` defaults to:

```text
reproduce → add regression test/check → prove it fails for the defect →
fix → rerun it green → run focused verification
```

Do not create a separate `implement-tests` stage for small fixes. Record concise before/after
evidence in `progress.md`. The regression check must demonstrate the original bad behavior, not
merely execute the changed code. If automation is genuinely impractical (flaky third-party
dependency, one-off corrupted production data), document why and use the strongest repeatable
alternative: a focused API/script check, fixture, or local repro. That is an exception, not a
loophole.

| Situation | Recommended lane |
|---|---|
| Isolated defect, deterministic reproduction, established local pattern | Manual |
| Narrow feature follow-up with an established local pattern | Manual |
| Regression needs several test layers, or the cause is uncertain | Full pipeline |
| Security, billing, tenancy/OPA, schema, public contract, data correction | Full pipeline + review |
| Broad or multi-repository work, migrations, or automated publishing wanted | Full pipeline |

The full pipeline already has the ideal bugfix form: test-only red proof → implementation →
independent review → publishing. Lane choice remains guidance: the user confirms it.

## Default routes and fresh boundaries

`/update-models` refreshes available models and proposes model/effort defaults for Apaleo's
machine scope, this workspace, or both. It confirms the providers and exact settings diff.
Agent Flow remains independent. The shared evaluator is a versioned local snapshot, not a live
link to another workflow. See `references/model-policy.md` for the settings and evidence contract.

Every `/specify`, including manual work, evaluates the selected stages offline with no extra
model call. Balanced model-specific effort is preferred; difficult or risky stages can escalate.
Maximum effort requires an explicit choice. Missing optional metadata adds no questionnaire.
Existing pins remain fixed, and approved plans retain their saved routes after defaults change.
Review stays optional, and commit/push/PR stages remain mechanical. Legacy tables are retained
only for initial fallback and compatibility with older plans.

Every AI stage, retry, and fallback starts a fresh provider process; only a genuine
`PIPELINE_INPUT_REQUIRED` pause resumes that same stage session.

The prompt prefix is byte-stable for one plan revision: root `AGENTS.md`, then the plan set. The
stage skill, permitted references, task, diff/report pointers, and run-specific data are appended
after `# Stage-specific tail`. Timestamps, run ids, and pids never enter the stable prefix.

## Context and completion contracts

`pipeline.json.context_contracts` declares each AI stage's reads, denied inputs, and writes. The
runner supplies only the declared prompt inputs and enforces write paths and report postconditions.
Provider CLIs still have host filesystem access; `references/security-boundary.md` records that
important isolation gap instead of pretending prose is an OS sandbox.

The deterministic gates verify outcomes rather than stage claims:

- `implement-tests` cannot change product paths; every mapped test must reach an assertion-level
  failure, never a compile/setup failure;
- an interrupted `implement-tests` handoff with valid current `red-proof.md` and
  `tests-implementation-<n>.md` is re-verified and marked complete on normal resume, avoiding
  needless test-author reruns;
- `implement` runs and parses every named command, maps every acceptance criterion to an existing
  named test, and records the exact output;
- the current diff fingerprint binds reusable evidence; a changed diff invalidates it;
- diff budget overshoot is advisory (the default planning threshold is 4,000 changed lines);
  secrets, blocking conventions, missing implementation traceability, or enabled mutation failures stop the run;
- plan revisions are preserved as audit history and take effect automatically on the next run;
- pre-commit uses fast diff-scoped convention/Semgrep and secret/gitleaks checks;
- review never receives implementation reasoning and audits ACs, tests, correctness, then
  rules/semantic-DRY in that order. It receives the registered rule inventory and runner-verified
  post-review deterministic scan; pipeline review applies only safe in-plan corrections and
  narrow verification, and must eliminate Tier-1 scanner findings. Direct review is no-edit.
  Missing evidence and plan/behavior findings remain advisory;
- `dotnet stryker --since:main` is opt-in only for authorization or billing risk.

Semgrep and gitleaks are used when installed; deterministic local fallbacks still run when they are
absent. Advisory convention findings are recorded in verification evidence without blocking.

## Tiered rule capture

`/add-rule` is the only user-facing entry point. It asks whether a deterministic script can decide
from the diff, rather than letting importance or operator preference choose the tier:

1. **Tier 1:** mechanically detectable and every match is wrong. Blocking hook and/or architecture
   proposal through the internal `/add-convention` path.
2. **Tier 2:** mechanically detectable with unenumerated legitimate exceptions. Semgrep/detector
   warning in stage evidence; later promotion to Tier 1 is explicit.
3. **Tier 3:** genuinely not mechanically checkable. Scoped rule/reference prose only—never global
   `AGENTS.md`.

All tiers have reviewable metadata under `.claude/conventions/rules/`. A Tier-3 rule's second
recorded violation forces escalation to Tier 1 or 2. There is no force-Tier-3 override. Approved
mechanical exemptions require an exact path and reason in `allowlist.json`.

The worked Tier-1 example blocks ASP.NET authorization policy primitives in C# outside the OPA
integration layer, exits `2`, and directs the agent to Rego/data artifacts. `/address-pr-comments`
counts matched human convention comments once per URL; `/prune-context` proposes six-month unused
rule deletion and repeated Tier-3 escalation. Neither skill applies maintenance proposals unattended.

## Untrusted inputs and security boundary

Ticket text, PR comments, CI logs, and foreign diffs pass through `pipeline/untrusted_input.py`:
zero-width/control characters and HTML comments are removed, content is delimited as data, and
injection-shaped imperatives require confirmation. Large logs are also capped by
`summarize_output.py` before model use.

This is a secondary control. The audit explicitly reports that provider CLIs inherit host
credentials, use broad tool permissions, and have unrestricted outbound network access. No local
prompt sanitizer fixes that three-way coexistence. Run:

```bash
python3 "$ROOT/.claude/skills/pipeline/workflow_audit.py" --root "$ROOT"
```

## Run and maintain

Simple manual work needs only:

```bash
/specify HC-3333
/implement HC-3333
```

Use the full pipeline when its detached stages and publish automation are wanted:

```bash
/implement-pipeline HC-3333 --dry-run
/implement-pipeline HC-3333 --preflight-only
/implement-pipeline HC-3333
/implement-pipeline HC-3333 --status
/implement-pipeline HC-3333 --watch
/implement-pipeline HC-3333 --answer 'the required answer'
```

The worker may detach; its watcher is shell-only and adds no model tokens. Run evidence lives in
`.local/pipeline-runs/`, state in `.local/pipeline-state/`, and verification logs in
`.local/pipeline-verification/`.

After a draft PR, use `/address-pr-comments`, `/diagnose-ci`, manual `/test-and-fix`, and
`/test-on-staging`. Nothing posts comments, requests review, approves, or merges as the user without
explicit authorization.

When a merged migration should be applied on production by hand, `/migration-script`
generates that SQL from the parked master checkout with the production runbook command
(`dotnet ef migrations script <last-applied> --output Migration.sql`, no `-i`), then
`SET statement_timeout = 0;` at the top. It does not apply the script.

`/test-on-staging` answers "is it safe to deploy to production?" for one or more merged changes
(issues, PRs, or branches in any mix). It reads the Jenkins master pipelines for those commits
(`references/jenkins-readonly.sh`, GET only), proves the staging deployment, lists what else ships
from the production commit onward, and runs one to three focused smoke checks per change, never the
E2E suite. It ends with one verdict: safe to deploy (with the exact `Deployment/Core` input), quick
fix first, revert, wait, or blocked. It runs read-only plus tightly bounded disposable-account
browser/API/SQL checks without an option-menu pause. API checks
and test data go through the Apaleo MCP first, then `references/staging-api.sh`; automatic writes
happen only on the configured test account. Several targets share readiness probes, fixtures, and one
cleanup ledger, and get an integration check where they touch the same thing. It uses browser control when the current host provides it and leaves
only sign-in/MFA, high-impact shared-state changes, missing access, or genuine human judgment as one
short step-by-step handoff. Reachability, deployment freshness, and ticket-specific verification are
reported separately; only complete observed proof is **PASS**.

### Chat output

Mechanical skills use their scripts as the source of truth but translate routine command output into
a concise, decision-oriented Markdown result. Raw stdout is available on request and brief error
excerpts remain appropriate when they explain a failure. Review skills render their prescribed
orientation and findings as normal Markdown, not terminal transcripts.

## Support rotation

`/support-rotation <Slack thread | Linear issue>` is the local second pass on one
`#product-inquiries` inquiry. The cloud agent (`rotation-processor`, Cursor Cloud, started by n8n)
does the first static pass and posts an Outcome on the Linear issue. The local skill:

1. reads the thread and issue, classifies the cloud state (Outcome, in progress, missed, no summon),
   and reads that team's memory notes read-only;
2. writes competing hypotheses from the thread before reading the Outcome;
3. verifies the Outcome as a claim ledger (re-read cited code on `origin/master`, arithmetic,
   flags, recent history, a second screen computing the same number);
4. separates the remaining hypotheses with the cheapest decisive step: a precise question, the flag
   state, or a staging reproduction with a control (Apaleo MCP first, then `staging-api.sh`);
5. ends with next steps: the exact questions to post when information is missing, a "tell your
   team lead now" call with a draft message when it is urgent, the reply with fix steps when the
   cause is known, and an offer to create a fix issue and an improvement issue in Linear;
6. drafts the Slack reply, lead or owner messages, a Linear `## Verification` plus `## Feedback`
   comment, the issues, and a corrected team-memory note.

Reads and straightforward reversible writes on the configured test account need no confirmation; shared
configuration, flags, money, deletions, or uncertain cleanup do. Nothing is posted, moved, or pushed
without a yes. Production is never written. Details: `references/support-rotation.md`.

## Cost classification

| Item | Cost |
|---|---|
| 1. Tiered `/add-rule` and OPA example | Neutral in normal runs; rule authoring is opt-in |
| 2. Pruned/global-vs-scoped instructions | Reducing on every model call |
| 3. Cache-aligned prompt prefix | Reducing where provider prefix caching applies |
| 4. Data context contracts | Neutral |
| 5. Suggested test-author route diversity | Neutral; no extra model call |
| 6. Parsed verification, traceability, budgets, scanners | Neutral model cost; mutation is opt-in |
| 7. PR-comment feedback classification | Neutral; part of the existing analysis call |
| 8. Untrusted-input handling and boundary audit | Neutral; deterministic |
| 9. Verify/fix folded into `implement` | Reducing: one fewer provider session/stage |
| 10. Checkpoint audit, pruning, tests, maintenance | Neutral; manual/deterministic |
| Advisory convention and reuse/DRY review evidence | Neutral; existing review call |

No item adds a recurring model call.

## Safety invariants

- Feature code only under `worktrees/<branch>/`; parked mains stay on `master`.
- Repository inventory is `apaleo`, `development`, `identity`, `agent-skills`, `angular-api-proxy`.
  `apaleo` is the default; the other four are opt-in and are never created for ordinary backend
  work. `$ROOT` resolution depends only on `AGENTS.md` + `apaleo/` + `development/`. Another
  `apaleo` org repository attaches for one branch with `--with <name>`: an existing sibling
  checkout is reused, and a missing one is mirrored under `.repos/`. Later stages see it only
  when that branch recorded it.
- Never push a base branch or force-push.
- Never weaken, skip, delete, or quarantine a failing test.
- Never run destructive shared-environment E2E without confirmation.
- Never commit the local Identity-scope workaround, secrets, or AI attribution.
- Plans remain complete and auditable; workflow configuration never edits application repositories.

## Maintenance log

- 2026-10-19: `/publish-workflow` opens the pull request from `origin/master` even when
  the checkout is on another branch. It carries uncommitted edits and commits that
  are not on `origin/master`. It stops when those changes do not apply cleanly.

- 2026-10-19: Added `/support-rotation`, the local verifier for the cloud support agent. It
  reuses the agent's Outcome and team memory instead of repeating them, checks each claim, and
  spends its effort on staging reproduction, flag state, and targeted questions. Linear comments
  (`## Verification`, `## Feedback`) and the `data/engineering-tech-support` memory notes are the
  shared record. `staging-api.sh` reads untracked client credentials and never prints them. Per-engineer
  values (test account, property, database user) live in the untracked `.local/user-config.json`
  (template `references/user-config.example.json`); the repository holds no personal setup, and
  `staging-api.sh` refuses writes outside the configured test account. `/support-rotation` tells
  Zendesk inquiries (bot-posted, Dispatcher summon, the named CS agent as the asker, follow-ups as
  bot messages) from direct ones and addresses its reply to the right person.

- 2026-10-19: `/test-on-staging` accepts several issues, PRs, or branches in one run and uses the
  Apaleo MCP, then the shared `references/staging-api.sh`, for API checks and test data. Automatic
  reversible writes are limited to the configured test account (`staging.testAccount`). Multi-target runs share
  readiness and cleanup, add integration checks, report a per-target table with the worst state as
  the overall result, and write a batch summary under `.local/staging-smoke/`.

- 2026-10-19: `/test-on-staging` now decides production readiness: Jenkins master pipeline per
  merge (first and latest build), staging freshness, the commit range a production deploy would
  ship, a small smoke budget instead of E2E flows, and one verdict (safe, quick fix, revert, wait,
  blocked). `/support-rotation` ends with explicit next steps: thread questions, team-lead
  escalation criteria, the reply with fix steps, and offered fix and improvement issues.

- 2026-10-19: Read-only staging SQL in `/test-on-staging` and `/support-rotation` goes through
  `references/staging-sql.sh`: `psql` with an IAM token for the engineer's database user, a statement
  allowlist, `default_transaction_read_only=on`, and a read-only transaction. It needs the staging
  VPN and reports a clear exit code when it is down. The Rider MCP (read-only data source, SQL
  tools allowed without a prompt) is the fallback, because Rider refused MCP queries in testing.

- 2026-10-15: `/publish-workflow` pull request bodies are a few short bullets for the
  commands, pipeline, tests, and docs that changed.

- 2026-10-15: A branch can attach any other `apaleo` org repository with
  `worktree-start --with <name>`. The five parked clones stay as they are. An existing
  `$ROOT/<name>` checkout of that repository is the worktree source; otherwise the first
  attach creates a bare mirror at `$ROOT/.repos/<name>.git`. `/specify` confirms the name
  and records `extra_repos`. Commit, push, sync, draft PR, checkout, list, remove, and
  pipeline verification include that checkout and ignore an unlisted directory beside it.

- 2026-10-15: Added `/update-workflow`. On a clean `master` it fast-forwards this
  checkout from `origin/master` and runs `install.sh` so new commands are
  registered. It stops when the checkout is dirty, on another branch, or cannot
  fast-forward. It does not touch product repositories.

- 2026-10-15: `/migration-script` now follows the production runbook. It runs
  `dotnet ef migrations script <last-applied> --output Migration.sql` with no `-i`
  and no end id, then writes `SET statement_timeout = 0;` as the first line
  without a byte-order mark. `task ef:migration-script` stays the `-i` source
  for the flattened PR review copy.

- 2026-10-15: Added `/publish-workflow`. It commits uncommitted workflow files on a new
  branch from `origin/master`, pushes, and opens a pull request. A missing summary
  is derived from the changed files. It does not run by itself, and it refuses
  product repositories, plans, worktrees, and secrets.

- 2026-10-15: Published the workflow as the private checkout
  `marko-arsov/apaleo-agent-workflow`. That checkout is the workspace parent.
  Product repositories, worktrees, plans, and run state stay untracked. `install.sh`
  registers the host commands. Later workflow edits are branches and pull requests.

- 2026-10-14: Added independent model settings, native catalogue refresh and an offline per-spec
  evaluator shared as a versioned component. Model-specific effort uses balanced defaults;
  approved snapshots and legacy suggestions remain stable. `/update-models` confirms scope and
  exact changes, and does not alter native host preferences or Agent Flow settings.

- 2026-10-14: `/migration-script` generates the production SQL for a merged apaleo migration
  from the parked master checkout (`task ef:migration-script`, then
  `SET statement_timeout = 0;`). The flattened PR script stays the review copy.
  Tier-3 `db-migration-production-apply` now says the executed file is that
  post-merge script. The skill does not apply, commit, or push it.

- 2026-10-14: Draft PR titles ignore process headings (`Prompt and research`, `Decisions and
  research`, `Product`) and use the plan's imperative summary, the quoted Linear title, or a
  plan-stated `[DB-MIGRATION]` title. Descriptions read `## Outcome` as well as
  `## Observable outcome`, and `In:` scope as well as `### In`. A plan `migration.sql` and
  `## Production apply` section are pasted into the Changes section. Tier-3 rule
  `db-migration-production-apply` requires that section: staging applies at startup, and
  production is manual only when the migration can exceed the 30-second startup timeout or
  lock a hot table.

- 2026-09-22: Moved the default Cursor Grok route from `cursor-grok-4.6-high` to `grok-4.7-high`.
  Cursor's 4.7 ids omit the `cursor-grok-` prefix. Implement, review Grok fallbacks, and Cursor
  agent tiers follow the same family (`low-fast`, `medium`, `medium-fast`, `high`). Already
  confirmed `pipeline.json` routes stay on their recorded model.

- 2026-09-18: Fixed mechanical feature-branch resolution so repository-named source directories
  such as `development/apaleo` cannot be mistaken for nested branches. `/commit-and-push` now
  explicitly accepts an issue id such as `sl-100`, delegates resolution to the script, and operates
  on every attached repository without asking the user to choose a repo. The regression test keeps
  this zero-model-call publish path deterministic. `/open-rider` uses the same direct issue-id
  resolution and defaults unambiguously to the resolved worktree's `apaleo/Apaleo.sln`; other
  attached repositories do not change the target unless the user explicitly asks.

- 2026-09-17: Made `/test-on-staging` execution-first across Codex, Cursor, and Claude Code. The
  skill now runs all available read-only checks and narrowly bounded reversible DEMO/test-data
  smoke actions without an option-menu pause, uses browser control instead of treating UI as inherently
  manual, exhausts deploy/version/behavior evidence before asking about freshness, and groups any
  high-impact staging mutation behind one exact checkpoint. Its Markdown result now has stable
  PASS/PARTIAL/WAIT/FAIL/BLOCKED semantics, concise human takeover steps, sanitized evidence, and
  explicit cleanup tracking.

- 2026-09-15: Treated `angular-api-proxy` as a first-class **optional** worktree repo, opt-in only
  via `--with-angular-api-proxy` / `--angular-api-proxy-only`. Commit, push, draft-pr, worktree
  start/list/remove, checkout, branch resolution, and pipeline manifests now accept it exactly as
  they do development/identity/agent-skills; it is never created for ordinary backend work, and
  `$ROOT` resolution still depends only on `AGENTS.md` + `apaleo/` + `development/`. Generated
  clients under `modules/**` are regenerated by the canonical flow, never hand-edited, and the
  parked `$ROOT/angular-api-proxy` clone is never edited directly. Two duplicate repo lists were
  removed in the process: `pipeline/root.sh`'s worktree-scan `find` predicate is now derived from
  `FEATURE_REPOS`, and the `Mains:` reports in worktree-start/worktree-remove/checkout-branch are
  derived from it too, so a sixth repo needs one edit per language rather than six.
  `test_feature_repos_inventory` pins the Python and bash inventories together.

- 2026-09-14: Captured three review-comment conventions: advisory `Check.NotNull`
  instead of `ArgumentNullException`, Tier-3 no restating XML docs, and promotion of
  `reuse-identical-opa-decision` to a blocking rename-wrapper detector on `.rego` files.

- 2026-09-14: Made peer PR review explicitly reuse the `/review` evidence order,
  rule inventory, and convention/semantic-DRY checks while remaining read-only.
  Its lead briefing now separately explains the PR's reason, project context, and
  high-level solution architecture before giving plain-language potential comments.

- 2026-09-11: Draft PR descriptions now derive the established template's Summary from the approved
  product plan's Observable outcome and Details from its in-scope bullets. Titles preserve any
  plan-provided issue label (or the whole plan H1), independently of the branch naming convention,
  and never use stacked branch history as PR copy.

- 2026-09-11: Treated `agent-skills` as a first-class optional worktree repo (including
  agent-skills-only branches). Commit, push, draft-pr, worktree start/list/remove, checkout,
  sync-master, and pipeline manifests now operate on it the same way as development/identity.

- 2026-09-11: Replaced verbatim stdout in mechanical skill chat replies with a shared concise-output
  rule, corrected the update-agent-skills apply prompt, and required peer PR reviews to render their
  orientation and comments as Markdown rather than a command transcript.

- 2026-09-11: Made in-flight policy snapshots advisory because a provider prompt or script is fixed
  at launch; policy changes now apply to the next fresh session without invalidating completed work.
  Added durable cache-backed recovery for both implement-tests and implement, a provider inner-tool
  timeout watchdog, and a single bounded local-E2E evidence pass to keep test authoring from
  turning into broad stack diagnosis.

- 2026-09-04: Bound pipeline review to `/add-rule` output. The review prompt now carries the
  registry, metadata, allowlist, and scoped rules; reviewers must repair Tier-1 violations and
  assess Tier-2/Tier-3 rules. The runner repeats the fast deterministic convention/secret scan
  after review edits, so report text cannot claim compliance on its own.
- 2026-09-04: Added a lightweight bugfix posture without a new stage or manifest field. Defect
  plans require expected behavior, reproduction, suspected cause/scope, and a regression check
  that fails for the original bad behavior. Isolated fixes stay in the manual lane
  (reproduce → red → fix → green); higher-risk or unclear-cause work uses the full pipeline.
- 2026-09-04: Made full-pipeline test authoring and review Cursor-hosted Claude/GPT-first while
  retaining Cursor Grok and native Claude Code/Codex fallbacks. Test-author selection now suggests
  Opus for four or more planned test files or a substantial planned diff; Cursor hosted-model limits
  advance only that route, not every Cursor route.
- 2026-09-03: Made local E2E stack release the Docker cleanup boundary. After verified restoration it safely
  removes unreferenced branch-scoped API/Identity images and caps least-recently-used BuildKit cache at 20GB;
  containers, networks, and volumes remain untouched.
- 2026-09-03: Made review fresh-context and adversarial. It now audits specification, behavioral
  tests, correctness, and rules/semantic DRY in that order; pipeline review applies safe in-plan
  improvements without blocking while manual review is check-only, focused, and stops for
  confirmation when its plan/solution basis is ambiguous. Added non-binding estimate-based review
  suggestions (1 skip, 2 Grok, 3 Sol, 5 Opus) and switched test authoring to Claude Sonnet 5.
- 2026-09-03: Made request challenge mandatory in `/specify`: repository evidence can refine a
  flawed or incomplete initial proposal. A materially changed agreed definition now produces an
  exact, confirmed Linear update after plan artifacts are written.
- 2026-09-02: Added a first-class, two-command manual lane for small follow-ups: `/specify` then
  `/implement`. It uses the same concise plan and in-session verification without a pipeline run,
  stage routing, review, or publishing queue.
- 2026-09-01: Removed operational pipeline dead ends: shared AI routes are valid, plan revisions
  automatically rebind state, diff budgets are advisory (4,000-line default), and review/report/E2E
  issues are recorded without re-running the full suite or blocking publish. Secrets, out-of-scope
  writes, implementation traceability, and publish safety scans remain enforced.
- 2026-08-31: Added tiered `/add-rule` metadata, recurrence/promotion ratchets, the blocking OPA
  worked example, advisory evidence, and PR-comment/pruning feedback; compacted instructions; made
  prompts cache-aligned; moved context/verification/risk/diff contracts into manifest v2; separated
  test-author and implementer model families; required assertion-level red proof and parsed
  acceptance traceability; folded verify/fix into `implement`; added fast pre-commit scanners,
  untrusted-input handling, security/checkpoint audit, compatibility translation, and workflow tests.
- 2026-08-31: Added reversible local recovery, Docker startup/wait, bounded autonomy continuations,
  and exact-session resume for genuine user-input pauses.
- 2026-08-28: Replaced profiles with plan-confirmed stages/routes, made `/specify` the sole plan
  author, introduced test-first execution, fresh providers, detached progress, and claim gates.
