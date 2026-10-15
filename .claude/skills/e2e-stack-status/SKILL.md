---
name: e2e-stack-status
description: Mechanical wrapper. Runs the sibling script and presents its outcome clearly. Stops on ASK.
disable-model-invocation: true
---

# E2E stack status

Read `$ROOT/.claude/skills/references/chat-output.md`. Run the script, present its outcome
according to that reference, and stop.

```bash
"$ROOT/.claude/skills/e2e-stack-status/e2e-stack-status.sh" "$@"
```

Do **not** read repo files, grep, explore, restate rules, or "verify" another way.

Ambiguity (dirty worktree, diverged branch, lock held by another branch, missing args) → stop and ask. Do not investigate.
