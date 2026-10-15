#!/usr/bin/env bash
# Generate the production EF SQL for one merged apaleo migration PR.
# Writes the gitignored parked-master file. Never applies SQL, commits, or pushes.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../pipeline/root.sh"
ROOT="$(resolve_root)"

FROM_OVERRIDE=""
QUERY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)
      [[ $# -ge 2 ]] || die_ask "usage: migration-script.sh [--from <MigrationId>] <issue|pr|branch>"
      FROM_OVERRIDE="$2"
      shift 2
      ;;
    *)
      [[ -z "$QUERY" ]] || die_ask "usage: migration-script.sh [--from <MigrationId>] <issue|pr|branch>"
      QUERY="$1"
      shift
      ;;
  esac
done
[[ -n "$QUERY" ]] || die_ask "pass an issue id, PR, or branch"

APALEO="$ROOT/apaleo"
is_git_checkout "$APALEO" || die_ask "missing parked apaleo checkout at $APALEO"
cur="$(git -C "$APALEO" branch --show-current)"
[[ "$cur" == "master" ]] || die_ask "parked apaleo is on $cur, not master — will not switch branches"
[[ -z "$(git -C "$APALEO" status --porcelain --untracked-files=no)" ]] || die_ask "parked apaleo has local changes — will not update master"

git -C "$APALEO" fetch --prune --quiet origin
if ! git -C "$APALEO" merge --ff-only --quiet origin/master; then
  die_ask "parked apaleo cannot fast-forward onto origin/master"
fi

pr_number=""
if [[ "$QUERY" == *github.com/*/pull/* && "$QUERY" != *github.com/apaleo/apaleo/pull/* ]]; then
  die_ask "migration-script only generates apaleo EF scripts"
fi
if [[ "$QUERY" == *github.com/apaleo/apaleo/pull/* ]]; then
  pr_number="$(printf '%s' "$QUERY" | sed -E 's#.*/pull/([0-9]+).*#\1#')"
else
  bare="${QUERY#\#}"
  if [[ "$bare" =~ ^[0-9]+$ ]]; then
    pr_number="$bare"
  fi
fi

if [[ -n "$pr_number" ]]; then
  if ! gh pr view "$pr_number" --repo apaleo/apaleo --json number -q .number >/dev/null 2>&1; then
    die_ask "no apaleo/apaleo PR #$pr_number"
  fi
else
  branch="$(resolve_feature_branch "$QUERY")"
  merged="$(gh pr list --repo apaleo/apaleo --head "$branch" --state merged --limit 5 --json number -q '.[].number')"
  if [[ -n "$merged" ]]; then
    count="$(printf '%s\n' "$merged" | wc -l | tr -d ' ')"
    [[ "$count" == "1" ]] || die_ask "branch $branch has several merged apaleo PRs: $(printf '%s' "$merged" | tr '\n' ' ')"
    pr_number="$merged"
  else
    open="$(gh pr list --repo apaleo/apaleo --head "$branch" --state open --limit 1 --json number -q '.[].number')"
    if [[ -n "$open" ]]; then
      die_ask "apaleo PR #$open is not merged — generate the script after it merges to master"
    fi
    token="$(printf '%s' "$QUERY" | grep -Eio '(sl|hc)-[0-9]+' | head -1 || true)"
    [[ -n "$token" ]] || die_ask "could not find a merged apaleo PR for '$QUERY'"
    merged="$(gh pr list --repo apaleo/apaleo --search "$token in:title" --state merged --limit 10 --json number -q '.[].number')"
    [[ -n "$merged" ]] || die_ask "no merged apaleo PR for $token"
    count="$(printf '%s\n' "$merged" | wc -l | tr -d ' ')"
    [[ "$count" == "1" ]] || die_ask "$token matches several merged apaleo PRs: $(printf '%s' "$merged" | tr '\n' ' '). Pass the PR number."
    pr_number="$merged"
  fi
fi

state="$(gh pr view "$pr_number" --repo apaleo/apaleo --json state -q .state)"
base="$(gh pr view "$pr_number" --repo apaleo/apaleo --json baseRefName -q .baseRefName)"
url="$(gh pr view "$pr_number" --repo apaleo/apaleo --json url -q .url)"
[[ "$state" == "MERGED" ]] || die_ask "apaleo PR #$pr_number is $state — generate the script after it merges to master"
[[ "$base" == "master" ]] || die_ask "apaleo PR #$pr_number targets $base, not master"

added=()
while IFS= read -r path; do
  [[ -n "$path" ]] || continue
  case "$path" in
    src/Apaleo.Data/Migrations/*.Designer.cs) continue ;;
    src/Apaleo.Data/Migrations/[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_*.cs) ;;
    *) continue ;;
  esac
  git -C "$APALEO" cat-file -e "HEAD:$path" || die_ask "$path from PR #$pr_number is not on master"
  added+=("$(basename "$path" .cs)")
done < <(gh pr view "$pr_number" --repo apaleo/apaleo --json files -q '.files[] | select(.changeType=="ADDED") | .path')

[[ ${#added[@]} -gt 0 ]] || die_ask "PR #$pr_number adds no EF migration under src/Apaleo.Data/Migrations"

all_ids=()
while IFS= read -r path; do
  [[ -n "$path" ]] || continue
  all_ids+=("$(basename "$path" .cs)")
done < <(git -C "$APALEO" ls-tree -r --name-only HEAD -- src/Apaleo.Data/Migrations | awk '/\/[0-9]{14}_.+\.cs$/ && !/\.Designer\.cs$/ { print }' | sort)

[[ ${#all_ids[@]} -gt 0 ]] || die_ask "no EF migrations on master"

in_pr() {
  local id="$1" item
  for item in "${added[@]}"; do
    [[ "$item" == "$id" ]] && return 0
  done
  return 1
}

first=""
last=""
previous=""
seen_target=0
for id in "${all_ids[@]}"; do
  if in_pr "$id"; then
    if [[ -z "$first" ]]; then
      first="$id"
      [[ -n "$previous" ]] || die_ask "$id is the first migration on master — pass --from only when a real predecessor exists"
    fi
    last="$id"
    seen_target=1
  elif [[ "$seen_target" == "0" ]]; then
    previous="$id"
  fi
done
[[ -n "$first" && -n "$last" && -n "$previous" ]] || die_ask "could not place the PR migrations in master's history"

from_id="$previous"
if [[ -n "$FROM_OVERRIDE" ]]; then
  known=0
  for id in "${all_ids[@]}"; do
    [[ "$id" == "$FROM_OVERRIDE" ]] && known=1
  done
  [[ "$known" == "1" ]] || die_ask "--from $FROM_OVERRIDE is not an EF migration on master"
  [[ "$FROM_OVERRIDE" < "$first" ]] || die_ask "--from $FROM_OVERRIDE is not before $first"
  from_id="$FROM_OVERRIDE"
fi

expected=()
collect=0
for id in "${all_ids[@]}"; do
  if [[ "$id" == "$from_id" ]]; then
    collect=1
    continue
  fi
  if [[ "$collect" == "1" ]]; then
    expected+=("$id")
    [[ "$id" == "$last" ]] && break
  fi
done
[[ ${#expected[@]} -gt 0 ]] || die_ask "no migrations to script from $from_id to $last"

if ! (
  cd "$APALEO"
  if command -v task >/dev/null 2>&1; then
    task ef:migration-script -- "$from_id" "$last"
  else
    if ! dotnet ef --version >/dev/null 2>&1; then
      dotnet tool restore
    fi
    dotnet ef migrations script \
      --project src/Apaleo.Data/ \
      --startup-project src/Apaleo.Data/ \
      -o ./migration.sql \
      -i \
      "$from_id" "$last"
  fi
) >&2; then
  die_ask "could not generate the EF script for $from_id..$last"
fi

out="$APALEO/migration.sql"
[[ -s "$out" ]] || die_ask "task ef:migration-script wrote no $out"

found=()
while IFS= read -r id; do
  [[ -n "$id" ]] || continue
  found+=("$id")
done < <(grep -oE '[0-9]{14}_[A-Za-z0-9]+' "$out" | sort -u)

if [[ ${#found[@]} -ne ${#expected[@]} ]]; then
  rm -f "$out"
  die_ask "generated script migration ids do not match $from_id..$last — removed $out"
fi
i=0
while [[ "$i" -lt ${#expected[@]} ]]; do
  if [[ "${found[$i]}" != "${expected[$i]}" ]]; then
    rm -f "$out"
    die_ask "generated script migration ids do not match $from_id..$last — removed $out"
  fi
  i=$((i + 1))
done

if ! head -n 1 "$out" | grep -q 'statement_timeout'; then
  tmp="$(mktemp)"
  printf '%s\n\n' 'SET statement_timeout = 0;' | cat - "$out" > "$tmp"
  mv "$tmp" "$out"
fi

echo "apaleo: generated $out"
echo "pr: $url"
echo "from: $from_id"
echo "to: $last"
echo "migrations: ${#expected[@]}"
if [[ -n "$FROM_OVERRIDE" && "$from_id" != "$previous" ]]; then
  echo "note: --from is behind the immediate predecessor $previous, so the file includes every migration after $from_id through $last"
fi
echo "assumption: production is already on $from_id. That id is the start boundary; its SQL is not in the file. Pass --from <MigrationId> when production is behind it."
echo "next: send the file to the person who will run it on production before the deploy. This skill did not apply it."
