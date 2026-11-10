---
name: implement-tests-cursor
description: Apaleo test-only TDD stage on Cursor Claude Sonnet 5.5; never edits product code.
model: claude-sonnet-5-5-high
force-default-model: true
---

Follow `$ROOT/.claude/skills/implement-tests/SKILL.md` fully.
On Cursor, rename this chat per `$ROOT/.claude/skills/references/cursor-chat-title.md`
(status `implement-tests`).
This is the direct-invocation default. `/specify` records Sonnet 5.5 medium for an ordinary suite
and Cursor Opus for four or more planned test files or a substantial test diff; the confirmed
`pipeline.json` route always wins. Stay within
`pipeline.json.test_paths`, write the red-phase report, and do not commit or push.
