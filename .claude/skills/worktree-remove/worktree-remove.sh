#!/usr/bin/env bash
# Remove $ROOT/worktrees/<branch> after confirmation (or --yes). Never --force unless --force.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../pipeline/root.sh"
ROOT="$(resolve_root)"
YES=0
FORCE=0
MERGED=0
CLOSED=0
DELETE_PLANS=0
BRANCH=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) YES=1; shift ;;
    --force) FORCE=1; shift ;;
    --merged) MERGED=1; shift ;;
    --closed) CLOSED=1; shift ;;
    --delete-plans) DELETE_PLANS=1; shift ;;
    -h|--help) echo "Usage: worktree-remove.sh <branch|--merged|--closed> [--yes] [--force] [--delete-plans]"; exit 0 ;;
    *) BRANCH="$1"; shift ;;
  esac
done

remove_one() {
  local br="$1"
  local wt="$ROOT/worktrees/$br"
  [[ -d "$wt" ]] || { echo "skip $br (no worktree dir)"; return 0; }
  echo "Candidate $br  $wt"
  for repo in "${FEATURE_REPOS[@]}"; do
    local dest="$wt/$repo"
    is_git_checkout "$dest" || continue
    local dirty=""
    [[ -z "$(git -C "$dest" status --porcelain)" ]] || dirty=" DIRTY"
    echo "  $repo $(git -C "$dest" rev-parse --short HEAD)$dirty"
    if [[ -n "$dirty" && "$FORCE" != "1" ]]; then
      die_ask "$dest is dirty — commit/stash yourself or pass --force"
    fi
  done
  if [[ "$YES" != "1" ]]; then
    die_ask "re-run with --yes to remove $wt"
  fi
  for repo in "${FEATURE_REPOS[@]}"; do
    local dest="$wt/$repo"
    is_git_checkout "$dest" || continue
    local args=(worktree remove "$dest")
    [[ "$FORCE" == "1" ]] && args=(worktree remove --force "$dest")
    if git -C "$ROOT/$repo" "${args[@]}"; then
      echo "  $repo/  ok"
    else
      echo "  $repo/  failed"
    fi
  done
  rmdir "$wt" 2>/dev/null || rm -rf "$wt"
  if [[ "$DELETE_PLANS" == "1" && -d "$ROOT/ai-plans/$br" ]]; then
    rm -rf "$ROOT/ai-plans/$br"
    echo "Plans: deleted ai-plans/$br"
  else
    echo "Plans: kept ai-plans/$br"
  fi
}

if [[ -n "$BRANCH" ]]; then
  BRANCH="$(resolve_feature_branch "$BRANCH")"
  remove_one "$BRANCH"
  mains_report() {
    local m="" r
    for r in "${FEATURE_REPOS[@]}"; do
      is_git_checkout "$ROOT/$r" || continue
      m+="${m:+ }$r=$(git -C "$ROOT/$r" branch --show-current)"
    done
    printf 'Mains: %s' "$m"
  }
  mains_report; echo
  exit 0
fi
die_ask "pass a branch (auto --merged/--closed candidate listing is interactive — name the branch)"
