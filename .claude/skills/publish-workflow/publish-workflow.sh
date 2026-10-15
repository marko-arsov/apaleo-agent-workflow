#!/usr/bin/env bash
# Publish uncommitted workflow edits on a new branch and open a pull request.
# The workspace parent is the only repository this script touches.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../pipeline/root.sh"

usage() {
  cat <<'EOF'
Usage: publish-workflow.sh [--dry-run] ["short summary"]

Commit uncommitted workflow files on a new branch from origin/master, push
that branch, and open a pull request. When the summary is omitted, it is
derived from the changed files. Product repositories, worktrees, plans, and
run state are refused. Nothing is committed on master, and nothing is force-pushed.
EOF
}

subject_for() {
  local path="$1" rest base
  case "$path" in
    .claude/skills/pipeline/tests/test_*.py)
      base="${path##*/}"
      base="${base#test_}"
      base="${base%.py}"
      printf '%s' "${base//_/-}"
      ;;
    .claude/skills/*/*)
      rest="${path#.claude/skills/}"
      printf '%s' "${rest%%/*}"
      ;;
    .claude/skills/*)
      rest="${path#.claude/skills/}"
      printf '%s' "$rest"
      ;;
    .cursor/agents/*-cursor.md)
      base="${path##*/}"
      printf '%s' "${base%-cursor.md}"
      ;;
    host/routers/*.md)
      base="${path##*/}"
      printf '%s' "${base%.md}"
      ;;
    *)
      printf '%s' "${path##*/}"
      ;;
  esac
}

