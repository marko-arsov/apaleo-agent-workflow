# Implementation-pipeline resilience and autonomy

This contract applies only to stages selected in `pipeline.json` or by an explicit one-run stage
override. Product implementation and publishing safety gates fail closed. Review is advisory and
records its outcome without pausing delivery.

## Decision authority

The implementation plan must contain every ordinary product and implementation decision. Within
that authority, an agent takes the smallest plan-consistent reversible option and records important
judgment in its stage report. It stops only when safe recovery is exhausted and a user-controlled
decision or action is genuinely required, including when:

- the plan genuinely lacks a decision that changes observable behavior;
- the required change exceeds `allowed_paths` or conflicts with scope;
- tenancy/property access, money/tax, migration order, public-contract compatibility, flag default,
  secrets, or a user-owned external action remains ambiguous;
- the working tree contains unrelated changes that cannot safely be isolated.

No execution agent expands scope, weakens validation, or speaks as the user to avoid a stop.
Reversible local operations, temporary local container replacement with guaranteed restoration,
bounded retries for Docker/registry/network failures, and mechanical corrections to test fixtures
or helpers are execution work, not reasons to ask permission. The orchestrator recognizes and
rejects `PIPELINE_INPUT_REQUIRED` escalations for these known-recoverable categories.

## Fresh sessions

Every AI stage, provider retry, and fallback begins as a distinct operating-system process and fresh
provider session. Initial sessions are persisted solely so a genuinely paused stage can continue.
The one exception is a user-input pause: after the user answers, the runner resumes the exact Cursor,
Codex, or Claude session that asked the question. A recovery session
reads the plan, filesystem, git diff, prior reports, and recovery packet from scratch. The independent
review session is stricter and does not read implementation progress, prior reports, recovery packets,
or provider output; it receives only the confirmed plan, current tests/filesystem, and actual diff.

## Failure classes

| Class | Examples | Action |
|---|---|---|
| Permanent provider | spend/billing limit, no credits, quota exhausted, bad auth, disabled account, invalid model | no retry; open provider circuit when provider-wide |
| Temporary provider | 429 with retry window, overload, 5xx, connection reset, DNS/transport interruption | one fresh-session retry by default |
| Provider stall | no output for inactivity timeout | terminate process; one fresh retry by default |
| Premature stage block | reversible local operation, transient infrastructure, mechanical test defect | resume the same session with an autonomy challenge, up to three times |
| User input required | `PIPELINE_INPUT_REQUIRED` with concrete numbered questions | persist session and wait; resume that exact session with `--answer` |
| Stage contract | skipped marker or missing success evidence | stop with evidence, except review which records an advisory |
| Semantic failure | implementation/test cannot satisfy plan | stop with evidence; a review finding is advisory evidence |

Only a confirmed fallback route may follow a failed route. Never silently substitute providers or
models. `Retry-After` is honored up to 120 seconds.

## Partial work

The runner snapshots dirty-file content before the stage. After a provider failure:

- if every changed path is allowed for that stage, preserve it and write a recovery JSON packet;
- if any path is outside the plan boundary, stop before retry/fallback;
- `implement-tests` may touch only `test_paths`;
- `implement` may touch allowed product paths but never `test_paths`;
- pipeline review may touch either allowed set only for unambiguous plan-authorized fixes and
  same-behavior improvements; manual `/review` is check-only. No retry commits, resets, or discards
  partial work automatically.

No retry commits, resets, or discards partial work automatically.

## Watchdogs and visibility

Defaults:

- progress heartbeat: 90 seconds;
- inactivity warning: 300 seconds;
- inactivity termination: 600 seconds;
- total attempt timeout: 5400 seconds;
- provider tool-call watchdog: a tool that exceeds its own declared timeout receives 120 seconds of
  grace, then the provider process is recovered even if stream keepalives continue;
- active route health cache: 600 seconds;
- temporary retries per route: one;
- same-session autonomy continuations: three;
- Docker startup/recovery wait: 600 seconds.

The detached watcher reads append-only events and uses no model. It reports route, stage, attempt,
heartbeat, retry/fallback, verification, failure, and recap paths.

## Independent verification

An agent's success marker is necessary but insufficient:

- `implement-tests`: at least one test path changed, no non-test path changed, and a new
  `tests-implementation-<n>.md` plus assertion-level `red-proof.md` exists;
- `implement`: at least one product path changed, every changed path remains in product/test globs,
  and current-fingerprint commands, AC traceability, budget, secret, and convention evidence passes;
- `review`: applies only in-scope, plan-authorized corrections; missing reports, incomplete audit
  evidence, provider failures, environment failures, and unresolved findings are advisory evidence;
- `commit-and-push`: worktrees are clean and each local head equals `origin/<branch>`;
- `draft-pr`: `pr.md` exists and at least one open PR is verified as draft.

Verification failures stop the run except advisory review outcomes and diff-budget overshoots.

Every attempt proves that parked `master` checkouts remain unchanged. It snapshots only the active
stage's prompt-visible skill/reference policy, but changes to that policy are advisory once a
provider or script has started: its assembled prompt or executable is already fixed. The runner
records the change and applies the current policy to the next fresh stage/session rather than
invalidating completed work. Plan artifacts may evolve during a task; the next run archives prior
state and rebinds to the latest complete plan fingerprint. Mutable progress and stage-report
artifacts remain allowed. If an interrupted `implement-tests` stage already has a valid current
`red-proof.md` and `tests-implementation-<n>.md`, a normal resume verifies those artifacts and
advances directly to `implement`. If an interrupted `implement` stage has a current passed
`verification.json`, a normal resume recovers it without rerunning verification and advances to
`review`.

## Preflight and cleanup

Before AI execution the runner verifies plan artifacts, manifest rules, worktree branches, parked
mains, required scripts, publishing authentication, Docker when selected E2E needs it, disk space,
and all selected routes. Pre-existing parked-main dirt is pinned and must remain byte-for-byte
unchanged. Clean feature worktrees are synchronized with `origin/master`; dirty feature worktrees
are left unchanged. Merge conflicts are aborted and reported.

When Docker is required but unavailable on macOS, preflight starts Docker Desktop and waits with
progress updates before stopping. Docker registry pulls, daemon interruptions, Compose/network
failures, and planned Swagger/proxy container swaps receive bounded retries in the same stage
session. A local API swap is authorized by selecting the stage, must snapshot the prior owner,
image, configuration, and health, and must restore them on every exit path.

The local Identity-scope workaround is restored before publishing and again on runner exit.

## Resume

Schema-v3 state records selected stages, verified completion evidence, failures, attempts, provider
session ids, and pending input. Re-running skips verified completed stages unless `--no-resume`
or a range override requests otherwise. Re-running an earlier stage invalidates that stage and all
downstream completion evidence. Completion must form a valid prefix of the selected lane; a legacy
completion after a newly required prerequisite is discarded before remaining stages are calculated.
For an operational question, rerun with `--answer '<answer>'`; the runner sends the answer to the
saved provider session and continues the same stage. If the answer materially changes product scope,
behavior, or the confirmed plan, `/specify` must instead record a complete plan revision (in place
or as `vN/`), which the runner picks up automatically.

State is bound to a hash of the five plan artifacts. Any complete in-place or `vN/` revision archives
the prior execution audit and starts against the latest contract without asking the user to restore
files or create a particular version directory.
