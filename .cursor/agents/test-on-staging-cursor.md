---
name: test-on-staging-cursor
description: >-
  Execution-first Apaleo /test-on-staging on Cursor Grok. Runs every safe
  available check before requesting a minimal human action.
model: grok-4.7-high
force-default-model: true
---

# /test-on-staging — host routing

**Never** use Cursor’s Claude Opus/Sonnet (on-demand billing).
**Do not** hand off to Claude Code — run this skill **here on Grok**.

Follow `$ROOT/.claude/skills/test-on-staging/SKILL.md` fully, including `staging-smoke.md`. Run safe read-only and eligible disposable-test checks autonomously, use available browser tools, and stop only for the skill's single exact checkpoint or irreducible human step.

Canonical: `$ROOT/.claude/skills/references/model-routing.md`.
