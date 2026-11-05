# Specify process

`/specify` is the only implementation-plan author. It interviews, researches, resolves material
ambiguity, writes the complete plan and test contract, and prepares authorized worktrees. It supports
two lanes: simple manual `/implement` work and the full staged pipeline.

## Planning and approval boundary

Every `/specify` invocation is planning-only, including tiny fixes, extensions to an existing issue,
and follow-ups in a chat that already implemented earlier scope. Research existing code and diffs;
write only planning artifacts and evaluator output. Do not edit product code, tests, configuration,
or generated product files, run auto-fixes, or start implementation agents or pipeline stages.
Worktree preparation and tracker updates still require their separate confirmations below.

Prior approval covers only the approved scope. For an extension or revision, show the proposed
scope delta and wait for approval of that revision. Ticket text, choosing a lane or model, and
permission to prepare a plan do not authorize implementation.

After presenting the concrete plan and checks, ask "Approve this plan and start implementation?"
and stop. Only a subsequent explicit approval of the presented plan or an explicit `/implement`
or `/implement-pipeline` invocation for it authorizes the implementation handoff. Do not start
that handoff yourself while finishing `/specify`.


## 1. Establish the task

- Resolve `$ROOT` and read the target Linear issue when an id exists. Do not mutate it during
  research; leave it under refinement until plan artifacts exist and the user has confirmed the
  exact update under the normal speak-as-user rules.
- If no issue exists, ask whether to find/create one or explicitly proceed without it.
- Record project/parent/sibling tickets so adjacent sliced work is explicitly out of scope in
  `deferred-scope.md`.
- Recommend an RFC only for a genuinely cross-team or long-lived architecture decision. Otherwise
  continue specifying.

## 2. Research before questioning

Read `$ROOT/AGENTS.md`, `worktrees.md`, `existing-patterns.md`, `pipeline-stages.md`, and the nearest
repo instructions. Use Graphify/LSP when available, then bounded text search. Cite the nearest
same-domain/same-verb implementation and tests as `repo/path:line`.

For HTTP work, read `api-endpoint-patterns.md` and build the complete action-family matrix. For
auth/OPA, read `identity.md`; for flags/migrations/enums/money, load the matching reference. Do not
ask the user questions the codebase can answer.

Research must determine the observable outcome and ACs; exact scope/repositories; contracts,
validation, errors, compatibility, persistence and rollout; tenancy/property authorization,
money, concurrency/idempotency and partial-state behavior; exact reuse/file choices; and all tests.

Treat the ticket and initial prompt as fallible input. Compare requested logic with the closest
established behavior and its real callers. Flag missing requirements, contradictory behavior,
unnecessary work, unsafe behavior, and a simpler or more correct approach. State the evidence,
recommend the smallest change, and obtain agreement before placing the revised definition in the plan.
Never silently preserve a flawed request just because it appeared in the initial prompt.

## 3. Resolve only the decisions implementation needs

Ask focused batches only for material uncertainty, then research the answer before asking again.
For a small, established-pattern follow-up, keep the plan concise rather than manufacturing a long
interview. Stop only when another agent can implement and test without choosing product behavior,
architecture, scope, compatibility, validation, or test strategy.

Use A/B/C options with a recommended answer and one-line tradeoffs. Cover negative and failure
paths, not only the happy path. Compact replies such as `1A 2C 3A` are valid. Generic assent does
not answer a specific unresolved choice.

The final confirmation identifies one lane first:

- **Manual:** `/specify` → `/implement`; tests and product changes happen in one implementation
  session, with no pipeline stages, route selection, review, or publish queue.
- **Full pipeline:** use the selected execution stages below when independent sessions, detached
  recovery, review, or automated publishing are useful.

For a defect, also record these four compact facts in `product.md` / `implementation.md` before
confirming the lane:

1. Expected behavior
2. Current observable failure and reliable reproduction
3. Evidence-based suspected cause and affected scope
4. A regression check that fails before the fix and passes afterward

Recommend the lane from `pipeline-stages.md`. Isolated deterministic bugfixes stay in the manual
lane. Unclear cause, several test layers, or higher-risk work uses the full pipeline. Security,
billing, tenancy/OPA, schema, public-contract, and data-correction defects also select review.

