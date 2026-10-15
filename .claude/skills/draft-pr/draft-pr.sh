#!/usr/bin/env bash
# Draft PRs with plan-derived titles, product-plan bodies, Linear + companion-PR links.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../pipeline/root.sh"
ROOT="$(resolve_root)"
HELPER="$SCRIPT_DIR/pr_text.py"
BRANCH="$(resolve_feature_branch "${1:-}")"
WT="$ROOT/worktrees/$BRANCH"
PLAN_ROOT="$ROOT/ai-plans/$BRANCH"
PLAN="$(python3 "$SCRIPT_DIR/../pipeline/pipeline_manifest.py" plan-dir --root "$ROOT" --task "$BRANCH")"
# master, or the unmerged branch a stacked plan was cut from.
BASE="$(python3 "$SCRIPT_DIR/../pipeline/pipeline_manifest.py" base-branch --root "$ROOT" --task "$BRANCH")"
mkdir -p "$PLAN_ROOT"
PROMPT="$PLAN/prompt.md"
[[ -f "$PROMPT" ]] || PROMPT="$PLAN_ROOT/prompt.md"
PRODUCT="$PLAN/product.md"
IMPLEMENTATION="$PLAN/implementation.md"
SQL="$PLAN/migration.sql"
[[ -f "$SQL" ]] || SQL="$PLAN_ROOT/migration.sql"
[[ -f "$SQL" ]] || SQL=""
ISSUE="$(python3 "$HELPER" issue --prompt "$PROMPT" --product "$PRODUCT")"
LINEAR="$(python3 "$HELPER" linear --prompt "$PROMPT" --product "$PRODUCT")"

deterministic_sections() {
  local title="$1" related="$2" e2e="$3"
  python3 "$HELPER" assemble --product "$PRODUCT" --implementation "$IMPLEMENTATION" --sql "$SQL" --title "$title" --related "$related" --e2e "$e2e"
}

pr_url() {
  local dest="$1"
  (cd "$dest" && gh pr view --json url -q .url 2>/dev/null || true)
}

validate_existing_pr() {
  local dest="$1" name="$2"
  local status
  status="$(cd "$dest" && gh pr view --json state,isDraft --jq '.state + ":" + (.isDraft | tostring)' 2>/dev/null || true)"
  [[ -n "$status" ]] || return 0
  [[ "$status" == "OPEN:true" ]] || die_ask "$name has an existing PR in unsafe state $status; draft-pr only updates open drafts"
}

ensure_repo() {
  local dest="$1" name="$2"
  is_git_checkout "$dest" || return 1
  git -C "$dest" fetch --prune origin
  git -C "$dest" rev-parse --verify --quiet "refs/remotes/origin/$BRANCH" >/dev/null || {
    echo "$name: origin/$BRANCH missing — run push first"
    return 1
  }
  git -C "$dest" rev-parse --verify --quiet "refs/remotes/origin/$BASE" >/dev/null ||
    die_ask "$name: base branch origin/$BASE is missing — if it was merged, drop base_branch from pipeline.json"
  if git -C "$dest" diff --quiet "origin/$BASE...HEAD"; then
    echo "$name: skipped (no diff from origin/$BASE)"
    return 1
  fi
  return 0
}

create_or_note() {
  local dest="$1" name="$2" title="$3" body="$4"
  local existing out
  existing="$(pr_url "$dest")"
  if [[ -n "$existing" ]]; then
    echo "$name: existing $existing"
    return 0
  fi
  out="$(cd "$dest" && gh pr create --draft --base "$BASE" --title "$title" --body "$body")"
  echo "$name: $out"
}

new_body() {
  local title="$1" related="$2" e2e="$3"
  deterministic_sections "$title" "$related" "$e2e"
}

edit_pr() {
  local dest="$1" title="$2" related="$3" e2e="$4"
  local url current_title body_file patched needs
  url="$(pr_url "$dest")"
  [[ -n "$url" ]] || return 0
  current_title="$(cd "$dest" && gh pr view --json title -q .title)"
  body_file="$(mktemp)"
  (cd "$dest" && gh pr view --json body -q .body) >"$body_file"
  patched="$(python3 "$HELPER" refresh --product "$PRODUCT" --implementation "$IMPLEMENTATION" --sql "$SQL" --title "$title" --related "$related" --e2e "$e2e" <"$body_file")"
  needs="$(python3 "$HELPER" title-needs-replace --current "$current_title" --issue "$ISSUE" --wanted "$title")"
  if [[ "$needs" == "yes" ]] || ! cmp -s "$body_file" <(printf '%s' "$patched"); then
    (cd "$dest" && gh pr edit --title "$title" --body "$patched") >/dev/null
  fi
  rm -f "$body_file"
}

