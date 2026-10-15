#!/usr/bin/env bash
# Fetch/compare @apaleo marketplace. Default --check-only. Mutating needs --apply AND prior ask.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../pipeline/root.sh"
ROOT="$(resolve_root)"
CHECK_ONLY=1
APPLY=0
[[ "${1:-}" == "--apply" ]] && { APPLY=1; CHECK_ONLY=0; }
[[ "${1:-}" == "--check-only" ]] && CHECK_ONLY=1

AS="$ROOT/agent-skills"
if [[ ! -d "$AS/.git" ]]; then
  die_ask "clone https://github.com/apaleo/agent-skills.git into $AS first"
fi
git -C "$AS" fetch --prune origin
LOCAL="$(git -C "$AS" rev-parse --short HEAD)"
REMOTE="$(git -C "$AS" rev-parse --short origin/master)"
BEHIND="$(git -C "$AS" rev-list --count HEAD..origin/master)"
echo "agent-skills clone: $LOCAL  origin/master: $REMOTE  behind: $BEHIND"
echo "Commits behind:"
git -C "$AS" log --oneline HEAD..origin/master | head -20 || true
echo "Installed @apaleo plugin cache dirs:"
ls -1 "$HOME/.claude/plugins/cache/apaleo" 2>/dev/null || echo "  (none)"
echo "Personal pipeline (.claude/skills): unchanged by this script"
if [[ "$CHECK_ONLY" == "1" ]]; then
  echo "ASK: marketplace update available; ask whether to rerun with --apply to fast-forward the local clone"
  exit 2
fi
if [[ "$APPLY" == "1" ]]; then
  git -C "$AS" pull --ff-only origin master
  echo "Pulled HEAD=$(git -C "$AS" rev-parse --short HEAD)"
  echo "ASK: ask which named @apaleo plugin(s) to install or upgrade; do not install any plugin silently"
  exit 2
fi
