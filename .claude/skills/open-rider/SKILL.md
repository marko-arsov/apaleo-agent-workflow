---
name: open-rider
description: Mechanical wrapper. Runs the sibling script and presents its outcome clearly. Stops on ASK.
disable-model-invocation: true
---

# Open Rider

Read `$ROOT/.claude/skills/references/chat-output.md`. Run the script, present its outcome
according to that reference, and stop.

Default target: resolve the supplied issue id, PR, or branch and open
`$ROOT/worktrees/<resolved-branch>/apaleo/Apaleo.sln`. The presence of `development`, `identity`, or
another attached repository is not an ambiguity and does not change that default. Only apply a
different repository/solution target when the user explicitly requests it.

```bash
"$ROOT/.claude/skills/open-rider/open-rider.sh" "$@"
```

Do **not** read repo files, grep, explore, restate rules, or "verify" another way.

Pass an issue id such as `SL-100` directly to the script. Do not require the full branch name or
manually enumerate matching worktree paths. Ambiguity (dirty worktree, diverged branch, lock held by
another branch, missing args) → stop and ask. Do not investigate.
