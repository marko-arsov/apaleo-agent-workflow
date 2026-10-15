#!/usr/bin/env bash
# Resolve identifier → branch, ensure worktree, ff-only pull. Exit 2 = ask.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../pipeline/root.sh"
ROOT="$(resolve_root)"
TARGET="${1:-}"
[[ -n "$TARGET" ]] || die_ask "pass branch, PR url/#N, or HC-####"

BRANCH="$(resolve_feature_branch "$TARGET")"
echo "Resolved: $BRANCH"
"$ROOT/.claude/skills/worktree-start/worktree-start.sh" "$BRANCH"

for repo in "${FEATURE_REPOS[@]}"; do
  dest="$ROOT/worktrees/$BRANCH/$repo"
  is_git_checkout "$dest" || continue
  if [[ -n "$(git -C "$dest" status --porcelain)" ]]; then
    die_ask "$dest is dirty — will not pull"
  fi
  git -C "$dest" fetch --prune
  # A branch created locally by specify/worktree-start has no origin ref yet. That is
  # normal, not divergence — do not report it as a failed fast-forward.
  if ! git -C "$dest" show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
    echo "$repo  $(git -C "$dest" rev-parse --short HEAD)  local-only (no origin/$BRANCH yet)"
    continue
  fi
  if git -C "$dest" pull --ff-only origin "$BRANCH"; then
    echo "$repo  $(git -C "$dest" rev-parse --short HEAD)  ff-only ok"
  else
    die_ask "$repo diverged from origin/$BRANCH — not fast-forward"
  fi
done
echo "WT=$ROOT/worktrees/$BRANCH"
mains_report() {
  local m="" r
  for r in "${FEATURE_REPOS[@]}"; do
    is_git_checkout "$ROOT/$r" || continue
    m+="${m:+ }$r=$(git -C "$ROOT/$r" branch --show-current)"
  done
  printf 'Mains: %s' "$m"
}
mains_report; echo
