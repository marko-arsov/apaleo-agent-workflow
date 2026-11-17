---
name: specify-cursor
description: >-
  Apaleo /specify on Cursor Claude Opus 5.5 high: spec-driven planning that resolves ambiguity
  with the user and writes a plan a cheaper implementation model can execute. Never implements.
model: claude-opus-5-5-high
force-default-model: true
---

# `/specify` on Cursor

Follow `$ROOT/.claude/skills/specify/SKILL.md` and its canonical procedure,
`$ROOT/.claude/skills/references/specify-process.md`, exactly.

On Cursor, rename this chat per `$ROOT/.claude/skills/references/cursor-chat-title.md`
(status `specify`).

Planning runs on the deep band on purpose: implementation later runs on a cheaper route from the
written plan alone. Write only plan artifacts, end with the approval question, and stop.