write_record() {
  local dest="$1" name="$2"
  local url title body
  url="$(pr_url "$dest")"
  if [[ -z "$url" ]]; then
    printf '%s\n' "## $name" "skipped" "" >>"$PLAN_ROOT/pr.md"
    return
  fi
  title="$(cd "$dest" && gh pr view --json title -q .title)"
  body="$(cd "$dest" && gh pr view --json body -q .body)"
  {
    echo "## $name"
    echo "- Title: $title"
    echo "- URL: $url"
    echo
    echo "### Body"
    echo
    echo "$body"
    echo
  } >>"$PLAN_ROOT/pr.md"
}

APALEO_DEST="$WT/apaleo"
DEV_DEST="$WT/development"
ID_DEST="$WT/identity"
AS_DEST="$WT/agent-skills"
AAP_DEST="$WT/angular-api-proxy"
HAVE_APALEO=0
HAVE_DEV=0
HAVE_ID=0
HAVE_AS=0
HAVE_AAP=0
ensure_repo "$APALEO_DEST" apaleo && HAVE_APALEO=1 || true
ensure_repo "$DEV_DEST" development && HAVE_DEV=1 || true
ensure_repo "$ID_DEST" identity && HAVE_ID=1 || true
ensure_repo "$AS_DEST" agent-skills && HAVE_AS=1 || true
ensure_repo "$AAP_DEST" angular-api-proxy && HAVE_AAP=1 || true
[[ "$HAVE_APALEO$HAVE_DEV$HAVE_ID$HAVE_AS$HAVE_AAP" != "00000" ]] || die_ask "no worktree repo with origin/$BRANCH"
[[ "$HAVE_APALEO" -eq 1 ]] && validate_existing_pr "$APALEO_DEST" apaleo
[[ "$HAVE_DEV" -eq 1 ]] && validate_existing_pr "$DEV_DEST" development
[[ "$HAVE_ID" -eq 1 ]] && validate_existing_pr "$ID_DEST" identity
[[ "$HAVE_AS" -eq 1 ]] && validate_existing_pr "$AS_DEST" agent-skills
[[ "$HAVE_AAP" -eq 1 ]] && validate_existing_pr "$AAP_DEST" angular-api-proxy

APALEO_TITLE=""
DEV_TITLE=""
ID_TITLE=""
AS_TITLE=""
AAP_TITLE=""
APALEO_BODY=""
DEV_BODY=""
ID_BODY=""
AS_BODY=""
AAP_BODY=""
RELATED_BASE="$(python3 "$HELPER" related --issue "$ISSUE" --linear "$LINEAR")"

if [[ "$HAVE_APALEO" -eq 1 ]]; then
  APALEO_TITLE="$(python3 "$HELPER" title --issue "$ISSUE" --prompt "$PROMPT" --product "$PRODUCT" --implementation "$IMPLEMENTATION" --repo apaleo)"
  APALEO_E2E="[link to PR with E2E tests]"
  [[ "$HAVE_DEV" -eq 1 ]] || APALEO_E2E="N/A — no e2e changes"
  APALEO_BODY="$(new_body "$APALEO_TITLE" "$RELATED_BASE" "$APALEO_E2E")"
  create_or_note "$APALEO_DEST" apaleo "$APALEO_TITLE" "$APALEO_BODY"
fi
if [[ "$HAVE_DEV" -eq 1 ]]; then
  DEV_TITLE="$(python3 "$HELPER" title --issue "$ISSUE" --prompt "$PROMPT" --product "$PRODUCT" --implementation "$IMPLEMENTATION" --repo development)"
  DEV_BODY="$(new_body "$DEV_TITLE" "$RELATED_BASE" "this PR")"
  create_or_note "$DEV_DEST" development "$DEV_TITLE" "$DEV_BODY"
