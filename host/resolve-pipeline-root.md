# Resolve the Apaleo workflow root

Use the active workspace path, or the current working directory. Resolve symlinks, then walk
upward to a directory containing `AGENTS.md`, `.claude/skills`, `apaleo`, and `development`.
Verify that its instructions identify the Apaleo workspace. This also handles feature worktrees.

Run `~/.claude/skills/references/resolve-pipeline-root.sh [path]` for the deterministic check.
It prints `apaleo` and the root separated by a tab, or exits 1 outside that workspace.
Load the root's `AGENTS.md` and the selected canonical skill. There is no alternate pack fallback.
