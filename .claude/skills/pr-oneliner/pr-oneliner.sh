#!/usr/bin/env bash
# Print the product one-liner and pull request URLs for a feature. No greeting.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../pipeline/root.sh
source "$SCRIPT_DIR/../pipeline/root.sh"
ROOT="$(resolve_root)"
BRANCH="$(resolve_feature_branch "${1:-}")"
PLAN="$(python3 "$SCRIPT_DIR/../pipeline/pipeline_manifest.py" plan-dir --root "$ROOT" --task "$BRANCH" 2>/dev/null || true)"
PRODUCT="${PLAN:+$PLAN/product.md}"
if [[ ! -f "${PRODUCT:-}" ]]; then
  PRODUCT="$ROOT/ai-plans/$BRANCH/product.md"
fi
[[ -f "$PRODUCT" ]] || PRODUCT=""

WT="$ROOT/worktrees/$BRANCH"
rows=()
collect() {
  local dest="$1" row
  is_git_checkout "$dest" || return 0
  row="$(cd "$dest" && gh pr view --json title,url -q '[.title, .url] | @tsv' 2>/dev/null || true)"
  [[ -n "$row" ]] && rows+=("$row")
}
for repo in "${FEATURE_REPOS[@]}"; do
  collect "$WT/$repo"
done
while IFS= read -r extra; do
  [[ -n "$extra" ]] || continue
  collect "$WT/$extra"
done < <(python3 "$SCRIPT_DIR/../pipeline/common.py" extra-repos --root "$ROOT" --branch "$BRANCH")

RECORD="$ROOT/ai-plans/$BRANCH/pr.md"
if [[ ${#rows[@]} -gt 0 ]]; then
  MESSAGE="$(printf '%s\n' "${rows[@]}" | python3 "$SCRIPT_DIR/pr_oneliner.py" message --product "$PRODUCT")"
elif [[ -f "$RECORD" ]]; then
  MESSAGE="$(python3 "$SCRIPT_DIR/pr_oneliner.py" message --product "$PRODUCT" --record "$RECORD")"
else
  die_ask "no pull request found for $BRANCH"
fi

[[ -n "$MESSAGE" && "$MESSAGE" == *"github.com/"* ]] || die_ask "no pull request found for $BRANCH"
printf '%s\n' "$MESSAGE"
