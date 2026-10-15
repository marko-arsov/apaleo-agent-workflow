---
name: implement-tests-cursor
description: Apaleo test-only TDD stage on Cursor Claude Sonnet; never edits product code.
model: claude-sonnet-5-thinking-high
force-default-model: true
---

Follow `$ROOT/.claude/skills/implement-tests/SKILL.md` fully.
This is the default modest-test suggestion. `/specify` selects Cursor Opus for four or more planned
test files or a substantial test diff; the confirmed `pipeline.json` route always wins. Stay within
`pipeline.json.test_paths`, write the red-phase report, and do not commit or push.
