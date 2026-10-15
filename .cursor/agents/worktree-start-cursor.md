---
name: worktree-start-cursor
description: >-
  Creates or reuses apaleo/development/identity/agent-skills/angular-api-proxy git worktrees under
  $ROOT/worktrees/<branch>/, leaving mains on master.
model: grok-4.7-low-fast
force-default-model: true
---

Follow `$ROOT/.claude/skills/worktree-start/SKILL.md` and `$ROOT/.claude/skills/references/worktrees.md`. Identity: `$ROOT/.claude/skills/references/identity.md`.

Never git switch feature branches in $ROOT/apaleo, $ROOT/development, $ROOT/identity, $ROOT/agent-skills, or $ROOT/angular-api-proxy.
After success, move_agent_to_root → $WT.
