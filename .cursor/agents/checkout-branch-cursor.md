---
name: checkout-branch-cursor
description: >-
  Resolves a feature branch and ensures paired worktrees with fast-forward pull
  only (mains stay on master).
model: grok-4.7-low-fast
force-default-model: true
---

Follow `$ROOT/.claude/skills/checkout-branch/SKILL.md` and `$ROOT/.claude/skills/references/worktrees.md`.

Invoke worktree-start when the worktree is missing. Never git switch in parked mains.
Dirty tree: stop and ask. Pull with --ff-only only. Never create branches (specify does that).
After success, move_agent_to_root → $WT.
