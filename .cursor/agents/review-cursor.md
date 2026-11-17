---
name: review-cursor
description: >-
  Apaleo /review on Cursor GPT-5.6 Sol. Full-pipeline routing may select
  Cursor Claude or native fallbacks instead.
model: gpt-5.6-sol-high
force-default-model: true
---

# /review — host routing

For full-pipeline work, use the exact route and fallback order confirmed in `pipeline.json`.
Cursor-hosted Claude/GPT is preferred until its model allowance is exhausted; Cursor Grok and
native Claude Code/Codex routes are explicit fallbacks, not prohibited providers.

Follow `$ROOT/.claude/skills/review/SKILL.md` fully.
On Cursor, rename this chat per `$ROOT/.claude/skills/references/cursor-chat-title.md`
(status `review`).

Canonical: `$ROOT/.claude/skills/references/model-routing.md`.
