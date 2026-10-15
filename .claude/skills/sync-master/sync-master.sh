#!/usr/bin/env bash
# Merge origin/master (or the feature's remote branch) into feature worktrees.
# Exit 0 clean, 10 = conflicts (agent handoff), 2 = ask.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../pipeline/root.sh"
ROOT="$(resolve_root)"
REMOTE_BRANCH=0
if [[ "${1:-}" == "--remote-branch" ]]; then
  REMOTE_BRANCH=1
  shift
fi
[[ $# -le 1 ]] || die_ask "usage: sync-master.sh [--remote-branch] <branch>"
BRANCH="$(resolve_feature_branch "${1:-}")"
WT="$ROOT/worktrees/$BRANCH"
[[ -d "$WT" ]] || die_ask "missing $WT — run worktree-start.sh first"
feature_worktree_exists "$WT" || die_ask "no feature worktree in $WT — run worktree-start.sh first"

conflicted=0
merge_one() {
  local dest="$1" name="$2"
  is_git_checkout "$dest" || { echo "$name: n/a"; return 0; }
  local cur
  cur="$(git -C "$dest" branch --show-current)"
  [[ "$cur" == "$BRANCH" ]] || die_ask "$dest is on $cur not $BRANCH"
  if [[ -n "$(git -C "$dest" status --porcelain)" ]]; then
    die_ask "$name worktree is dirty — will not merge"
  fi
  git -C "$dest" fetch --prune origin
  local merge_ref="origin/master"
  if [[ "$REMOTE_BRANCH" == "1" ]]; then
    if ! git -C "$dest" rev-parse --verify --quiet "refs/remotes/origin/$BRANCH" >/dev/null; then
      echo "$name: origin/$BRANCH missing (new branch)"
      return 0
    fi
    merge_ref="origin/$BRANCH"
  fi
  local before after
  before="$(git -C "$dest" rev-parse HEAD)"
  if git -C "$dest" merge --no-edit "$merge_ref"; then
    after="$(git -C "$dest" rev-parse HEAD)"
    if [[ "$before" == "$after" ]]; then
      echo "$name: up to date $(git -C "$dest" rev-parse --short HEAD)"
    else
      echo "$name: merged $(git -C "$dest" rev-parse --short HEAD)"
    fi
  else
    echo "$name: CONFLICTS $merge_ref $(git -C "$dest" diff --name-only --diff-filter=U | tr '\n' ' ')"
    conflicted=1
  fi
}

for repo in "${FEATURE_REPOS[@]}"; do
  merge_one "$WT/$repo" "$repo"
done
[[ "$REMOTE_BRANCH" == "1" ]] || echo "Mains still $(git -C "$ROOT/apaleo" branch --show-current)"
if [[ "$conflicted" == "1" ]]; then
  echo "HANDOFF_CONFLICTS=1"
  exit 10
fi
exit 0
