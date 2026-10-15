#!/usr/bin/env bash
# Fast-forward the workflow checkout from origin/master and register commands.
# Product repositories are separate checkouts and are left untouched.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../pipeline/root.sh"

usage() {
  cat <<'EOF'
Usage: update-workflow.sh

Fast-forward a clean workflow master from origin/master, then register host
commands with install.sh. Stops when the checkout has uncommitted changes or
is not on master. Does not merge, rebase, or force-update.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
[[ $# -eq 0 ]] || die_ask "update-workflow takes no arguments"

ROOT="$(resolve_root)"
cd "$ROOT"
git rev-parse --is-inside-work-tree >/dev/null
toplevel="$(git rev-parse --show-toplevel)"
[[ "$toplevel" == "$ROOT" ]] || die_ask "workflow git root is $toplevel, expected $ROOT"
remote="$(git remote get-url origin)"
case "$remote" in
  *apaleo-agent-workflow*) ;;
  *) die_ask "origin is not the workflow repository: $remote" ;;
esac

branch="$(git branch --show-current)"
[[ "$branch" == "master" ]] || die_ask "checkout is on ${branch:-detached HEAD}. Update only a clean master."
[[ -z "$(git status --porcelain)" ]] || die_ask "checkout has uncommitted changes"

before="$(git rev-parse HEAD)"
if ! git pull --ff-only origin master; then
  die_ask "master cannot fast-forward to origin/master"
fi
"$ROOT/install.sh" "$ROOT"
after="$(git rev-parse HEAD)"
if [[ "$before" == "$after" ]]; then
  printf '%s\n' "Result: Already up to date"
else
  printf '%s\n' "Result: Updated"
fi
printf '%s\n' "Commit: $(git rev-parse --short HEAD)"
