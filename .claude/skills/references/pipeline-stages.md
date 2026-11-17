# Implementation pipeline stages

`/specify` records the selected subset and routes in `pipeline.json`; later plan revisions rebind
the runner automatically and preserve the prior execution audit.

```text
implement-tests? → implement → review? → commit-and-push? → draft-pr?
```

## Simple manual lane

For a narrow follow-up, `/specify` may select the manual lane. Run `/implement` directly after the
plan; it writes/tests product and test changes in one session. No pipeline stages, route confirmation,
red-proof artifact, review, or publish stage is required. The normal implementation rules still apply.

For an isolated bugfix in this lane, `/implement` defaults to reproduce → add a regression
test/check → prove it fails for the defect → fix → rerun it green → focused verification. Record
before/after evidence in `progress.md`. Do not add a separate `implement-tests` stage for small
fixes.

## Lane selection

This table is guidance. The user confirms the lane during `/specify`.

| Situation | Recommended lane |
|---|---|
| Isolated defect, deterministic reproduction, established local pattern | Manual |
| Narrow feature follow-up with an established local pattern | Manual |
| Regression needs several test layers, or the cause is uncertain | Full pipeline |
| Security, billing, tenancy/OPA, schema, public contract, data correction | Full pipeline + review |
| Broad or multi-repository work, migrations, or automated publishing wanted | Full pipeline |

| Stage | Selection rule |
|---|---|
| `implement-tests` | Required when the plan adds/changes tests. Test-only red phase; assertion failure required. |
| `implement` | Always required. Builds the plan's steps, then runs the full verify/fix procedure with parsed evidence and API samples. In the manual lane it also writes the tests first and self-reviews (Tier 1, test strength, polish). |
| `review` | Optional fresh-context, two-tier review. Tier 1 finds, proves, and fixes bugs, security, performance, and contract problems. Tier 2 applies the rules and polishes changed lines without changing behaviour. Its outcome is advisory, except that an unfixable High finding pauses for the user. Direct `/review <branch> [bugs\|polish] [focus]` reports first and applies only the findings the user picks. |
| `commit-and-push` | Optional deterministic scan/commit/push. |
| `draft-pr` | Optional; requires `commit-and-push`. |

`/test-and-fix` is an internal procedure of `implement` and remains manually invocable after PR
comment fixes. It is not selectable as a regular stage. A v1 manifest that selected it is translated
in memory so its validation still runs inside `implement`; the plan file is not rewritten.

After `implement-tests`, `implement`, and `review` succeed, the runner makes one local commit.
A failed stage stays dirty. `/commit-and-push` publishes that history. The manual lane does not
make these commits.

When `implement` or `review` changes a `test_paths` file, the runner compares it with the
`implement-tests` commit. An import or comment edit stays. A setup or helper edit stays and is
named; review receives those files with a diff command and checks that none makes a test easier
to pass. Assertion lines that are only moved or re-indented count as unchanged. The patterns cover
Jest and C# (xUnit `Skip`/`[Ignore]`, `[Fact]`/`[Theory]` attributes, `[InlineData]` rows, and
`Verify`/`Times`). A skip, a deleted test, or an assertion that was removed or rewritten is restored from
that commit, and the acceptance command for that file runs once. A passing re-run is a real
success. A failing re-run still publishes, and the draft PR names the restored hunk and the
failing command. That result is not recorded as a passed verification.

Implementation and publishing safety checks remain enforced. Review is advisory: provider/report,
convention, reuse, build, and environment issues are recorded and delivery continues. The one
exception is a High finding the reviewer truly cannot fix, which ends the stage with
`PIPELINE_INPUT_REQUIRED` and waits for the user. Comment
handling, CI diagnosis, and staging smoke remain manual skills.

## Default routes

`/update-models` proposes independent machine/workspace model defaults. Every `/specify` evaluates
selected stages offline using `model-policy.md`; the confirmed manifest saves model, effort and
ordered fallbacks. Routine work uses reviewed balanced effort; maximum effort is explicit only.
Publishing stays mechanical. The evaluator suggests different labs for test authoring and review. Explicit routes remain authoritative, and a missing alternate is an advisory.
One-run overrides never modify the plan.

## Stacked plans

A manifest may set `base_branch` to the unmerged branch the feature was cut from. Verification
diffs, the scope and budget checks, the preflight sync and `draft-pr` then use that branch instead
of master. Parked mains stay on master either way. Remove `base_branch` once the base branch has merged.

## Selection heuristic

- Any new/changed test selects `implement-tests`.
- Offer review according to task scope and risk; estimates can inform the suggestion. The user
  decides whether to run it. Use the evaluator to recommend its model and effort.
- User-facing, security, money, schema, public-contract, or broad changes should select `review`.
- Normal delivery selects both publish stages.
- Local exploration can stop after implementation/review.

Implementation validation is never optional: it runs the plan's commands even when `review` and
publish stages are omitted. The user confirms the stage set and routes during `/specify`.

```bash
/implement-pipeline HC-3333 \
  --stages implement-tests,implement,review,commit-and-push,draft-pr \
  --route review=cursor:gpt-5.6-sol-high \
  --fallback review=cursor:grok-4.7-high \
  --fallback review=codex:gpt-5.6-sol:high
```
