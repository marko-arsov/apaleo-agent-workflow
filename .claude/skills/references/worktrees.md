# Worktrees — shared conventions

Read this from any pipeline skill that touches git checkouts. Canonical layout lives in `$ROOT/AGENTS.md`. Identity/authz catalog: `$ROOT/.claude/skills/references/identity.md`.

## Layout

```
$ROOT/                              # workspace root (has AGENTS.md + ai-plans/)
├── apaleo/                         # PARKED on master — never feature work
├── development/                    # PARKED on master — never feature work
├── identity/                       # PARKED on master — never feature work
├── agent-skills/                   # PARKED on master — never feature work
├── angular-api-proxy/              # PARKED on master — never feature work
├── worktrees/<branch>/             # one folder per feature branch
│   ├── apaleo/                     # git worktree on <branch> (default product work)
│   ├── development/                # git worktree on <branch> (when e2e needed)
│   ├── identity/                   # git worktree on <branch> (when Identity needed)
│   ├── agent-skills/               # git worktree on <branch> (when team plugins change)
│   └── angular-api-proxy/          # git worktree on <branch> (when Angular API clients change)
└── ai-plans/<branch>/              # plans stay at $ROOT (not inside the worktree)
```

`<branch>` may contain `/` (e.g. `<github-login>/<issue-id>-<slug>`) → nested dirs under `worktrees/` are normal.

A branch may be **agent-skills-only** or **angular-api-proxy-only** (no `apaleo/` worktree). `/update-agent-skills` still fast-forwards the parked clone after merge; it is not the place to edit plugins.

### Path helpers

| Name | Path |
|---|---|
| `$WT` | `$ROOT/worktrees/<branch>` |
| `$APALEO` | `$WT/apaleo` (may be absent on agent-skills-only branches) |
| `$DEV` | `$WT/development` (may be absent) |
| `$IDENTITY` | `$WT/identity` (may be absent) |
| `$AGENT_SKILLS` | `$WT/agent-skills` (may be absent) |
| `$AAP` | `$WT/angular-api-proxy` (may be absent) |
| Main apaleo | `$ROOT/apaleo` (always `master`) |
| Main development | `$ROOT/development` (always `master`) |
| Main identity | `$ROOT/identity` (always `master`) |
| Main agent-skills | `$ROOT/agent-skills` (always `master`) |
| Main angular-api-proxy | `$ROOT/angular-api-proxy` (always `master`) |

All code edits, builds, tests, commits, and pushes for a feature happen under `$WT`, never under `$ROOT/apaleo`, `$ROOT/development`, `$ROOT/identity`, `$ROOT/agent-skills`, or `$ROOT/angular-api-proxy`.

## Hard rules

1. **Mains stay on `master`.** After any worktree operation, verify:
   `git -C $ROOT/apaleo branch --show-current` and the same for `development`, `identity`, `agent-skills`, and `angular-api-proxy` when those clones exist → all `master`.
2. **Never `git switch` / `git checkout` a feature branch in a main repo.** That parks the main off master and blocks a second worktree for the same branch.
3. **Never `git checkout master` inside a feature worktree.** Sync via `/sync-master` (`merge origin/master` while staying on the feature branch).
4. **One branch ↔ one worktree.** Git refuses the same branch in two worktrees.
5. **`ai-plans/<branch>/` stays at `$ROOT`** — shared across sessions; do not copy into `$WT`.
6. **Cursor session root:** after creating/selecting a worktree you will edit, call `move_agent_to_root` with `rootPath: $WT` (folder that contains the feature repos for this branch). Keep using absolute `$ROOT/…` for plans and AGENTS.md.

## Resolve `$ROOT` when cwd is inside a worktree

1. If the absolute path contains `/worktrees/`, `$ROOT` is the path **before** `/worktrees/`.
2. Else walk up for a directory that has `AGENTS.md` **and** sibling `apaleo/` + `development/` **and** is **not** itself under `…/worktrees/…`.
3. Else walk up for `apaleo/` + `development/` siblings outside `worktrees/`.
4. Verify `$ROOT/AGENTS.md` exists before proceeding.

Do **not** treat `$WT` as `$ROOT` even when it contains `apaleo/` and `development/`. `identity/` is optional and is **not** required to resolve `$ROOT`.

## Ensure worktree (shared failsafe)

Used by `specify`, `implement-tests`, `implement`, `checkout-branch`, and any skill that previously did `git switch` in mains.

1. Resolve `<target>` branch name.
2. If no feature repo exists under `$WT` (or the existing checkouts are not on `<target>`) → follow **`worktree-start`** (create/reuse; do not invent a different branch). Product tickets use the default apaleo worktree. Team-plugin tickets that do not touch apaleo/development/identity use `--agent-skills-only`; Angular-client tickets that do not touch apaleo use `--angular-api-proxy-only`.
3. **development:**
   - Required when the plan changes payment E2E (`src/tests/payment`) or another file that still lives in development, or when `origin/<target>` exists on development and the skill needs that repo → ensure `$WT/development` via `worktree-start`.
   - Core, identity, and other migrated-service E2E live in that service's `e2e/` directory. Do not create a development worktree for those tests. If one remains and its own changes are only core E2E that origin/master already removed, remove that checkout and close its pull request. Do not merge master into it.
