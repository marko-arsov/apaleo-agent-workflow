#!/usr/bin/env bash
# One-shot commit message + git commit in feature worktrees. No push.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../pipeline/root.sh"
ROOT="$(resolve_root)"
BRANCH="$(resolve_feature_branch "${1:-}")"
[[ "$BRANCH" != "master" && "$BRANCH" != "main" ]] || die_ask "refusing to commit on $BRANCH"
WT="$ROOT/worktrees/$BRANCH"
PLAN="$ROOT/ai-plans/$BRANCH"

# The E2E scope workaround is deliberately machine-local. Restore it before
# inspecting or staging anything so a direct /commit cannot capture it.
"$SCRIPT_DIR/../references/e2e-local-scope-workaround.sh" restore --root "$ROOT"

REPOS=()
CANDIDATES=()
DIRTY_REPOS=()
BAD_PATHS=""
while IFS= read -r repo; do
  [[ -n "$repo" ]] && CANDIDATES+=("$repo")
done < <(attached_repos "$BRANCH")
for repo in "${CANDIDATES[@]:-}"; do
  dest="$WT/$repo"
  is_git_checkout "$dest" || continue
  current="$(git -C "$dest" branch --show-current)"
  [[ "$current" == "$BRANCH" ]] || die_ask "$dest is on ${current:-detached HEAD}"
  REPOS+=("$repo")
  if [[ -n "$(git -C "$dest" status --porcelain)" ]]; then
    DIRTY_REPOS+=("$repo")
    bad="$(git -C "$dest" status --porcelain | awk '{print $2}' | grep -E '(^|/)\.env($|\.)|(^|/)id_rsa|(^|/)credentials(\.json)?$' || true)"
    [[ -n "$bad" ]] && BAD_PATHS+="$repo: $bad"$'\n'
  fi
done
(( ${#REPOS[@]} > 0 )) || die_ask "no feature worktree found for $BRANCH"
if [[ -n "$BAD_PATHS" ]]; then
  die_ask "secret-looking paths in status: ${BAD_PATHS%$'\n'}"
fi
if (( ${#DIRTY_REPOS[@]} == 0 )); then
  printf '%s\n' "Result: Nothing to commit (${REPOS[*]})"
  exit 0
fi

# A development checkout that only still has core E2E master already removed
# must be dropped before the scan. The scan otherwise reads that whole branch.
if ! leftover="$(python3 "$ROOT/.claude/skills/pipeline/verification.py" \
  "$BRANCH" --root "$ROOT" --leftover-development)"; then
  die_ask "$leftover"
fi

# Fast deterministic safety gate only. Project tests remain owned by
# implement/review; this checks the diff for conventions and secrets.
python3 "$ROOT/.claude/skills/pipeline/verification.py" \
  "$BRANCH" --root "$ROOT" --precommit >/dev/null

FILES=""
TICKET=""
TITLE=""
if [[ "$BRANCH" =~ [Hh][Cc]-?([0-9]+) ]]; then TICKET="HC-${BASH_REMATCH[1]}"; fi
if [[ -f "$PLAN/prompt.md" ]]; then
  TITLE="$(sed -n 's/^# //p' "$PLAN/prompt.md" | head -1)"
fi
for repo in "${DIRTY_REPOS[@]}"; do
  dest="$WT/$repo"
  while IFS= read -r changed; do
    [[ -n "$changed" ]] && FILES+="$repo/$changed"$'\n'
  done < <(git -C "$dest" diff --name-only HEAD; git -C "$dest" ls-files --others --exclude-standard)
done
SUMMARY="$TITLE"
[[ -n "$TICKET" ]] && SUMMARY="${SUMMARY#"$TICKET"}"
SUMMARY="$(printf '%s' "$SUMMARY" | sed -E 's/^[[:space:]—–-]+//; s/[[:space:]]+/ /g')"
if [[ -z "$SUMMARY" ]]; then
  SUMMARY="$(printf '%s' "${BRANCH##*/}" | sed -E 's/^[Hh][Cc]-?[0-9]+-?//; s/[-_]+/ /g')"
fi
SUMMARY="$(printf '%s' "$SUMMARY" | awk '{if (length($0)) $0=toupper(substr($0,1,1)) substr($0,2); print}')"
MSG="${TICKET:+$TICKET }${SUMMARY:-Update implementation}"
if [[ -n "$FILES" ]] && ! printf '%s' "$FILES" | grep -Ev '^apaleo/src/Apaleo.Data/Migrations/' >/dev/null; then
  MSG="[DB-MIGRATION] $MSG"
fi
MSG="$(printf '%s' "$MSG" | cut -c1-120)"
echo "Message:"
echo "$MSG"
for repo in "${DIRTY_REPOS[@]}"; do
  dest="$WT/$repo"
  git -C "$dest" add -A
  git -C "$dest" commit -m "$MSG"
  echo "$repo  committed $(git -C "$dest" rev-parse --short HEAD)"
done