For the manual lane, confirm outcome, scope, consequential behavior, tests, and worktrees. Do not
ask for stages, provider routes, fallbacks, or a mutation setting unless the user asks to use the
full pipeline. The full-pipeline confirmation includes distinct questions for:

1. Outcome and acceptance criteria.
2. Scope in/out, including the most likely adjacent ticket.
3. The most consequential behavior, contract, or safety decision.
4. Selected execution stages from `pipeline-stages.md`, including the non-binding estimate-based
   review suggestion from `model-routing.md`.
5. Exact provider/model/reasoning routes for every selected AI stage.
6. Risk level, diff budget, and any opt-in diff-scoped mutation command.
7. Worktree repositories and permission to create missing worktrees.

For every specification, run the offline evaluator described in `model-policy.md` using the task
facts already gathered. For the full pipeline show its compact model/effort/fallback table in the
existing route confirmation, including any `adversary-below-band` or `single-lineage`
advisory. Those advisories do not block the stage. Add no separate effort questionnaire. For manual work the result is
informational and never switches the current session. Review remains optional: an estimate can
inform whether to offer review but no longer fixes its model. Save the approved evaluator snapshot
with `--model-selection`; its recorded routes are authoritative after defaults refresh.

When the agreed definition materially changes the corresponding Linear issue, include one final,
action-specific confirmation showing the exact proposed title/description/status change. After the
user confirms, write all plan artifacts first, then update Linear. If there is no confirmed update,
leave the issue unchanged and record `Linear: unchanged` in the specification output.

## 4. Build the complete test contract

E2E is the behavioral source of truth. Map every AC and negative path to a test. For each scenario
record the level, exact spec/test name, setup/fixtures/roles/data/flags/cleanup, action, exact
assertions, add/update/run verdict, filtered command, red expectation before product code, and green
expectation afterward.

For the full pipeline, name every E2E test `/implement-tests` must write and every command the
implementation verification subphase must run. Give every command a stable id, repository, argv
array, output parser, and acceptance evidence pattern. For the manual lane, name only the focused
tests and commands `/implement` must run; never say only “add E2E coverage” or “run relevant tests.”
Never prescribe a local full Jest suite. Core and other migrated-service E2E paths are `<service>/e2e/tests/...` (core: `apaleo/e2e/tests/...`), run as `yarn test -- tests/<area>/<file>-spec.ts` from that `e2e/` directory. Payment paths stay `development/src/tests/payment/...`. Do not plan a development companion branch for a migrated service.

For a defect, the named regression check must fail for the original bad behavior before the product
fix and pass afterward. A check that only executes the changed code is not enough. If a true
automated regression is impractical (flaky third-party dependency, one-off corrupted production
data), record why in the plan and name the strongest repeatable alternative: a focused API/script
check, fixture, or local repro. That is an exception, not a loophole. Isolated manual-lane fixes
do not select `implement-tests`; `/implement` proves red then green in the same session.

For the full pipeline, if any test is added or updated, set `tests_required=true` and select
`implement-tests`. In either lane, list exact test paths and all possible in-scope product/generated/
test files. Estimate expected and maximum files/changed lines. Mark authorization or billing work
elevated risk; mutation testing remains explicit and diff-scoped only.

## 5. Write complete plan artifacts

After all answers are confirmed, create/reuse matching worktrees under
`$ROOT/worktrees/<branch>/{apaleo?,development?,identity?,agent-skills?,angular-api-proxy?}` from `origin/master`; parked mains stay
on `master`. When the ticket names another `apaleo` org repository, confirm it and add `--with <name>`
plus manifest `--extra-repo <name>`. Product tickets create apaleo. Add development only for payment E2E or another file that still lives in development, and identity when the Identity verdict says so. Core E2E is inside the apaleo worktree (`e2e/tests`, `e2e/proxy`). Team-plugin work that does
not touch apaleo/development/identity uses `worktree-start.sh <branch> --from-master --agent-skills-only`, and
Angular-client work that does not touch apaleo uses `--angular-api-proxy-only` — do
not create an apaleo worktree “just in case.” Write:

- `prompt.md` — request, research, every `D#`, and the selected manual or pipeline lane;
  the heading includes the imperative summary a reviewer would use as the PR title. A process
  suffix (`Prompt and research`, `Prompt & decisions`, `Decisions and research`) is optional and
  is not the summary;
