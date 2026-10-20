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
PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Build a find(1) name predicate from FEATURE_REPOS so the worktree scan can never
# drift from the repo inventory: ( -name a -o -name b -o ... ). Recorded extra
# repositories are added in resolve_feature_branch.
find_repo_predicate=()
refresh_find_predicate() {
  local repo
  find_repo_predicate=()
  for repo in "${FEATURE_REPOS[@]}"; do
    [[ ${#find_repo_predicate[@]} -eq 0 ]] || find_repo_predicate+=(-o)
    find_repo_predicate+=(-name "$repo")
  done
  [[ -n "${ROOT:-}" ]] || return 0
  while IFS= read -r repo; do
    [[ -n "$repo" ]] || continue
    find_repo_predicate+=(-o -name "$repo")
  done < <(python3 "$PIPELINE_DIR/common.py" discover-extras --root "$ROOT" 2>/dev/null || true)
}
refresh_find_predicate

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
  if [[ -f "$wt/.extra-repos" ]]; then
    while IFS= read -r repo; do
      [[ -n "$repo" ]] || continue
      is_git_checkout "$wt/$repo" && return 0
    done < "$wt/.extra-repos"
  fi
  return 1
}

attached_repos() {
  local branch="$1"
  python3 "$PIPELINE_DIR/common.py" attached-repos --root "$ROOT" --branch "$branch"
}

# Resolve a full feature branch from a full name, issue shorthand, or the current
# worktree. Call after ROOT="$(resolve_root)". Short ids must be unique.
worktree_branch_from_cwd() {
  local cwd d outer parent rel child
  cwd="$(pwd -P 2>/dev/null || pwd)"
  case "$cwd" in "$ROOT"/worktrees/*) ;; *) return 0 ;; esac
  # The outermost checkout under worktrees is the feature repository. A nested
  # submodule stays inside it, so the branch is that checkout's parent.
  outer=""
  d="$cwd"
  while [[ "$d" == "$ROOT"/worktrees/* ]]; do
    if is_git_checkout "$d"; then
      outer="$d"
    fi
    d="$(dirname "$d")"
  done
  if [[ -n "$outer" ]]; then
    parent="$(dirname "$outer")"
    printf '%s' "${parent#"$ROOT/worktrees/"}"
    return 0
  fi
  rel="${cwd#"$ROOT/worktrees/"}"
  for child in "$cwd"/*; do
    if is_git_checkout "$child"; then
      printf '%s' "$rel"
      return 0
    fi
  done
}

normalize_feature_query() {
  local query token digits prefix
  query="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  # A bare issue id, with or without a dash: sl129, sl-129, c3331, hc3331.
  if [[ "$query" =~ ^([a-z]{1,8})[[:space:]_-]*([0-9]+)$ ]]; then
    prefix="${BASH_REMATCH[1]}"
    digits="${BASH_REMATCH[2]}"
    if [[ "$prefix" == "c" || "$prefix" == "hc" ]]; then
      printf 'hc-%s' "$digits"
      return 0
    fi
    if [[ ${#prefix} -ge 2 ]]; then
      printf '%s-%s' "$prefix" "$digits"
      return 0
    fi
  fi
  token="$(printf '%s' "$query" | grep -Eio 'h?c[[:space:]_-]*[0-9]+' | head -1 || true)"
  if [[ -n "$token" ]]; then
    digits="$(printf '%s' "$token" | tr -cd '0-9')"
    printf 'hc-%s' "$digits"
    return 0
  fi
  printf '%s' "$query"
}

# Issue ids match on a digit boundary, so sl-129 does not select sl-1290.
branch_matches_needle() {
  local branch_l="$1" needle="$2"
  if [[ "$needle" =~ ^[a-z]+-[0-9]+$ ]]; then
    [[ "$branch_l" =~ (^|[^0-9])${needle}([^0-9]|$) ]]
    return
  fi
  case "$branch_l" in
    *"$needle"*) return 0 ;;
  esac
  return 1
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
consider_pr_repo() {
  local number="$1" repo="$2" branch existing found
  branch="$(gh pr view "$number" --repo "$repo" --json headRefName -q .headRefName 2>/dev/null || true)"
  [[ -n "$branch" ]] || return 0
  found=0
  for existing in "${matches[@]:-}"; do [[ "$existing" == "$branch" ]] && found=1; done
  [[ "$found" == "0" ]] && matches+=("$branch")
}

feature_pr_branch() {
  local query="$1" number repo name
  local -a matches=()
  if [[ "$query" == *github.com/*/pull/* ]]; then
    local branch
    branch="$(gh pr view "$query" --json headRefName -q .headRefName 2>/dev/null || true)"
    [[ -n "$branch" ]] && { printf '%s' "$branch"; return 0; }
    return 2
  fi
  number="${query#\#}"
  [[ "$number" =~ ^[0-9]+$ ]] || return 1
  for repo in "${GITHUB_REPOS[@]}"; do
    consider_pr_repo "$number" "$repo"
  done
  # Attached extras only. A pull request in some other org repository is not searched.
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    consider_pr_repo "$number" "apaleo/$name"
  done < <(python3 "$PIPELINE_DIR/common.py" discover-extras --root "$ROOT" 2>/dev/null || true)
  [[ ${#matches[@]} -eq 1 ]] && { printf '%s' "${matches[0]}"; return 0; }
  [[ ${#matches[@]} -gt 1 ]] && return 2
  return 2
}

feature_remote_issue_matches() {
  local issue="$1" repo branch name
  for repo in "${GITHUB_REPOS[@]}"; do
    while IFS= read -r branch; do
      feature_match_add "$branch"
    done < <(gh pr list --repo "$repo" --search "$issue in:title" --state all --limit 10 \
      --json headRefName -q '.[].headRefName' 2>/dev/null || true)
  done
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    while IFS= read -r branch; do
      feature_match_add "$branch"
    done < <(gh pr list --repo "apaleo/$name" --search "$issue in:title" --state all --limit 10 \
      --json headRefName -q '.[].headRefName' 2>/dev/null || true)
  done < <(python3 "$PIPELINE_DIR/common.py" discover-extras --root "$ROOT" 2>/dev/null || true)
}

resolve_feature_branch() {
  local query="${1:-}" cwd_branch needle branch branch_l repo_dir wt plan plan_file pr_branch pr_rc=0
  local -a matches=()

  refresh_find_predicate
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
    if branch_matches_needle "$branch_l" "$needle"; then
      printf '%s' "$cwd_branch"
      return 0
    fi
  fi

  while IFS= read -r -d '' repo_dir; do
    # Repository names can also occur as ordinary source directories inside a
    # worktree (for example development/apaleo). Only direct Git checkouts mark
    # the parent as a feature-worktree root.
    is_git_checkout "$repo_dir" || continue
    wt="$(dirname "$repo_dir")"
    branch="${wt#"$ROOT/worktrees/"}"
    branch_l="$(printf '%s' "$branch" | tr '[:upper:]' '[:lower:]')"
    if branch_matches_needle "$branch_l" "$needle"; then
      feature_match_add "$branch"
    fi
  done < <(find "$ROOT/worktrees" -maxdepth 4 -type d \( "${find_repo_predicate[@]}" \) -print0 2>/dev/null)

  if [[ ${#matches[@]} -eq 0 && -d "$ROOT/ai-plans" ]]; then
    while IFS= read -r -d '' plan_file; do
      plan="$(dirname "$plan_file")"
      branch="${plan#"$ROOT/ai-plans/"}"
      branch_l="$(printf '%s' "$branch" | tr '[:upper:]' '[:lower:]')"
      if branch_matches_needle "$branch_l" "$needle"; then
        feature_match_add "$branch"
      fi
  done < <(find "$ROOT/ai-plans" -type f \( -name prompt.md -o -name product.md -o -name implementation.md -o -name progress.md -o -name pr.md \) -print0 2>/dev/null)
  fi

  [[ ${#matches[@]} -eq 0 && "$needle" =~ ^[a-z]+-[0-9]+$ ]] && feature_remote_issue_matches "$needle"

  if [[ ${#matches[@]} -eq 1 ]]; then
    printf '%s' "${matches[0]}"
    return 0
  fi
  if [[ ${#matches[@]} -gt 1 ]]; then
    die_ask "'$query' matches several feature branches: ${matches[*]}. Pass the full branch name."
  fi
  printf '%s' "$query"
}
