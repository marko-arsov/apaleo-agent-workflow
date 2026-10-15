---
name: wizard
description: "Apaleo-only workflow: wizard. Resolve the Apaleo workspace and follow its canonical procedure."
---

# wizard (Apaleo)

Read `~/.claude/skills/references/resolve-pipeline-root.md` and resolve the current workspace.
This entry point applies only inside the Apaleo workspace. If resolution fails, stop;
use the project's af-* skills when it uses the separate Agent Flow workflow.

Read `$ROOT/AGENTS.md`, then fully follow `$ROOT/.claude/skills/wizard/SKILL.md`.
The canonical Apaleo procedure owns all behaviour, arguments, and checks.