fi
if [[ "$HAVE_ID" -eq 1 ]]; then
  ID_TITLE="$(python3 "$HELPER" title --issue "$ISSUE" --prompt "$PROMPT" --product "$PRODUCT" --implementation "$IMPLEMENTATION" --repo identity)"
  ID_E2E="N/A — no e2e changes"
  ID_BODY="$(new_body "$ID_TITLE" "$RELATED_BASE" "$ID_E2E")"
  create_or_note "$ID_DEST" identity "$ID_TITLE" "$ID_BODY"
fi
if [[ "$HAVE_AS" -eq 1 ]]; then
  AS_TITLE="$(python3 "$HELPER" title --issue "$ISSUE" --prompt "$PROMPT" --product "$PRODUCT" --implementation "$IMPLEMENTATION" --repo agent-skills)"
  AS_BODY="$(new_body "$AS_TITLE" "$RELATED_BASE" "N/A — no e2e changes")"
  create_or_note "$AS_DEST" agent-skills "$AS_TITLE" "$AS_BODY"
fi
if [[ "$HAVE_AAP" -eq 1 ]]; then
  AAP_TITLE="$(python3 "$HELPER" title --issue "$ISSUE" --prompt "$PROMPT" --product "$PRODUCT" --implementation "$IMPLEMENTATION" --repo angular-api-proxy)"
  AAP_BODY="$(new_body "$AAP_TITLE" "$RELATED_BASE" "N/A — no e2e changes")"
  create_or_note "$AAP_DEST" angular-api-proxy "$AAP_TITLE" "$AAP_BODY"
fi

APALEO_URL=""
DEV_URL=""
ID_URL=""
AS_URL=""
AAP_URL=""
[[ "$HAVE_APALEO" -eq 1 ]] && APALEO_URL="$(pr_url "$APALEO_DEST")"
[[ "$HAVE_DEV" -eq 1 ]] && DEV_URL="$(pr_url "$DEV_DEST")"
[[ "$HAVE_ID" -eq 1 ]] && ID_URL="$(pr_url "$ID_DEST")"
[[ "$HAVE_AS" -eq 1 ]] && AS_URL="$(pr_url "$AS_DEST")"
[[ "$HAVE_AAP" -eq 1 ]] && AAP_URL="$(pr_url "$AAP_DEST")"
[[ "$HAVE_APALEO" -eq 0 || -n "$APALEO_URL" ]] || die_ask "apaleo draft PR could not be verified after creation"
[[ "$HAVE_DEV" -eq 0 || -n "$DEV_URL" ]] || die_ask "development draft PR could not be verified after creation"
[[ "$HAVE_ID" -eq 0 || -n "$ID_URL" ]] || die_ask "identity draft PR could not be verified after creation"
[[ "$HAVE_AS" -eq 0 || -n "$AS_URL" ]] || die_ask "agent-skills draft PR could not be verified after creation"
[[ "$HAVE_AAP" -eq 0 || -n "$AAP_URL" ]] || die_ask "angular-api-proxy draft PR could not be verified after creation"

APALEO_RELATED="$RELATED_BASE"
DEV_RELATED="$RELATED_BASE"
ID_RELATED="$RELATED_BASE"
AS_RELATED="$RELATED_BASE"
AAP_RELATED="$RELATED_BASE"
APALEO_E2E_FINAL="N/A — no e2e changes"
DEV_E2E_FINAL="this PR"
ID_E2E_FINAL="N/A — no e2e changes"
AS_E2E_FINAL="N/A — no e2e changes"
AAP_E2E_FINAL="N/A — no e2e changes"
if [[ -n "$DEV_URL" ]]; then
  APALEO_E2E_FINAL="$DEV_URL"
  ID_E2E_FINAL="$DEV_URL"
  AS_E2E_FINAL="$DEV_URL"
  AAP_E2E_FINAL="$DEV_URL"
fi
if [[ -n "$APALEO_URL" ]]; then
  DEV_RELATED="$(python3 "$HELPER" related --issue "$ISSUE" --linear "$LINEAR" --extra "apaleo PR: $APALEO_URL")"
  ID_RELATED="$(python3 "$HELPER" related --issue "$ISSUE" --linear "$LINEAR" --extra "apaleo PR: $APALEO_URL")"
  AS_RELATED="$(python3 "$HELPER" related --issue "$ISSUE" --linear "$LINEAR" --extra "apaleo PR: $APALEO_URL")"
  AAP_RELATED="$(python3 "$HELPER" related --issue "$ISSUE" --linear "$LINEAR" --extra "apaleo PR: $APALEO_URL")"
