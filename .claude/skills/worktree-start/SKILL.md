---
name: worktree-start
description: Mechanical wrapper. Runs the sibling script and presents its outcome clearly. Stops on ASK.
disable-model-invocation: true
---

# Worktree start

Existing worktree references may be a short issue id (`sl129`, `hc3331`), issue text, or a GitHub PR URL. A genuinely new
worktree still needs the full `<github-login>/<issue-id>-<slug>` branch name.

Read `$ROOT/.claude/skills/references/chat-output.md`. Run the script, present its outcome
according to that reference, and stop.

```bash
"$ROOT/.claude/skills/worktree-start/worktree-start.sh" "$@"
```

Do **not** read repo files, grep, explore, restate rules, or "verify" another way.

No issue, branch, or PR → follow `$ROOT/.claude/skills/references/feature-argument.md` before
running the script. Ask only when that feature is not certain. A new worktree still needs the
full branch name when the id does not already exist.

Ambiguity (dirty worktree, diverged branch, lock held by another branch) → stop and ask. Do not investigate.
