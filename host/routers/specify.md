---
name: specify
description: "Apaleo-only planning: research and present a plan for approval before implementation."
---

# specify (Apaleo)

Invoking specify authorizes research and planning artifacts only, including extensions to existing
issues. Present the plan or revision, ask for implementation approval, and stop before code, test,
configuration, or generated-product edits. Follow the canonical approval boundary below.

Read `~/.claude/skills/references/resolve-pipeline-root.md` and resolve the current workspace.
This entry point applies only inside the Apaleo workspace. If resolution fails, stop;
use the project's af-* skills when it uses the separate Agent Flow workflow.

Read `$ROOT/AGENTS.md`, then fully follow `$ROOT/.claude/skills/specify/SKILL.md`.
The canonical Apaleo procedure owns all behaviour, arguments, and checks.
