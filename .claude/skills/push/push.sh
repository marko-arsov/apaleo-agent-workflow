#!/usr/bin/env bash
# Push feature worktrees. A clean remote-branch merge is automatic; never --force.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../pipeline/root.sh"
ROOT="$(resolve_root)"
BRANCH="$(resolve_feature_branch "${1:-}")"
[[ "$BRANCH" != "master" && "$BRANCH" != "main" ]] || die_ask "refusing to push master"

echo "Push $BRANCH"
needs_remote_sync=0
found=0
for repo in "${FEATURE_REPOS[@]}"; do
  dest="$ROOT/worktrees/$BRANCH/$repo"
  if ! is_git_checkout "$dest"; then
    continue
  fi
  found=1
  cur="$(git -C "$dest" branch --show-current)"
  [[ "$cur" == "$BRANCH" ]] || die_ask "$dest is on $cur"
  [[ -z "$(git -C "$dest" status --porcelain)" ]] || die_ask "$repo worktree is dirty — will not push"
  git -C "$dest" fetch --prune origin
  if git -C "$dest" rev-parse --verify --quiet "refs/remotes/origin/$BRANCH" >/dev/null; then
    behind="$(git -C "$dest" rev-list --count "HEAD..origin/$BRANCH")"
    [[ "$behind" == "0" ]] || needs_remote_sync=1
  fi
done
(( found > 0 )) || die_ask "no feature worktree found for $BRANCH"

if [[ "$needs_remote_sync" == "1" ]]; then
  echo "Syncing origin/$BRANCH into feature worktree before push"
  "$SCRIPT_DIR/../sync-master/sync-master.sh" --remote-branch "$BRANCH"
fi

for repo in "${FEATURE_REPOS[@]}"; do
  dest="$ROOT/worktrees/$BRANCH/$repo"
  if ! is_git_checkout "$dest"; then
    echo "$repo  skipped (no worktree)"
    continue
  fi
  if git -C "$dest" rev-parse --verify --quiet "refs/remotes/origin/$BRANCH" >/dev/null; then
    local_ahead="$(git -C "$dest" rev-list --count "origin/$BRANCH..HEAD")"
    behind="$(git -C "$dest" rev-list --count "HEAD..origin/$BRANCH")"
    [[ "$behind" == "0" ]] || die_ask "$repo changed again on origin/$BRANCH (ahead=$local_ahead behind=$behind) — retry"
    if [[ "$local_ahead" == "0" ]]; then
      echo "$repo  nothing to push"
      continue
    fi
    echo "$repo  git push origin HEAD"
    git -C "$dest" push origin HEAD
  else
    echo "$repo  git push -u origin HEAD (new)"
    git -C "$dest" push -u origin HEAD
  fi
done
pr_found=0
for repo in "${FEATURE_REPOS[@]}"; do
  dest="$ROOT/worktrees/$BRANCH/$repo"
  is_git_checkout "$dest" || continue
  url="$(cd "$dest" && gh pr view --json url -q .url 2>/dev/null || true)"
  if [[ -n "$url" ]]; then
    echo "$repo PR: $url"
    pr_found=1
  fi
done
[[ "$pr_found" == "1" ]] || echo "PR: none"
