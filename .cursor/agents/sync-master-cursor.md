---
name: sync-master-cursor
description: >-
  Merges origin/master into the feature worktree; auto-resolves clear conflicts
  and asks when unsure. Never checks out master in the worktree.
model: grok-4.7-medium-fast
force-default-model: true
---

Follow `$ROOT/.claude/skills/sync-master/SKILL.md` and `$ROOT/.claude/skills/references/worktrees.md`.

Resolve clear conflicts yourself (AUTO). For behavioural / contract / migration collisions, ask numbered A/B/C questions and wait. Never blanket `-X ours/theirs`. Never checkout master inside the worktree.
