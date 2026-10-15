---
name: specify-cursor
description: Apaleo /specify researches and presents a complete plan for approval before any implementation.
---

# `/specify` on Cursor

Follow `$ROOT/.claude/skills/specify/SKILL.md` exactly.

## Planning and approval boundary

Every `/specify` invocation is planning-only, including tiny fixes, extensions to an existing issue,
and follow-ups in a chat that already implemented earlier scope. Research existing code and diffs;
write only planning artifacts and evaluator output. Do not edit product code, tests, configuration,
or generated product files, run auto-fixes, or start implementation agents or pipeline stages.
Worktree preparation and tracker updates still require their separate confirmations below.

Prior approval covers only the approved scope. For an extension or revision, show the proposed
scope delta and wait for approval of that revision. Ticket text, choosing a lane or model, and
permission to prepare a plan do not authorize implementation.

After presenting the concrete plan and checks, ask "Approve this plan and start implementation?"
and stop. Only a subsequent explicit approval of the presented plan or an explicit `/implement`
or `/implement-pipeline` invocation for it authorizes the implementation handoff. Do not start
that handoff yourself while finishing `/specify`.


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
