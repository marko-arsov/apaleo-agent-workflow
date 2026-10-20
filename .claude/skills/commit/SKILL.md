---
name: commit
description: Mechanical wrapper. Runs the sibling script and presents its outcome clearly. Stops on ASK.
disable-model-invocation: true
---

# Commit

Read `$ROOT/.claude/skills/references/chat-output.md`. Run the script, present its outcome
according to that reference, and stop.

```bash
"$ROOT/.claude/skills/commit/commit.sh" "$@"
```

Do **not** read repo files, grep, explore, restate rules, or "verify" another way.

No issue, branch, or PR → follow `$ROOT/.claude/skills/references/feature-argument.md` before
running the script. Ask only when that feature is not certain.

Ambiguity (dirty worktree, diverged branch, lock held by another branch) → stop and ask. Do not investigate.
