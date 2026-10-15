# Local E2E stack — lock + FIFO wait queue

The Docker Compose API stack used by `development` E2E is **machine-global**, not per-worktree. Worktrees isolate git; they do **not** isolate ports or compose.

Helper script (preferred): `$ROOT/.claude/skills/references/e2e-stack-lock.sh`  
Also read `$ROOT/.claude/skills/references/worktrees.md`.

## Which skills touch the stack

| Skill | Behaviour |
|---|---|
| **`implement` verify/fix** | **Waits** on the queue for plan-required localhost E2E (`acquire --wait`). Build/unit run first without the lock. |
| **manual `test-and-fix`** | Uses the same queue after PR/manual changes. |
| **`e2e-test-engineering-development`** | If running `test:file` during TDD: `acquire --wait`. Prefer deferring green E2E to implement's verify/fix subphase. |
| `review` | No E2E. May repair missing planned Swagger/proxy output under the same lock/snapshot/restore contract. |
| `specify` / plan | No stack. |

## Files

| Path | Role |
|---|---|
| `$ROOT/.local/e2e-stack.lock` | Current owner (branch, worktree, skill, pid, image, acquired_at) |
| `$ROOT/.local/e2e-stack.queue.json` | FIFO waiters (not committed) |
| `$ROOT/.local/e2e-scope-workaround/` | Backup + state for local `config.ts` Identity-scope strip (not committed) |

## What happens if E2E is running on A and implement verification starts on B?

**It waits** (does not stop, does not steal):

1. B finishes build + unit (parallel-safe) first.
2. Before localhost E2E, B runs:
   ```bash
   $ROOT/.claude/skills/references/e2e-stack-lock.sh acquire --wait \
     --branch "<B>" --worktree "$WT" --skill test-and-fix
   ```
3. Script enqueues B, prints `waiting: owner=A position=1 …` every ~30s.
4. When A releases the lock, B becomes head, acquires, rebuilds its `apaleo-ui-api:wt-<slug>` (and `apaleo-identity:wt-<slug>` if `$WT/identity` exists), runs E2E, releases.

Without `--wait` (status-only / dry check): exit `3` + `queued` — used by `/e2e-stack-status`, not by verification.

Max wait default: **2 hours** (`E2E_STACK_MAX_WAIT_SECONDS`). Poll: **30s** (`E2E_STACK_POLL_SECONDS`).

## Commands

```bash
# APALEO_ROOT is the workspace. Set it only when the shell is outside that tree.

# Who holds the seat + queue
$ROOT/.claude/skills/references/e2e-stack-lock.sh status

# Take seat or wait (the lock audit label remains test-and-fix for compatibility)
$ROOT/.claude/skills/references/e2e-stack-lock.sh acquire --wait \
  --branch "$(git -C "$APALEO" branch --show-current)" \
  --worktree "$WT" \
  --skill test-and-fix

# Free seat (end of E2E or /e2e-stack-release)
$ROOT/.claude/skills/references/e2e-stack-lock.sh release --branch "<branch>"
```

Exit codes for `acquire`: `0` acquired · `3` queued (no `--wait`) · `4` timeout · `2` error.

## Release rules

After E2E phase (pass or fail), always `release --branch <current>` unless the user asks to keep the seat.  
Release is also the local Docker cleanup boundary. After the caller restores the previous image/configuration,
the lock removes its branch-scoped `apaleo-ui-api:wt-*` and `apaleo-identity:wt-*` images when no container
still references them, then trims BuildKit's least-recently-used cache to **20GB**. It never prunes containers,
networks, or volumes. Override that cache cap only for one run with
`APALEO_DOCKER_BUILD_CACHE_MAX_USED_SPACE=<size>` (for example, `10GB`). A retained-in-use image means the
image is still referenced by a running or exited container; inspect restoration/container lifecycle because
release deliberately will not force-remove it.
Do **not** `docker compose down` unless asked.  
Do **not** recreate the whole `db` container to fix an apaleo migration collision — that wipes Identity’s `ApiScopes` (see `e2e-missing-identity-scopes.md`). Drop/recreate only the `apaleo` database.  
Force another branch’s lock only with explicit user confirm: `release --branch <other> --force`.

Stale lock: owner pid dead **and** older than 6h → next `acquire` may take it. Prefer explicit release.

## Image tag per branch

`apaleo-ui-api:wt-<short-slug>` (script prints `image=…` on acquire). Pin in the **owner** worktree’s `development/apaleo/.env`. Only the lock holder may recreate `api`.

When `$WT/identity` exists, also `apaleo-identity:wt-<short-slug>` (`identity_image=…`). Pin `IDENTITY_IMAGE` in the same gitignored `.env` and recreate `identity`. See `references/identity.md`. Do not commit `.env`.

## Reversible local image switching

Selecting a pipeline that requires localhost E2E or generated Swagger/proxy artifacts pre-authorizes
temporary switching of the **local** API container while the stage holds the lock. This is not a
shared-environment mutation and does not require a chat question.

Before switching, record the active container image, relevant gitignored `.env` values, health, and
lock owner. Build/tag the branch image, update only the local ignored configuration, recreate the API,
and perform the required generation/test. In cleanup—success, failure, timeout, or interruption—put
the prior image/configuration back, recreate it, verify health, and release the lock. Release then removes
only the no-longer-referenced branch image and enforces the BuildKit cache cap. Never replace an
image while another live branch holds the lock; wait in FIFO order instead.

Registry pulls, Docker daemon startup, compose timeouts, and transient network failures are retryable.
Use bounded exponential backoff and keep reporting progress; do not stop merely to ask the user to
“try again.” Ask only after recovery is exhausted and a concrete user action is necessary.

## Parallel full stacks

Not supported. Queue serializes local E2E. Use Jenkins or Cloud Agents for true parallel E2E.
