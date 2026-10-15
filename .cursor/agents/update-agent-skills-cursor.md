---
name: update-agent-skills-cursor
description: >-
  Syncs $ROOT/agent-skills and compares/installs @apaleo Claude plugins after
  asking the user.
model: grok-4.7-low-fast
force-default-model: true
---

Follow `$ROOT/.claude/skills/update-agent-skills/SKILL.md`.

Fetch and report first. Ask before pull/install. Never force-reset agent-skills. The Apaleo workflow checkout is out of scope for this skill.
