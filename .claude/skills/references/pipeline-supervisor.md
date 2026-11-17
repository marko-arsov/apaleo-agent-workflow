# Pipeline supervisor

The chat agent that runs `/implement-pipeline` is the supervisor. The worker is a deterministic
Python process: it runs the stages, retries providers, repairs rejected stage results in the same
session (up to two times), and restores cheated tests. The model-free watcher only streams its
events. When the worker stops, the supervisor diagnoses the stop, fixes what an engineer at this
desk could fix without a product decision, restarts the run, and asks the user only for a real
blocker.

## Loop

1. Start or resume with the default wait mode:
   `"$ROOT/.claude/skills/pipeline/implement-pipeline.sh" <task> --notify`. The watcher returns at
   `SUCCESS`, `WAITING_FOR_INPUT`, or a failure, and prints the recap with its stop reason.
2. On `SUCCESS`, report the recap and stop.
3. Otherwise, read the stop reason, `--status`, and the last events. When the reason is unclear,
   read the failing command's summary (`pipeline/summarize_output.py`) or the stage log.
4. Find the matching playbook row, take its action, and verify that it worked (worktree present,
   `docker info` healthy, conflict resolved, and so on).
5. Resume with the same command. Completed stages are kept. Use `--from <stage>` only to re-run a
   stage that verification rejected.
6. Repeat until success or until you must escalate.

**Budget.** At most two recoveries per failure class and six per supervision session. Never repeat
the same action on an unchanged failure. When the budget is spent, escalate with everything you
tried.

## Playbook

| Stop reason | Action | Escalate only when |
|---|---|---|
| `no feature worktree found` | `worktree-start <branch>`: the existing branch, or `origin/<base>` when the plan's branch does not exist yet | worktree-start fails |
| `sync conflict … merge aborted`, `sync-master conflict` | `/sync-master <branch>`; it resolves clear conflicts | the conflict needs a behavioural choice |
| `Docker is required … not running`, an unhealthy stack | `open -a Docker`; wait up to 10 minutes for `docker info` | Docker does not start |
| E2E lock wait timed out | `/e2e-stack-status`. If the owner's process is gone, release that stale lock (`references/e2e-stack-lock.sh release --branch <owner>`); otherwise wait | a live owner holds it beyond an hour |
| `workflow policy changed during the … stage` | Resume; the stage restarts on the new policy | never |
| `no approved route passed preflight`, `engine produced no output`, provider 5xx | Check the CLI's login (`agent status`, `claude auth status`, `codex login status`). If logged in, wait 10 minutes and resume | a login, spend limit, or quota needs the user |
| Report contract after the worker's repairs (`lacks the required 'none' declaration`, `red-proof.md must declare …`, report missing) | Resume with `--from <stage>` | it fails the same way twice |
| `changed out-of-plan paths: <repo>/.git/HEAD` | Switch that worktree back to `<branch>` (`git -C <worktree> switch <branch>`), then resume | uncommitted work would be lost |
| `stage left dirty paths outside the plan`, out-of-plan edits | Inspect the diff. Restore incidental changes (formatting, an unrelated regenerated file) with `git checkout -- <path>`, then resume | the path is genuinely needed: a plan revision |
| `implementation verification failed: <commands>` | Read the failing summary. Environmental (stack, ports, Identity scopes per `e2e-missing-identity-scopes.md`, npm auth via `NPM_CONFIG_USERCONFIG=$HOME/.npmrc`): fix it, then resume `--from implement`. A product or test failure: resume `--from implement` once; the fresh session gets the recovery packet | the same assertion fails twice |
| `dirty path is not a valid recovery input` | Inspect it. This branch's own partial work inside the plan's paths: resume | the changes are unrelated |
| `parked main <repo> is dirty` | Show `git status` of that checkout | always: those are the user's files |
| `draft-pr … existing PR … unsafe state` | Show the PR state | always |

## Pending questions (`WAITING_FOR_INPUT`)

Before asking the user, check whether something written already settles the question:
- the plan (`product.md`, `implementation.md`, `pipeline.json`, `deferred-scope.md`);
- `AGENTS.md`, `.claude/rules`, or a reference: for example, diff budgets are advisory, and
  `.npmrc` auth comes from `NPM_CONFIG_USERCONFIG`;
- a fact you can check, such as a file, a command, or the service state.

If it does, answer it with `--answer '<answer> (settled by <source>)'`. Otherwise relay the
question to the user unchanged, with your recommendation.

The user must answer when a question is about:
- product behaviour, scope, or the acceptance criteria;
- a plan change (a new path, budget, or command);
- credentials or logins;
- accepting a risk, or speaking as the user.

## Escalation

```text
Pipeline needs you: <task> — stage <stage>
What happened: <stop reason, one line>
What I tried: <action → result, for each>
Question: <one question>
Recommendation: <option and why>
```

## Never

- Edit `product.md`, `implementation.md`, `prompt.md`, `deferred-scope.md`, or `pipeline.json`.
  A plan change is a `/specify` revision with the user's approval.
- Undo a test-judge restore, or weaken, skip, or delete a test.
- Use a route or fallback that the plan did not confirm.
- Force-push, merge, or move a parked main off `master`.
- Delete, stash, or overwrite files you did not create.
- Release a lock whose owner process is alive.
- Comment, post, or change Linear or GitHub as the user.
