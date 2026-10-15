---
name: specify-cursor
description: Apaleo /specify with task-aware model advice; concise complete plan for the manual or full-pipeline lane.
---

# `/specify` on Cursor

Follow `$ROOT/.claude/skills/specify/SKILL.md` exactly.

Research first, then ask focused rounds only for material ambiguity. Do not create plans or
worktrees before the required user confirmations. Confirm the execution lane first. For a defect, record expected behavior, reproduction,
suspected cause/scope, and a regression check that fails before the fix. Recommend manual
`/implement` for an isolated deterministic bugfix or a small established-pattern follow-up;
otherwise use the full pipeline, with review when the defect is security, billing, tenancy/OPA,
schema, public-contract, or data-correction work.
Treat the original request as a hypothesis: identify gaps, incorrect logic, contradictions, or a
better established approach and recommend the change before planning it. When the agreed definition
materially changes a Linear issue, show the exact update, obtain action-specific confirmation, write
the plan files, then update Linear.
For the full pipeline, also confirm:

- selected stages in canonical order;
- exact provider/model/reasoning route for every selected AI stage;
- any ordered fallback (default none).

Write `prompt.md`, `product.md`, `implementation.md`, `deferred-scope.md`, and valid
`pipeline.json`. Include the focused tests and commands the selected lane needs. Next: `/implement
<task>` for manual work, otherwise `/implement-pipeline <task>`.

Canonical references: `specify-process.md`, `pipeline-stages.md`, and `model-routing.md`.
