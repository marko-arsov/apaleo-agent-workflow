---
name: e2e-stack-release
description: Mechanical wrapper. Runs the sibling script and presents its outcome clearly. Stops on ASK.
disable-model-invocation: true
---

# E2E stack release

Read `$ROOT/.claude/skills/references/chat-output.md`. Run the script and present its outcome
according to that reference. Stop. On a successful release it performs the lock's bounded
Docker cleanup (only unreferenced branch images and BuildKit cache); it never prunes Compose volumes,
containers, or networks.

```bash
"$ROOT/.claude/skills/e2e-stack-release/e2e-stack-release.sh" "$@"
```

Do **not** read repo files, grep, explore, restate rules, or "verify" another way.

Ambiguity (dirty worktree, diverged branch, lock held by another branch, missing args) → stop and ask. Do not investigate.
