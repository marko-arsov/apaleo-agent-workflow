---
name: checkout-branch
description: Mechanical wrapper. Runs the sibling script and presents its outcome clearly. Stops on ASK.
disable-model-invocation: true
---

# Checkout branch

Read `$ROOT/.claude/skills/references/chat-output.md`. Run the script, present its outcome
according to that reference, and stop.

```bash
"$ROOT/.claude/skills/checkout-branch/checkout-branch.sh" "$@"
```

Do **not** read repo files, grep, explore, restate rules, or "verify" another way.

Ambiguity (dirty worktree, diverged branch, lock held by another branch, missing args) → stop and ask. Do not investigate.
