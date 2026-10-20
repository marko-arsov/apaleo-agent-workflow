---
name: commit-and-push
description: Mechanical wrapper. Runs the sibling script and presents its outcome clearly. Stops on ASK.
disable-model-invocation: true
---

# Commit and push

Run the composite script. It commits first and invokes push only if commit succeeds. Push merges a
clean `origin/<branch>` update automatically. It resolves `sl100`, `sl-100`, `c3331`, `hc3331`, or `HC-3331` to the current matching worktree
first, then a unique existing branch. Read
`$ROOT/.claude/skills/references/chat-output.md` and present the script's outcome according to that
reference. If it exits `10` with `HANDOFF_CONFLICTS=1`, follow `/sync-master`'s conflict
path, finish the merge commit, then run `push.sh` again. Stop on any other non-zero exit.

```bash
"$ROOT/.claude/skills/commit-and-push/commit-and-push.sh" "$@"
```

Do **not** read repo files, grep, explore, restate rules, or "verify" another way.

Argument handling:

- No issue, branch, or PR → follow `$ROOT/.claude/skills/references/feature-argument.md` before
  running the script. Ask only when that feature is not certain. Do not require the dash or the
  full branch name.
- If the reply contains exactly one issue id, pass that id to the script; do not manually enumerate
  worktree paths or resolve it yourself.
- The script commits and pushes every attached repository for the resolved branch. Never ask the user
  to choose between `apaleo`, `development`, or "both".

Real ambiguity (several branches for the same id, dirty state outside the resolved worktree, or a lock
held by another branch) → stop and ask. Do not investigate.

## Automated execution (`/implement-pipeline`)

When selected, this stage is **required**. Commit/push only feature worktrees, never master and never force-push.
No changes to commit is success. Stop for diverged/behind remotes, dirty state outside the resolved
worktree, missing branch, failed push, AI attribution, or a local E2E scope strip that would be
committed. Fix a mechanical blocker externally, then rerun this idempotent script stage.
