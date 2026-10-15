---
name: peer-rfc-review-cursor
description: >-
  Apaleo /peer-rfc-review: prefer Claude Code when usage credits remain; otherwise run on
  Cursor Grok (never Cursor on-demand Claude).
model: grok-4.7-high
force-default-model: true
---

# /peer-rfc-review — host routing

**Never** use Cursor’s Claude Opus/Sonnet (on-demand billing).

1. Run the budget check (from Apaleo `$ROOT`):
   ```bash
   python3 "$ROOT/.claude/skills/pipeline/claude_usage_check.py"
   ```
2. **Exit 0 (enough credits):** tell the user to run `/peer-rfc-review` in **Claude Code** (see model-routing). Do not continue on Grok unless they explicitly override.
3. **Exit 1 (not enough) or exit 2 (check failed):** run `/peer-rfc-review` **here on Grok** — follow `$ROOT/.claude/skills/peer-rfc-review/SKILL.md` fully.
4. This review is manual and separate from `/implement-pipeline`.

Canonical: `$ROOT/.claude/skills/references/model-routing.md`.
