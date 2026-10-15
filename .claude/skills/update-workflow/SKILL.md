---
name: update-workflow
description: Mechanical wrapper. Runs the sibling script and presents its outcome clearly. Stops on ASK.
disable-model-invocation: true
---

# Update workflow

Read `$ROOT/.claude/skills/references/chat-output.md`. Run the script, present its outcome
according to that reference, and stop.

```bash
"$ROOT/.claude/skills/update-workflow/update-workflow.sh" "$@"
```

Do **not** read repo files, grep, explore, restate rules, or "verify" another way.

The script fast-forwards a clean workflow `master` from `origin/master`, then runs
`install.sh` so new commands are registered. It does not run by itself. It refuses a
dirty checkout, any branch other than `master`, and a history that cannot fast-forward.
It does not touch product repositories. This is not `/sync-master`.

Ambiguity (dirty checkout, wrong branch, diverged master) → stop and ask. Do not investigate.