summary_from_paths() {
  local subjects=() path subject known item n i last out
  for path in "$@"; do
    subject="$(subject_for "$path")"
    [[ -n "$subject" ]] || continue
    known=0
    if (( ${#subjects[@]} > 0 )); then
      for item in "${subjects[@]}"; do
        if [[ "$item" == "$subject" ]]; then
          known=1
          break
        fi
      done
    fi
    if [[ "$known" == 0 ]]; then
      subjects+=("$subject")
    fi
  done
  (( ${#subjects[@]} > 0 )) || die_ask "could not derive a summary"
  if (( ${#subjects[@]} > 4 )); then
    subjects=("${subjects[@]:0:3}" "other workflow files")
  fi
  n=${#subjects[@]}
  last="${subjects[$((n - 1))]}"
  if [[ "$n" -eq 1 ]]; then
    printf 'Update %s' "$last"
    return 0
  fi
  if [[ "$n" -eq 2 ]]; then
    printf 'Update %s and %s' "${subjects[0]}" "$last"
    return 0
  fi
  out="Update ${subjects[0]}"
  i=1
  while [[ "$i" -lt $((n - 1)) ]]; do
    out="$out, ${subjects[$i]}"
    i=$((i + 1))
  done
  printf '%s, and %s' "$out" "$last"
}

join_items() {
  local -a items=("$@")
  local n=${#items[@]} i out
  [[ "$n" -gt 0 ]] || return 0
  if [[ "$n" -eq 1 ]]; then
    printf '%s' "${items[0]}"
    return 0
  fi
  if [[ "$n" -eq 2 ]]; then
    printf '%s and %s' "${items[0]}" "${items[1]}"
    return 0
  fi
  out="${items[0]}"
  i=1
  while [[ "$i" -lt $((n - 1)) ]]; do
    out="$out, ${items[$i]}"
    i=$((i + 1))
  done
  printf '%s, and %s' "$out" "${items[$((n - 1))]}"
}

skill_of() {
  local path="$1" rest base
  case "$path" in
    .claude/skills/pipeline/*|.claude/skills/references/*) return 1 ;;
    .claude/skills/*/*)
      rest="${path#.claude/skills/}"
      printf '%s' "${rest%%/*}"
      ;;
    .cursor/agents/*-cursor.md)
      base="${path##*/}"
      printf '%s' "${base%-cursor.md}"
      ;;
    host/routers/*.md)
      base="${path##*/}"
      printf '%s' "${base%.md}"
      ;;
    *) return 1 ;;
  esac
}

remember_name() {
  local kind="$1" name="$2" item
  local -a existing=()
  if [[ "$kind" == added ]]; then
    existing=("${added_names[@]:-}")
  else
    existing=("${updated_names[@]:-}")
    for item in "${added_names[@]:-}"; do
      [[ "$item" == "$name" ]] && return 0
    done
  fi
  for item in "${existing[@]:-}"; do
    [[ "$item" == "$name" ]] && return 0
  done
  if [[ "$kind" == added ]]; then
    added_names+=("$name")
  else
    updated_names+=("$name")
  fi
}

remember_test() {
  local kind="$1" name="$2" item
  local -a existing=()
  if [[ "$kind" == added ]]; then
    existing=("${added_tests[@]:-}")
  else
    existing=("${updated_tests[@]:-}")
    for item in "${added_tests[@]:-}"; do
      [[ "$item" == "$name" ]] && return 0
    done
  fi
  for item in "${existing[@]:-}"; do
    [[ "$item" == "$name" ]] && return 0
  done
  if [[ "$kind" == added ]]; then
    added_tests+=("$name")
  else
    updated_tests+=("$name")
  fi
}

# Read git name-status lines on stdin. Print a few short bullets.
pr_bullets() {
  local status path extra skill base
  local pipeline=0 docs=0 other=0
  added_names=()
  updated_names=()
  added_tests=()
  updated_tests=()
  while IFS=$'\t' read -r status path extra; do
    [[ -n "$status" ]] || continue
    case "$status" in
      R*|C*) path="$extra" ;;
    esac
    case "$path" in
      .claude/skills/pipeline/tests/test_*.py)
        base="${path##*/}"
        base="${base#test_}"
        base="${base%.py}"
        base="${base//_/-}"
        if [[ "$status" == A ]]; then
          remember_test added "$base"
        else
          remember_test updated "$base"
        fi
        ;;
      .claude/skills/pipeline/*)
        pipeline=1
        ;;
      WORKFLOW.md|AGENTS.md|CLAUDE.md|README.md|.claude/skills/WORKFLOW.md|.claude/skills/references/*)
        docs=1
        ;;
      *)
        if skill="$(skill_of "$path")"; then
          if [[ "$status" == A && ( "$path" == ".claude/skills/$skill/SKILL.md" || "$path" == ".claude/skills/$skill/$skill.sh" ) ]]; then
            remember_name added "$skill"
          else
            remember_name updated "$skill"
          fi
        else
          other=1
        fi
        ;;
    esac
  done
  if [[ ${#added_names[@]} -gt 0 ]]; then
    printf '%s\n' "- Add $(quoted_commands "${added_names[@]}")."
  fi
  if [[ ${#updated_names[@]} -gt 0 ]]; then
    printf '%s\n' "- Update $(quoted_commands "${updated_names[@]}")."
  fi
  if [[ "$pipeline" -eq 1 ]]; then
    printf '%s\n' "- Update the pipeline runner."
  fi
  if [[ ${#added_tests[@]} -gt 0 ]]; then
    printf '%s\n' "- Add tests for $(join_items "${added_tests[@]}")."
  fi
  if [[ ${#updated_tests[@]} -gt 0 ]]; then
    printf '%s\n' "- Update tests for $(join_items "${updated_tests[@]}")."
  fi
  if [[ "$docs" -eq 1 ]]; then
    printf '%s\n' "- Update the workflow docs."
  fi
  if [[ "$other" -eq 1 ]]; then
    printf '%s\n' "- Update other workflow files."
  fi
}

quoted_commands() {
  local -a items=()
  local name
  for name in "$@"; do
    items+=('`/'"$name"'`')
  done
  join_items "${items[@]}"
}

# Title is $1. Name-status lines are on stdin.
pr_body() {
  local title="$1" bullets
  bullets="$(pr_bullets)"
  [[ -n "$bullets" ]] || bullets="- Update workflow files."
  cat <<EOF
## Summary
$title

$bullets
EOF
}

DRY=0
SUMMARY=""
for arg in "$@"; do
  case "$arg" in
    -h|--help)
      usage
      exit 0
      ;;
    --dry-run)
      DRY=1
      ;;
    --)
      ;;
    -*)
      die_ask "unknown option: $arg"
      ;;
    *)
      [[ -z "$SUMMARY" ]] || die_ask "pass one quoted summary"
      SUMMARY="$arg"
      ;;
  esac
done

[[ -z "$SUMMARY" || "$SUMMARY" != *$'\n'* ]] || die_ask "summary must be one line"

ROOT="$(resolve_root)"
cd "$ROOT"
git rev-parse --is-inside-work-tree >/dev/null
toplevel="$(git rev-parse --show-toplevel)"
[[ "$toplevel" == "$ROOT" ]] || die_ask "workflow git root is $toplevel, expected $ROOT"
remote="$(git remote get-url origin)"
case "$remote" in
  *apaleo-agent-workflow*) ;;
  *) die_ask "origin is not the workflow repository: $remote" ;;
esac

git fetch origin master
head="$(git rev-parse HEAD)"
origin_master="$(git rev-parse origin/master)"
[[ "$head" == "$origin_master" ]] || die_ask "HEAD is not origin/master. This publishes uncommitted edits onto a new branch from origin/master."

changes=()
while IFS= read -r line; do
  [[ -n "$line" ]] && changes+=("$line")
done < <(git status --porcelain -uall)
(( ${#changes[@]} > 0 )) || {
  printf '%s\n' "Result: Nothing to publish"
  exit 0
}

paths=()
for line in "${changes[@]}"; do
  path="${line:3}"
  [[ "$path" == *" -> "* ]] && path="${path##* -> }"
  paths+=("$path")
done

forbidden_path() {
  local path="$1"
  case "$path" in
    apaleo|apaleo/*|development|development/*|identity|identity/*|agent-skills|agent-skills/*|angular-api-proxy|angular-api-proxy/*|worktrees|worktrees/*|ai-plans|ai-plans/*|.local|.local/*|company-workflow-docs|company-workflow-docs/*)
      return 0
      ;;
  esac
  [[ "$path" =~ (^|/)\.env($|\.)|(^|/)id_rsa($|\.)|(^|/)credentials(\.json)?$|(^|/).*[.]pem$|settings[.]local[.]json ]]
}

for path in "${paths[@]}"; do
  if forbidden_path "$path"; then
    die_ask "refusing to publish $path"
  fi
done

if [[ -z "$SUMMARY" ]]; then
  SUMMARY="$(summary_from_paths "${paths[@]}")"
fi
slug="$(printf '%s' "$SUMMARY" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//' | cut -c1-48)"
slug="$(printf '%s' "$slug" | sed -E 's/-+$//')"
[[ -n "$slug" ]] || die_ask "summary did not produce a branch name"
branch="workflow/$slug"
title="$(printf '%s' "$SUMMARY" | cut -c1-120)"

if git show-ref --verify --quiet "refs/heads/$branch"; then
  die_ask "branch $branch already exists"
fi
if git ls-remote --heads origin "$branch" | grep -q .; then
  die_ask "branch $branch already exists on origin"
fi

if [[ "$DRY" == 1 ]]; then
  printf '%s\n' "Result: Dry run"
  printf '%s\n' "Branch: $branch"
  printf '%s\n' "Summary: $title"
  printf '%s\n' "${changes[@]}"
  exit 0
fi

git checkout -b "$branch"
git add -A
staged=()
while IFS= read -r path; do
  [[ -n "$path" ]] && staged+=("$path")
done < <(git diff --cached --name-only)
(( ${#staged[@]} > 0 )) || die_ask "nothing staged after git add"
for path in "${staged[@]}"; do
  if forbidden_path "$path"; then
    git reset -q
    die_ask "refusing to publish $path"
  fi
done

git commit -m "$title"
git push -u origin HEAD
body="$(git diff-tree --no-commit-id --name-status -r HEAD | pr_body "$title")"
url="$(gh pr create --base master --head "$branch" --title "$title" --body "$body")"
printf '%s\n' "Result: Pull request opened"
printf '%s\n' "Branch: $branch"
printf '%s\n' "Summary: $title"
printf '%s\n' "URL: $url"
