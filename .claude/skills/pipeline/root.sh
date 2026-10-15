#!/usr/bin/env bash
# Resolve Apaleo $ROOT. Source this from mechanical skill scripts.
# Never treats a worktrees/ folder as ROOT.

# Product repos that may appear under $ROOT/<name> (parked master) and
# $ROOT/worktrees/<branch>/<name> (feature work). apaleo is the default
# worktree; the others attach only when needed. A branch may be
# agent-skills-only or angular-api-proxy-only.
# Keep in sync with FEATURE_REPOS in pipeline/common.py (test_feature_repos_inventory).
FEATURE_REPOS=(apaleo development identity agent-skills angular-api-proxy)
GITHUB_REPOS=(apaleo/apaleo apaleo/development apaleo/identity apaleo/agent-skills apaleo/angular-api-proxy)

# Build a find(1) name predicate from FEATURE_REPOS so the worktree scan can never
# drift from the repo inventory: ( -name a -o -name b -o ... ).
find_repo_predicate=()
for _repo in "${FEATURE_REPOS[@]}"; do
  [[ ${#find_repo_predicate[@]} -eq 0 ]] || find_repo_predicate+=(-o)
  find_repo_predicate+=(-name "$_repo")
done
unset _repo

resolve_root() {
  local d cwd
  cwd="$(pwd -P 2>/dev/null || pwd)"
  if [[ "$cwd" == */worktrees/* ]]; then
    d="${cwd%%/worktrees/*}"
    if [[ -f "$d/AGENTS.md" && -d "$d/apaleo" ]]; then
      printf '%s' "$d"
      return 0
    fi
  fi
  d="$cwd"
  while [[ "$d" != "/" ]]; do
    if [[ -f "$d/AGENTS.md" && -d "$d/apaleo" && -d "$d/development" && "$d" != */worktrees/* ]]; then
      printf '%s' "$d"
      return 0
    fi
    d="$(dirname "$d")"
  done
  echo "ERROR: could not resolve \$ROOT" >&2
  return 2
}

die_ask() {
  echo "ASK: $*" >&2
  exit 2
}

is_git_checkout() {
  local dest="$1"
  [[ -d "$dest/.git" || -f "$dest/.git" ]]
}

feature_worktree_exists() {
  local wt="$1" repo
  for repo in "${FEATURE_REPOS[@]}"; do
    is_git_checkout "$wt/$repo" && return 0
  done
  return 1
}

# Resolve a full feature branch from a full name, issue shorthand, or the current
# worktree. Call after ROOT="$(resolve_root)". Short ids must be unique.
worktree_branch_from_cwd() {
  local cwd rel repo
  cwd="$(pwd -P 2>/dev/null || pwd)"
  case "$cwd" in "$ROOT"/worktrees/*) ;; *) return 0 ;; esac
  rel="${cwd#"$ROOT/worktrees/"}"
  for repo in "${FEATURE_REPOS[@]}"; do
    case "$rel" in
      */"$repo"|*/"$repo"/*)
        printf '%s' "${rel%/"$repo"*}"
        return 0
        ;;
    esac
  done
  for repo in "${FEATURE_REPOS[@]}"; do
    if is_git_checkout "$cwd/$repo"; then
      printf '%s' "$rel"
      return 0
    fi
  done
}

normalize_feature_query() {
  local query token digits
  query="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  token="$(printf '%s' "$query" | grep -Eio 'h?c[[:space:]_-]*[0-9]+' | head -1 || true)"
  if [[ -n "$token" ]]; then
    digits="$(printf '%s' "$token" | tr -cd '0-9')"
    query="hc-$digits"
  fi
  printf '%s' "$query"
}

feature_match_add() {
  local candidate="$1" existing
  [[ -n "$candidate" ]] || return 0
  for existing in "${matches[@]:-}"; do
    [[ "$existing" == "$candidate" ]] && return 0
  done
  matches+=("$candidate")
}

# Print the branch for a PR URL, #number, or bare number. Return 1 when the
# query is not a PR reference and 2 when it is one but cannot be resolved.
feature_pr_branch() {
  local query="$1" number repo branch
  local -a matches=()
  if [[ "$query" == *github.com/*/pull/* ]]; then
    branch="$(gh pr view "$query" --json headRefName -q .headRefName 2>/dev/null || true)"
    [[ -n "$branch" ]] && { printf '%s' "$branch"; return 0; }
    return 2
  fi
  number="${query#\#}"
  [[ "$number" =~ ^[0-9]+$ ]] || return 1
  for repo in "${GITHUB_REPOS[@]}"; do
    branch="$(gh pr view "$number" --repo "$repo" --json headRefName -q .headRefName 2>/dev/null || true)"
    [[ -n "$branch" ]] || continue
    local existing found=0
    for existing in "${matches[@]:-}"; do [[ "$existing" == "$branch" ]] && found=1; done
    [[ "$found" == "0" ]] && matches+=("$branch")
  done
  [[ ${#matches[@]} -eq 1 ]] && { printf '%s' "${matches[0]}"; return 0; }
  [[ ${#matches[@]} -gt 1 ]] && return 2
  return 2
}

feature_remote_issue_matches() {
  local issue="$1" repo branch
  for repo in "${GITHUB_REPOS[@]}"; do
    while IFS= read -r branch; do
      feature_match_add "$branch"
    done < <(gh pr list --repo "$repo" --search "$issue in:title" --state all --limit 10 \
      --json headRefName -q '.[].headRefName' 2>/dev/null || true)
  done
}

resolve_feature_branch() {
  local query="${1:-}" cwd_branch needle branch branch_l repo_dir wt plan plan_file pr_branch pr_rc=0
  local -a matches=()

  cwd_branch="$(worktree_branch_from_cwd)"
  if [[ -z "$query" ]]; then
    [[ -n "$cwd_branch" ]] || die_ask "pass branch name"
    printf '%s' "$cwd_branch"
    return 0
  fi

  pr_branch="$(feature_pr_branch "$query")" || pr_rc=$?
  if [[ "$pr_rc" == "0" ]]; then
    printf '%s' "$pr_branch"
    return 0
  fi
  [[ "$pr_rc" == "2" ]] && die_ask "could not resolve PR reference '$query' to one branch"

  feature_worktree_exists "$ROOT/worktrees/$query" && { printf '%s' "$query"; return 0; }
  needle="$(normalize_feature_query "$query")"
  if [[ -n "$cwd_branch" ]]; then
    branch_l="$(printf '%s' "$cwd_branch" | tr '[:upper:]' '[:lower:]')"
    case "$branch_l" in *"$needle"*) printf '%s' "$cwd_branch"; return 0 ;; esac
  fi

  while IFS= read -r -d '' repo_dir; do
    # Repository names can also occur as ordinary source directories inside a
    # worktree (for example development/apaleo). Only direct Git checkouts mark
    # the parent as a feature-worktree root.
    is_git_checkout "$repo_dir" || continue
    wt="$(dirname "$repo_dir")"
    branch="${wt#"$ROOT/worktrees/"}"
    branch_l="$(printf '%s' "$branch" | tr '[:upper:]' '[:lower:]')"
    case "$branch_l" in
      *"$needle"*)
        feature_match_add "$branch"
        ;;
    esac
  done < <(find "$ROOT/worktrees" -maxdepth 4 -type d \( "${find_repo_predicate[@]}" \) -print0 2>/dev/null)

  if [[ ${#matches[@]} -eq 0 && -d "$ROOT/ai-plans" ]]; then
    while IFS= read -r -d '' plan_file; do
      plan="$(dirname "$plan_file")"
      branch="${plan#"$ROOT/ai-plans/"}"
      branch_l="$(printf '%s' "$branch" | tr '[:upper:]' '[:lower:]')"
      case "$branch_l" in
        *"$needle"*)
          feature_match_add "$branch"
          ;;
      esac
  done < <(find "$ROOT/ai-plans" -type f \( -name prompt.md -o -name product.md -o -name implementation.md -o -name progress.md -o -name pr.md \) -print0 2>/dev/null)
  fi

  [[ ${#matches[@]} -eq 0 && "$needle" =~ ^hc-[0-9]+$ ]] && feature_remote_issue_matches "$needle"

  if [[ ${#matches[@]} -eq 1 ]]; then
    printf '%s' "${matches[0]}"
    return 0
  fi
  if [[ ${#matches[@]} -gt 1 ]]; then
    die_ask "'$query' matches several feature branches: ${matches[*]}. Pass the full branch name."
  fi
  printf '%s' "$query"
}
