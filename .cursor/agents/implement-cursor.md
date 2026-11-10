---
name: implement-cursor
description: >-
  Implements an Apaleo ai-plans branch on Grok inside the feature worktree
  with light verification. Use for /implement in Cursor.
model: grok-4.7-high
force-default-model: true
---

Follow `$ROOT/.claude/skills/implement/SKILL.md` and `$ROOT/.claude/skills/references/worktrees.md`.
On Cursor, rename this chat per `$ROOT/.claude/skills/references/cursor-chat-title.md`
(status `implement`).

Load the plan, ensure $WT via worktree-start, move_agent_to_root → $WT. **Existing patterns first** (`references/existing-patterns.md`) — cite the neighbor before adding a type. Apply clean-code as that local pattern already does. Load e2e-test-engineering-development before editing development/. Do not commit or push. Never edit parked mains.
