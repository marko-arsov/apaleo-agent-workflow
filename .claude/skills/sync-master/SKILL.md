---
name: sync-master
description: >-
  Merge origin/master into the feature worktree. Fast path is shell-only; if
  conflicts remain, resolve clear merge conflicts and ask only when unsafe.
---

# Sync master

Read `$ROOT/.claude/skills/references/chat-output.md`. Run the script first and present its outcome
according to that reference. `--remote-branch <branch>` is the internal
mode used by `/push` to merge `origin/<branch>` before a non-force push. If the runner already
reported `sync-master conflicts` or a merge state is already active, skip this
step and go straight to the conflict path.

```bash
"$ROOT/.claude/skills/sync-master/sync-master.sh" "$@"
```

Short ids like `c3331`, `hc3331`, or `hc-3331` are resolved by the script to the current
matching worktree first, then a unique existing worktree/plan branch. Do not ask
the user to confirm that unique resolution.

If it exits `0`, stop. Do **not** read repo files, grep, explore, restate rules,
or verify another way on the clean path.

Ambiguity before a merge starts (dirty worktree, diverged branch, missing args,
not under `$ROOT/worktrees/<branch>/`) → stop and ask. Do not investigate.

## Conflict path (`exit 10`)

Only now inspect files. The failed merge has left conflict state in one or more
worktree repos; do **not** abort it.

For each conflicted repo:

1. Confirm state with `git status --short`, `git diff --name-only --diff-filter=U`,
   and the active operation (`git status` says merge/rebase).
2. Understand both sides before editing:
   - `ours` = feature branch / plan in `$ROOT/ai-plans/<branch>/`
   - `theirs` = `origin/master`
   - Use `git diff`, `git diff --cc`, `git log --oneline --left-right --merge`,
     nearby code, and cited plan artifacts. Use PR/ticket context only when it is
     already local or cheaply available.
3. Resolve hunks by preserving both intents when possible. If behavior,
   public contracts, migrations, tenancy, money, authz, secrets, or tests
   collide in a way that is not obviously safe, ask a concise numbered question
   and leave the merge state intact.
4. Never blanket `-X ours` / `-X theirs`. Never invent behavior. Never weaken,
   skip, delete, or quarantine tests to get green.
5. Run the cheapest relevant checks for touched repos when feasible:
   - C# compile or targeted tests for touched projects when conflict edits can affect build.
   - No local E2E and no staging/prod tests from this skill.
6. Ensure no conflict markers remain (`rg '<<<<<<<|=======|>>>>>>>'` in touched
   repos), stage resolved files, and finish the merge with `git commit --no-edit`
   (or `git merge --continue` if Git requires it).
7. Do not push. Summarize resolved files, important trade-offs, checks run, and
   any remaining human decisions.
