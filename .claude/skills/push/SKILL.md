---
name: push
description: Mechanical wrapper. Runs the sibling script and presents its outcome clearly. Stops on ASK.
disable-model-invocation: true
---

# Push

Run the script. It merges a clean `origin/<branch>` update before pushing. Read
`$ROOT/.claude/skills/references/chat-output.md` and present its outcome according to that reference.
If it exits `10` with `HANDOFF_CONFLICTS=1`, resolve the active merge using `/sync-master`'s
conflict path, finish the merge commit, then run this script again. Stop on any other non-zero exit.

```bash
"$ROOT/.claude/skills/push/push.sh" "$@"
```

Do **not** read repo files, grep, explore, restate rules, or "verify" another way.

No issue, branch, or PR → follow `$ROOT/.claude/skills/references/feature-argument.md` before
running the script. Ask only when that feature is not certain.

Ambiguity (dirty worktree, lock held by another branch) → stop and ask. Do not investigate.
