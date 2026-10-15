---
name: migration-script-cursor
description: >-
  Generates the production EF SQL for a merged apaleo migration from parked
  master. Does not apply, commit, or push the script.
model: grok-4.7-medium-fast
force-default-model: true
---

Follow `$ROOT/.claude/skills/migration-script/SKILL.md` and `$ROOT/.claude/skills/references/db-migrations.md`.

Run the script. Do not apply the SQL, commit `migration.sql`, or push. Parked `apaleo` stays on `master`.
