---
name: add-convention
description: >-
  Turns a recurring, mechanically detectable Apaleo convention plus one violating
  example into proposed edit-time and diff-time enforcement, an exemption entry,
  and an architecture-test proposal when appropriate. Never applies proposals
  without explicit approval.
disable-model-invocation: true
argument-hint: "<plain-English rule> + <violating example>"
---

# Add convention

Internal Tier-1 generator. Users enter through `/add-rule`; do not route around its checkability
question or recurrence ratchet.

Use this only for a repeated mistake with a precise mechanical signal and an established
alternative. Prefer an existing compiler analyzer, formatter, linter, or test over custom logic.
Do not turn ambiguous style advice or a one-off review preference into a global rule.

Read:

- `$ROOT/.claude/conventions/registry.json`
- `$ROOT/.claude/conventions/allowlist.json`
- `$ROOT/.claude/hooks/conventions.py`
- the relevant reference that establishes the correct alternative

From the supplied rule and violating example, propose:

1. A narrow registry entry for the shared `PreToolUse`/diff detector.
2. A matching root-local Semgrep rule when AST matching improves precision.
3. Exact exemption entries only when the user identifies an approved exception; every entry needs
   a rule id, exact path, and reason.
4. A repository architecture-test patch only for a real dependency or architectural boundary.
   For a small syntax rule, mark this layer `not applicable` with a reason instead of manufacturing
   a test. Store any architecture-test patch as a proposal; never apply it to a product repository.

Show the proposed unified diffs, expected matches, false-positive risks, and cost classification.
Stop for explicit approval before changing workflow files. Approval never authorizes repository
code changes. After an approved workflow-only update, run:

```bash
python3 "$ROOT/.claude/hooks/conventions.py" validate
python3 -m unittest discover "$ROOT/.claude/skills/pipeline/tests" -v
```

Keep recurring checks deterministic. The model is used only for this opt-in rule-authoring request.
