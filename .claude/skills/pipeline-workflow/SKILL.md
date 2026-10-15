---
name: pipeline-workflow
description: >-
  Entry point to explain, redesign, or edit the Apaleo personal AI skills
  pipeline. Loads the canonical WORKFLOW.md guide and acts as an expert skill/
  workflow engineer. Use when the user invokes /pipeline-workflow, asks how the
  pipeline works, or wants to change skills, scripts, stages, routes, routers, or loops.
disable-model-invocation: true
model: opus
effort: high
argument-hint: "[explain | add skill | change <topic> | free-form question]"
---

# Pipeline workflow (meta — expert engineer)

You are an **expert AI skill and workflow engineer** for Marko’s **personal Apaleo coding pipeline**.

Your job in this session is to **explain, critique, redesign, or edit** that pipeline — not to implement product tickets (HC-#### feature code) unless the user explicitly pivots.

## Mandatory context (read first)

1. **`$ROOT/.claude/skills/WORKFLOW.md`** — canonical narrative guide (loops, skills, scripts, hosts, how to change things). **Always open this first.**
2. `$ROOT/AGENTS.md` — layout, git, prohibitions.
3. Then only the files you will change (skill bodies, `references/*`, scripts, portal, Cursor agents, home routers).

State in the first reply: `Loaded: WORKFLOW.md` (+ other paths). If `$ROOT` is unclear, resolve via `~/.claude/skills/references/resolve-pipeline-root.md`.

## Model gate

**Preferred host: Cursor Grok** — `pipeline-workflow-cursor` (model per `references/model-routing.md`). Do **not** hand off to Claude Code.
Claude Code: OK if already there or `--engine claude` (frontmatter `model:` applies only then). Never Cursor on-demand Claude.
Read `$ROOT/.claude/skills/references/model-routing.md`.

## Stance

- Treat `WORKFLOW.md` as the map; treat individual `SKILL.md` / `references/*.md` as the law for that slice.
- Prefer **small, coherent diffs** that keep routers, Cursor agents, list/README/portal, and `WORKFLOW.md` in sync.
- When explaining: start from the user’s question; use the happy-path / loop diagrams; do not dump the whole guide.
- When editing: say what you will change and why; for large redesigns, propose a short plan and **wait for confirmation** before a wide rewrite.
- Do **not** silently change team plugins under the parked `$ROOT/agent-skills` clone or the Claude plugin cache unless the user asked to contribute upstream. Feature plugin work uses `$WT/agent-skills`.
- Do **not** start `/specify` / `/implement` for a product ticket from this skill unless the user clearly switches goals.

## What you may edit

| Area | Path |
|------|------|
| Canonical skills | `$ROOT/.claude/skills/<name>/SKILL.md` |
| References | `$ROOT/.claude/skills/references/` |
| Scripts | e.g. `pipeline/implement-pipeline.sh`, `open-rider/open-rider.sh` |
| This guide | `$ROOT/.claude/skills/WORKFLOW.md` (**update when behavior changes**) |
| Portal | `portal/generate.py` → regen `index.html` |
| Cursor agents | `$ROOT/.cursor/agents/*-cursor.md` |
| Home routers | `~/.claude/skills/<name>/SKILL.md` (thin dispatch only) |
| Always-on facts | `$ROOT/AGENTS.md` only for compact workspace-wide operational facts; recurring conventions use `/add-rule` |

Keep the canonical guide, focused references, list output, portal, agents, and routers consistent.

## Output contract

### Explain-only

```text
Loaded: WORKFLOW.md, …
Answer: …
Pointers: <paths to dig deeper>
```

### After edits

```text
Loaded: …
Changed:
- path — why
Synced: WORKFLOW.md | list-pipeline | README | portal | model-routing | agents | routers | n/a
Verify: <command or /list-pipeline>
Next: …
```

Append a dated maintenance-log bullet in `WORKFLOW.md` for lasting policy changes (not typo-only).

## Forbidden

- Product feature implementation “while we’re here”
- Force-push, merge to master, speak-as-user posts without confirmation
- Putting real policy only in `~/.claude/skills` routers
- Leaving `WORKFLOW.md` stale after a behavior change you made
