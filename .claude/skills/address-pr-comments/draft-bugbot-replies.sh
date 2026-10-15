#!/usr/bin/env bash
# One-shot paste-ready Bugbot replies from unfixable ledger rows. Never posts.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../pipeline/root.sh"
ROOT="$(resolve_root)"
IDENT="${1:-}"
[[ -n "$IDENT" ]] || die_ask "pass branch"
BRANCH="$(resolve_feature_branch "$IDENT")"
PLAN="$ROOT/ai-plans/$BRANCH"
[[ -f "$PLAN/bugbot.md" ]] || die_ask "missing $PLAN/bugbot.md — run address-pr-comments --bugbot first"
ENTRIES="$(mktemp)"
# extract Unfixable / U# sections only
awk 'BEGIN{p=0} /^## Unfixable/{p=1} /^## / && !/^## Unfixable/{if($0 !~ /Unfixable/) p=0} p{print}' "$PLAN/bugbot.md" >"$ENTRIES"
if [[ ! -s "$ENTRIES" ]]; then
  echo "No unfixable entries."
  rm -f "$ENTRIES"
  exit 0
fi
OUT="$(python3 "$ROOT/.claude/skills/pipeline/oneshot.py" --template bugbot-replies --entries-file "$ENTRIES")"
rm -f "$ENTRIES"
echo "$OUT" | tee "$PLAN/bugbot-replies.md"
echo "Paste-only. Never posted. Wrote $PLAN/bugbot-replies.md"
