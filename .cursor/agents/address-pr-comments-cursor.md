---
name: address-pr-comments-cursor
description: >-
  Apaleo /address-pr-comments on Cursor Grok. Never Cursor on-demand Claude;
  do not hand off to Claude Code.
model: grok-4.7-high
force-default-model: true
---

# /address-pr-comments — host routing

**Never** use Cursor’s Claude Opus/Sonnet (on-demand billing).
**Do not** hand off to Claude Code — run this skill **here on Grok**.

Follow `$ROOT/.claude/skills/address-pr-comments/SKILL.md` fully.
Manual use is analysis-first: explain every thread and wait for the user's selected options before edits.
This agent also owns explicit `--bugbot` and `--draft-bugbot-replies` modes.

Canonical: `$ROOT/.claude/skills/references/model-routing.md`.
