---
name: commit-and-push-cursor
description: >-
  Commits then safely pushes the Apaleo feature branch in worktree repos.
  Does not open PRs.
model: grok-4.7-low-fast
force-default-model: true
---

Follow `$ROOT/.claude/skills/commit-and-push/SKILL.md` and `$ROOT/.claude/skills/references/worktrees.md`.

Operate under feature worktrees only. Run commit rules then push rules. No force-push. No PR create. Restore the local E2E Identity-scope workaround before commit (`references/e2e-missing-identity-scopes.md`).
