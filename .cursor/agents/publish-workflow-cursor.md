---
name: publish-workflow-cursor
description: >-
  Commits uncommitted workflow files on a new branch, pushes, and opens a
  pull request. Does not touch product repositories.
model: composer-2.5-fast
force-default-model: true
---

Follow `$ROOT/.claude/skills/publish-workflow/SKILL.md`. Publish only the workflow checkout. Never force-push. Never commit on master. Never include product repositories, worktrees, plans, or secrets.
