#!/usr/bin/env bash
# Inventory $ROOT/worktrees. Optional --pr uses gh. Exit 0 always unless ROOT missing.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../pipeline/root.sh"
ROOT="$(resolve_root)"
WITH_PR=0
[[ "${1:-}" == "--pr" ]] && WITH_PR=1

echo "Mains"
for main in "${FEATURE_REPOS[@]}"; do
  if ! is_git_checkout "$ROOT/$main"; then
    echo "  $main  MISSING"
    continue
  fi
  cur="$(git -C "$ROOT/$main" branch --show-current)"
  sha="$(git -C "$ROOT/$main" rev-parse --short HEAD)"
  flag=""
  [[ "$cur" == "master" ]] || flag=" NOT on master"
  echo "  $main  $cur @ $sha$flag"
done

echo "Worktrees"
shopt -s nullglob
found=0
wts=()
for repo in "${FEATURE_REPOS[@]}"; do
  for dest in "$ROOT/worktrees"/*/"$repo" "$ROOT/worktrees"/*/*/"$repo"; do
    [[ -d "$dest/.git" || -f "$dest/.git" ]] || continue
    wt="$(cd "$(dirname "$dest")" && pwd -P)"
    already=0
    for existing in "${wts[@]:-}"; do
      [[ "$existing" == "$wt" ]] && already=1 && break
    done
    [[ "$already" == "1" ]] && continue
    wts+=("$wt")
  done
done
for wt in "${wts[@]:-}"; do
  found=1
  branch=""
  for repo in "${FEATURE_REPOS[@]}"; do
    dest="$wt/$repo"
    [[ -d "$dest/.git" || -f "$dest/.git" ]] || continue
    branch="$(git -C "$dest" branch --show-current 2>/dev/null || echo '?')"
    break
  done
  echo "  ${branch:-?}"
  echo "    path $wt"
  for repo in "${FEATURE_REPOS[@]}"; do
    dest="$wt/$repo"
    if [[ ! -d "$dest/.git" && ! -f "$dest/.git" ]]; then
      echo "    $repo  missing"
      continue
    fi
    sha="$(git -C "$dest" rev-parse --short HEAD)"
    dirty="clean"
    [[ -z "$(git -C "$dest" status --porcelain)" ]] || dirty="dirty"
    pr="n/a"
    if [[ "$WITH_PR" == "1" ]]; then
      pr="$(gh pr view --repo "apaleo/$repo" --head "$branch" --json url,state -q '.state + " " + .url' 2>/dev/null || echo none)"
    fi
    echo "    $repo  $sha  $dirty  PR:$pr"
  done
  plans="$ROOT/ai-plans/$branch"
  if [[ -d "$plans" ]]; then echo "    plans  yes $plans"; else echo "    plans  no"; fi
done
[[ "$found" == "1" ]] || echo "  (none)"
echo "Cleanup: worktree-remove.sh <branch> for merged/closed PRs"
