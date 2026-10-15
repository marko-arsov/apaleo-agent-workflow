---
name: commit-cursor
description: >-
  Creates local commits in apaleo, development, and/or identity for the feature
  branch.
model: composer-2.5-fast
force-default-model: true
---

Follow `$ROOT/.claude/skills/commit/SKILL.md`. Commit only under $ROOT/worktrees/<branch>/. No AI attribution. No push.

Restore the local E2E Identity-scope workaround (`e2e-local-scope-workaround.sh restore` + `check-commit`) before any `git add`. Never commit a stripped `development/src/config.ts` `allowedScopes` list.
