---
name: open-rider-cursor
description: >-
  Resolves branch/PR/HC, ensures Apaleo feature worktree, quits Rider if open,
  opens Apaleo.sln (mechanics — Cursor Grok).
model: grok-4.7-low-fast
force-default-model: true
---

# /open-rider — host routing

**Never** use Cursor on-demand Claude.

Follow `$ROOT/.claude/skills/open-rider/SKILL.md`.

Prefer running the script (do not re-implement):

```bash
$ROOT/.claude/skills/open-rider/open-rider.sh <branch|PR|#N|HC-####>
```

Mains stay on `master`. Never open parked `$ROOT/apaleo`. After success, optional `move_agent_to_root` → `$WT`.
