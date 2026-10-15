---
name: update-agent-skills
description: Mechanical wrapper. Runs the sibling script and presents its outcome clearly. Stops on ASK.
disable-model-invocation: true
---

# Update agent skills

Read `$ROOT/.claude/skills/references/chat-output.md`. Run the script and present its outcome
according to that reference. Stop.

If the check-only run says an update is available, ask whether to run the script again with
`--apply` to fast-forward the local `agent-skills` clone. Do not claim that plugins were installed:
the apply run asks separately which named plugins to install or upgrade.

```bash
"$ROOT/.claude/skills/update-agent-skills/update-agent-skills.sh" "$@"
```

Do **not** read repo files, grep, explore, restate rules, or "verify" another way.

Ambiguity (dirty worktree, diverged branch, lock held by another branch, missing args) → stop and ask. Do not investigate.
