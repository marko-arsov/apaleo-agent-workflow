---
name: peer-pr-review
description: "Apaleo-only workflow: peer-pr-review. Resolve the Apaleo workspace and follow its canonical procedure."
---

# peer-pr-review (Apaleo)

Read `~/.claude/skills/references/resolve-pipeline-root.md` and resolve the current workspace.
This entry point applies only inside the Apaleo workspace. If resolution fails, stop;
use the project's af-* skills when it uses the separate Agent Flow workflow.

Read `$ROOT/AGENTS.md`, then fully follow `$ROOT/.claude/skills/peer-pr-review/SKILL.md`.
The canonical Apaleo procedure owns all behaviour, arguments, and checks.
