---
name: publish-workflow
description: Mechanical wrapper. Runs the sibling script and presents its outcome clearly. Stops on ASK.
disable-model-invocation: true
---

# Publish workflow

Read `$ROOT/.claude/skills/references/chat-output.md`. Run the script, present its outcome
according to that reference, and stop.

```bash
"$ROOT/.claude/skills/publish-workflow/publish-workflow.sh" "$@"
```

Do **not** read repo files, grep, explore, restate rules, or "verify" another way.

The script publishes uncommitted files in the workflow checkout. It creates
`workflow/<summary>`, commits there, pushes, and opens a pull request against `master`.
It does not run by itself. A quoted summary is optional. When omitted, the script
derives one from the changed files. The pull request body is a few short bullets
for the commands, pipeline, tests, and docs that changed. It refuses product repositories, worktrees,
plans, secrets, a dirty `master` that is not `origin/master`, and any force-push.

Ambiguity (existing branch, unsafe path) → stop and ask. Do not investigate.
