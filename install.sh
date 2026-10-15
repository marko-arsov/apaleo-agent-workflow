#!/usr/bin/env bash
# Link this checkout into an Apaleo workspace and register the host commands.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install.sh <workspace>

Link this checkout into a workspace parent that already contains apaleo/ and
development/. Registers the Cursor and Claude Code commands. Safe to re-run.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ $# -ne 1 ]]; then
  usage >&2
  exit 2
fi

WORKFLOW_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
WORKSPACE="$(cd "$1" && pwd -P)"

if [[ ! -d "$WORKSPACE/apaleo" || ! -d "$WORKSPACE/development" ]]; then
  echo "workspace must contain apaleo/ and development/: $WORKSPACE" >&2
  exit 2
fi

LINKED=()

replace_owned() {
  local src="$1" dest="$2" marker="$3"
  mkdir -p "$(dirname "$dest")"
  if [[ -L "$dest" ]]; then
    if [[ "$(readlink "$dest")" == "$src" ]]; then
      LINKED+=("$dest")
      return 0
    fi
    echo "refusing to replace link $dest -> $(readlink "$dest")" >&2
    exit 2
  fi
  if [[ -e "$dest" ]]; then
    if ! grep -q -F -- "$marker" "$dest"; then
      echo "refusing to replace unrelated file $dest" >&2
      exit 2
    fi
    rm "$dest"
  fi
  ln -s "$src" "$dest"
  LINKED+=("$dest")
}

ensure_router() {
  local name="$1" router="$2"
  [[ -f "$router" ]] && return 0
  mkdir -p "$(dirname "$router")"
  cat >"$router" <<EOF
---
name: ${name}
description: "Apaleo-only workflow: ${name}. Resolve the Apaleo workspace and follow its canonical procedure."
---

# ${name} (Apaleo)

Read \`~/.claude/skills/references/resolve-pipeline-root.md\` and resolve the current workspace.
This entry point applies only inside the Apaleo workspace. If resolution fails, stop;
use the project's af-* skills when it uses the separate Agent Flow workflow.

Read \`\$ROOT/AGENTS.md\`, then fully follow \`\$ROOT/.claude/skills/${name}/SKILL.md\`.
The canonical Apaleo procedure owns all behaviour, arguments, and checks.
EOF
}

if [[ "$WORKFLOW_HOME" != "$WORKSPACE" ]]; then
  echo "Run install.sh from the workspace checkout: $WORKFLOW_HOME" >&2
  echo "Clone or check out this repository as the workspace parent, then run ./install.sh ." >&2
  exit 2
fi

while IFS= read -r skill_file; do
  name="$(basename "$(dirname "$skill_file")")"
  [[ "$name" == "add-convention" ]] && continue
  router="$WORKFLOW_HOME/host/routers/${name}.md"
  ensure_router "$name" "$router"
  replace_owned "$router" "$HOME/.claude/skills/${name}/SKILL.md" "Apaleo-only workflow"
done < <(find "$WORKFLOW_HOME/.claude/skills" -mindepth 2 -maxdepth 2 -name SKILL.md | sort)

replace_owned \
  "$WORKFLOW_HOME/host/resolve-pipeline-root.md" \
  "$HOME/.claude/skills/references/resolve-pipeline-root.md" \
  "Apaleo"
replace_owned \
  "$WORKFLOW_HOME/host/resolve-pipeline-root.sh" \
  "$HOME/.claude/skills/references/resolve-pipeline-root.sh" \
  "Apaleo"

mkdir -p "$HOME/.cursor/agents"
for agent in "$WORKFLOW_HOME"/.cursor/agents/*.md; do
  replace_owned "$agent" "$HOME/.cursor/agents/$(basename "$agent")" ".claude/skills"
done

MANIFEST="$WORKSPACE/.workflow-install.json"
python3 - "$MANIFEST" "$WORKFLOW_HOME" "$WORKSPACE" "${LINKED[@]}" <<'PY'
import json
import sys
from pathlib import Path

manifest, home, workspace, *links = sys.argv[1:]
Path(manifest).write_text(
    json.dumps(
        {
            "workflow_home": home,
            "workspace": workspace,
            "links": links,
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY

echo "Installed $WORKFLOW_HOME into $WORKSPACE"