fi
APALEO_EXTRAS=()
[[ -n "$ID_URL" ]] && APALEO_EXTRAS+=("identity PR: $ID_URL")
[[ -n "$AS_URL" ]] && APALEO_EXTRAS+=("agent-skills PR: $AS_URL")
[[ -n "$AAP_URL" ]] && APALEO_EXTRAS+=("angular-api-proxy PR: $AAP_URL")
if [[ ${#APALEO_EXTRAS[@]} -gt 0 && -n "$APALEO_URL" ]]; then
  extra="$(IFS='; '; echo "${APALEO_EXTRAS[*]}")"
  APALEO_RELATED="$(python3 "$HELPER" related --issue "$ISSUE" --linear "$LINEAR" --extra "$extra")"
fi

[[ "$HAVE_APALEO" -eq 1 ]] && edit_pr "$APALEO_DEST" "$APALEO_TITLE" "$APALEO_RELATED" "$APALEO_E2E_FINAL"
[[ "$HAVE_DEV" -eq 1 ]] && edit_pr "$DEV_DEST" "$DEV_TITLE" "$DEV_RELATED" "$DEV_E2E_FINAL"
[[ "$HAVE_ID" -eq 1 ]] && edit_pr "$ID_DEST" "$ID_TITLE" "$ID_RELATED" "$ID_E2E_FINAL"
[[ "$HAVE_AS" -eq 1 ]] && edit_pr "$AS_DEST" "$AS_TITLE" "$AS_RELATED" "$AS_E2E_FINAL"
[[ "$HAVE_AAP" -eq 1 ]] && edit_pr "$AAP_DEST" "$AAP_TITLE" "$AAP_RELATED" "$AAP_E2E_FINAL"

{
  echo "# PR record — $BRANCH"
  echo
  echo "- Draft: true"
  [[ -n "$LINEAR" ]] && echo "- Linear: $LINEAR"
  echo
} >"$PLAN_ROOT/pr.md"
[[ "$HAVE_APALEO" -eq 1 ]] && write_record "$APALEO_DEST" apaleo
[[ "$HAVE_DEV" -eq 1 ]] && write_record "$DEV_DEST" development
[[ "$HAVE_ID" -eq 1 ]] && write_record "$ID_DEST" identity
[[ "$HAVE_AS" -eq 1 ]] && write_record "$AS_DEST" agent-skills
[[ "$HAVE_AAP" -eq 1 ]] && write_record "$AAP_DEST" angular-api-proxy

echo "Wrote $PLAN_ROOT/pr.md"
[[ -n "$APALEO_URL" ]] && echo "apaleo       Draft: $APALEO_URL"
[[ -n "$DEV_URL" ]] && echo "development  Draft: $DEV_URL"
[[ -n "$ID_URL" ]] && echo "identity     Draft: $ID_URL"
[[ -n "$AS_URL" ]] && echo "agent-skills Draft: $AS_URL"
[[ -n "$AAP_URL" ]] && echo "angular-api-proxy Draft: $AAP_URL"
[[ "$HAVE_APALEO" -eq 1 && -z "$APALEO_URL" ]] && echo "apaleo       skipped"
[[ "$HAVE_DEV" -eq 1 && -z "$DEV_URL" ]] && echo "development  skipped"
[[ "$HAVE_ID" -eq 1 && -z "$ID_URL" ]] && echo "identity     skipped"
[[ "$HAVE_AS" -eq 1 && -z "$AS_URL" ]] && echo "agent-skills skipped"
[[ "$HAVE_AAP" -eq 1 && -z "$AAP_URL" ]] && echo "angular-api-proxy skipped"
[[ -n "$APALEO_TITLE" ]] && echo "Title: $APALEO_TITLE"
[[ -n "$AS_TITLE" && -z "$APALEO_TITLE" ]] && echo "Title: $AS_TITLE"
[[ -n "$AAP_TITLE" && -z "$APALEO_TITLE" && -z "$AS_TITLE" ]] && echo "Title: $AAP_TITLE"
echo "PrFile: $PLAN_ROOT/pr.md"