4. **identity** (same pattern; see `references/identity.md`):
   - Required when plan/Identity verdict says so, or when `origin/<target>` exists on identity and the skill needs that repo → ensure `$WT/identity` via `worktree-start --with-identity`.
   - Not needed → do not create an identity worktree “just in case.”
5. **agent-skills** (same pattern):
   - Required when the plan/ticket is team-plugin work, or when `origin/<target>` exists on agent-skills and the skill needs that repo → ensure `$WT/agent-skills` via `worktree-start --with-agent-skills` (or `--agent-skills-only` when apaleo is not in scope).
   - Not needed → do not create an agent-skills worktree “just in case.” Do not edit the parked `$ROOT/agent-skills` clone.
6. **angular-api-proxy** (same pattern):
   - Required when the plan changes the generated Angular API clients or the generator under `openapi-generator-solution/`, or when `origin/<target>` exists on angular-api-proxy and the skill needs that repo → ensure `$WT/angular-api-proxy` via `worktree-start --with-angular-api-proxy` (or `--angular-api-proxy-only` when apaleo is not in scope).
   - Not needed → do not create an angular-api-proxy worktree “just in case.” Ordinary backend tickets never need it. Do not edit the parked `$ROOT/angular-api-proxy` clone.
   - Generated clients under `modules/**` are regenerated by the canonical flow, never hand-edited.
7. **Another `apaleo` org repository:**
   - Attach it only when the ticket or the user names it. Confirm the name, then `worktree-start.sh <branch> --with <name>` (repeat `--with` for each one). Record the name with `pipeline_manifest.py create --extra-repo <name>`, which writes `extra_repos`.
   - If `$ROOT/<name>` is already a checkout of `apaleo/<name>`, that checkout is the source. Otherwise the script creates a bare mirror at `$ROOT/.repos/<name>.git` and adds the worktree from it.
   - A ticket that never names another repository keeps the usual worktrees. Do not scan the org, and do not add a parked clone for every repository.
8. Verify: at least one required worktree is on `<target>`. For product work, `git -C $APALEO branch --show-current` equals `<target>` (and `$DEV` / `$IDENTITY` / `$AGENT_SKILLS` / `$AAP` when required). An attached extra checkout is on `<target>` too.
9. Dirty worktree with unrelated/unexpected changes → **stop and ask** (never stash/switch silently).
10. Confirm mains still on `master`.
11. Prefer `move_agent_to_root` → `$WT` before edits.
12. Report paths + `was → now` in the skill output.

**Never create a new branch** except inside `specify` / `worktree-start` when explicitly creating from `origin/master`. Plan/implement/checkout only attach worktrees to existing local or `origin/<target>` refs.

## Creating a new branch (specify only)

From main repo (must be on `master`, clean enough):

```bash
git -C $ROOT/apaleo fetch --prune
# create worktree + branch in one step — leaves main on master
git -C $ROOT/apaleo worktree add -b <branch> "$ROOT/worktrees/<branch>/apaleo" origin/master
```

Same for development when payment E2E or another file that still lives in development changes, identity when the Identity verdict says needed, agent-skills when the ticket is team-plugin work, and angular-api-proxy when the Angular clients or their generator change (`worktree-start.sh <branch> --from-master --agent-skills-only` / `--angular-api-proxy-only` when apaleo is out of scope). Core and other migrated-service E2E stay on that service's branch. For another `apaleo` org repository named by the ticket, add `--with <name>` on that same command. **Identical `<branch>` name.** Do **not** `git switch -c` in the main checkout.

## Stacked branch (specify only)

When a ticket must build on another unmerged feature branch, cut the worktree from that branch
instead of `origin/master`. Use an absolute target path: `git -C` resolves a relative path inside the
parked clone.

```bash
git -C $ROOT/apaleo fetch --prune
git -C $ROOT/apaleo worktree add -b <branch> "$ROOT/worktrees/<branch>/apaleo" origin/<base-branch>
git -C "$ROOT/worktrees/<branch>/apaleo" branch --unset-upstream
```

Create the manifest with `--base-branch <base-branch>`. Verification then measures scope and
budget from the fork point with that branch. Preflight merges `origin/<base-branch>` instead of
master, and `draft-pr` targets it. After the base branch merges:

1. Remove `base_branch` from `pipeline.json`.
2. Run `/sync-master`.
3. Retarget the PR to `master`.

## Existing branch (checkout / failsafe)

```bash
git -C $ROOT/apaleo fetch --prune
git -C $ROOT/apaleo worktree add "$ROOT/worktrees/<branch>/apaleo" <branch>
# or, if only on remote:
git -C $ROOT/apaleo worktree add --track -b <branch> "$ROOT/worktrees/<branch>/apaleo" origin/<branch>
```

Then ff-only update inside the worktree: `git -C $APALEO pull --ff-only origin <branch>`.

Same for `$ROOT/development`, `$ROOT/identity`, `$ROOT/agent-skills`, and `$ROOT/angular-api-proxy` when those worktrees are required.

## Sync with master

Use `/sync-master` only. Never checkout `master` in `$WT`. On conflicts: list files, open them in the editor, **stop** for manual resolve — no auto-resolve of conflicted hunks unless the skill’s resolve protocol applies.

## Cleanup

`/worktree-list` inventory · `/worktree-remove` after PR merged/closed (with confirmation) · `/open-rider` quit Rider + open `$APALEO/Apaleo.sln` (Identity `Apaleo.Identity.sln` only if asked).
