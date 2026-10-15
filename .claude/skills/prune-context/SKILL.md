---
name: prune-context
description: >-
  Audits the compact Apaleo AGENTS.md against recent local pipeline evidence and
  proposes low-value lines for removal. Use for deliberate context maintenance;
  it reports only and never deletes instructions unattended.
disable-model-invocation: true
argument-hint: "[--days N]"
---

# Prune context

Generate the deterministic report first:

```bash
python3 "$ROOT/.claude/skills/prune-context/prune_context.py" \
  --root "$ROOT" $ARGUMENTS
```

Then inspect each candidate against `WORKFLOW.md`, the nearest reference, and safety invariants.
Missing recent evidence is not proof that a line is useless. Never propose removal of plan
immutability, worktree/base-branch safety, test-integrity, secret, destructive-environment, or
speak-as-user controls.

The report also applies the rule ratchet mechanically:

- zero violations six months after `added` → deletion candidate;
- Tier 3 with two or more violations → mandatory `/add-rule` escalation candidate.

Do not turn an escalation candidate into another prose edit.

Return a proposed unified diff with one reason per deletion. Stop for approval. This skill never
applies its own proposal, even when the user invoked it unattended or from automation.