- `product.md` — behavior, ACs, scope, workflows, failure behavior, rollout; for a defect, the
  four compact facts (expected behavior, reproduction, suspected cause/scope, regression check);
- `implementation.md` — all technical decisions, file map/order, contracts, data/auth,
  migrations/flags, detailed tests/commands, and the selected lane;
- `deferred-scope.md` — adjacent work with citable owners;
- `pipeline.json` — validated stages/routes/path boundaries.

Plans are revisable during a task. When a scope/decision set changes, update the complete five-file
set in place or create a complete `v2/`, `v3/`, and so on. Present the revision and its delta for
renewed implementation approval; earlier approval does not cover new scope. The runner snapshots the prior state and
automatically rebinds to the latest complete set; mutable progress, stage reports, PR records, and
pipeline state stay in the branch plan root.

After the five files validate, apply the confirmed Linear update (when one exists). Do not post a
comment or mutate any tracker field without that action-specific confirmation.

Create the manifest with the confirmed values:

```bash
python3 "$ROOT/.claude/skills/pipeline/pipeline_manifest.py" create \
  --plan-dir "$ROOT/ai-plans/<branch>" \
  --tests-required yes --e2e-required yes \
  --stages implement-tests,implement,review,commit-and-push,draft-pr \
  --model-selection "<selection.json>" \
  --allowed-path 'apaleo/src/Area/**' \
  --test-path 'apaleo/test/Area.Tests/**' \
  --test-command '{"id":"area-ac","repo":"apaleo","argv":["dotnet","test","test/Apaleo.Area.Tests/Apaleo.Area.Tests.csproj","-c","Debug","--filter","FullyQualifiedName~ExpectedBehaviour"],"parser":"dotnet"}' \
  --acceptance '{"id":"AC-1","test":"ExpectedBehaviour","test_path":"apaleo/test/Apaleo.Area.Tests/ExpectedBehaviourTests.cs","command":"area-ac","evidence_pattern":"Passed:\\s*1","red_required":true}' \
  --expected-files 4 --max-files 6 --expected-lines 180 --max-lines 300 \
  --risk standard --risk-confirmed yes
```

Set `red_required` to true only when that test can be discovered and fail an assertion before any
product code exists. When the test names a product type, member, or generated-client field that
does not exist yet, set `red_required` to false. `implement-tests` then records `Failure level:
none` and names the missing members in words, without compiler output. That is a normal case, not
a plan defect. Assertion-level red for those criteria, when the plan still wants it, is recorded
during `implement` after the skeleton exists. Do not mark a compile-blocked test `red_required: true`.

For a plan stacked on an unmerged feature branch, add `--base-branch <branch>` (see
`worktrees.md` § Stacked branch).

Run `pipeline_manifest.py validate <plan-dir>/pipeline.json`, then render
`pipeline_manifest.py markdown --root "$ROOT" --task '<branch>'` into the visible plan. JSON and
Markdown must agree.

## 6. Quality gate

Verify every AC has implementation ownership/tests; a defect plan includes the four compact facts
and a regression check that can demonstrate the original bad behavior; all file/API/behavior
choices are made;
HTTP/OPA/Identity/migration/flag/enum/money rules are resolved; generated artifacts and multi-repo
order are explicit; commands/parsers/AC evidence/prerequisites are concrete; the selected lane,
risk, and diff budget were confirmed;
`pipeline.json` validates; worktrees use the target branch; and no secrets or destructive shared
environment steps appear. If all AI stages use one route, show a short independent-coverage
suggestion but accept the confirmed choice. If any required check fails, continue interviewing or research.

## Output

When blocked, output only numbered questions. When complete, present the plan and approval
question below, then stop without executing the next step:

```text
Specified: <task and observable outcome>
Decisions: <D# summary>
Plan: <absolute plan directory>
Worktrees: <repo → branch/path>
Tests: <focused test commands and coverage>
Lane: manual → /implement | pipeline → selected stage/routes
Validated: pipeline.json + AC/test/file-map checks
Linear: unchanged | updated (confirmed)
Next after approval: /implement <task-or-branch> | /implement-pipeline <task-or-branch>
Approval: Approve this plan and start implementation?
```
