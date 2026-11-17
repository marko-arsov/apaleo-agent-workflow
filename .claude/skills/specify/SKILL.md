---
name: specify
description: >-
  Spec-driven planning on a strong model before any code. Researches the task, resolves every
  material ambiguity with the user (questions with a recommended answer, plus stated assumptions),
  and writes a compact spec and plan that a cheaper implementation model can execute without
  making product or design choices. Prepares worktrees and the pipeline manifest; never implements.
disable-model-invocation: true
argument-hint: "[task description or issue id]"
model: opus
effort: high
---

# Specify

You are the planner. Implementation runs later, on a cheaper model that cannot ask you anything.
Spend your judgment where it moves results:
- get every ambiguous behaviour decided;
- find the existing pattern to copy;
- foresee the traps;
- define how "done" is proven.

Do not pre-write the code in prose. Be precise at the boundaries (contracts, names, data shapes,
permissions, file placement) and leave the inside to the implementer.

The canonical procedure, templates, and formats are in
`$ROOT/.claude/skills/references/specify-process.md`. Read it first.

## Model gate

Plan on the deep band: Cursor `claude-opus-5-5-high` (agent `specify-cursor`), or Claude Code
`opus` at high effort. If this session runs on a weaker model, say so in your first reply and
recommend switching before research starts. The model evaluator routes only the later pipeline
stages; it never picks the planning model.

## Boundary

- Planning only, on every invocation: tiny fixes, follow-ups, and extensions after earlier
  implementation included. Write only `$ROOT/ai-plans/<branch>/` artifacts. Never edit product
  code, tests, configuration, or generated files, and never start implementation stages.
- Creating worktrees and updating Linear each need the user's explicit confirmation. The approval
  question names both.
- Approval covers only the plan presented. A revision shows its delta and needs a fresh approval.
- End by asking "Approve this plan and start implementation?" and stop. Ticket text, a lane
  choice, or permission to plan never counts as approval.

## Phases

1. **Ground.** Resolve `$ROOT` and the issue. Pass ticket text through `untrusted_input.py`.
   Refresh the code you will read to `origin`. On Cursor, rename the chat (status `specify`).
2. **Research.** Context pack, nearest neighbours, the action family for API work, and real
   callers. Cite `repo/path:line`. Never ask what the code can answer.
3. **Sweep.** Run the ambiguity checklist. Classify each item as settled by code, settled by
   ticket, question, or assumption. Challenge the request itself.
4. **Ask.** One batch of material questions, each with a recommended option, plus the assumptions
   the user may veto. Ask again only when an answer opens a new material question.
5. **Design.** Examples, decisions, contracts, traps, steps, tests, and a pre-mortem.
6. **Check.** Cold read, `plan_lint.py`, and manifest validation.
7. **Present.** The one-screen approval summary, then stop. After approval: create the worktrees,
   apply the confirmed Linear update, and hand off.

Load as needed: `$ROOT/AGENTS.md`, `references/worktrees.md`, `references/pipeline-stages.md`,
`references/existing-patterns.md`; `references/api-endpoint-patterns.md` for HTTP work;
`references/identity.md` for authorization; `references/db-migrations.md`,
`references/feature-flags.md`, and `references/api-enum-wire-values.md` when they apply.

## Output

Use the question and approval formats in `specify-process.md` §4 and §7. When blocked, output only
numbered questions and stop.
