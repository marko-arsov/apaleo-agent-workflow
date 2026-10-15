#!/usr/bin/env bash
# Open JetBrains Rider on an Apaleo feature worktree.
# Resolves branch from name / PR / issue id, creates the worktree if missing,
# quits Rider if running, then opens the Apaleo repo's Apaleo.sln by default.
#
# Usage:
#   open-rider.sh <branch|PR-url|#N|issue-id>
#   open-rider.sh --list
#   open-rider.sh HC-3328 --no-quit
#   open-rider.sh 12945 --force
#
# Env:
#   APALEO_ROOT   override workspace root (default: derived from this script)
#   RIDER_APP     override app path (default: /Applications/Rider.app)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../pipeline/root.sh"
ROOT="${APALEO_ROOT:-$(resolve_root)}"
RIDER_APP="${RIDER_APP:-/Applications/Rider.app}"
REPO_APALEO="apaleo/apaleo"
REPO_DEV="apaleo/development"

NO_QUIT=0
FORCE=0
DRY_RUN=0
LIST_ONLY=0
WITH_DEV=0
APALEO_ONLY=0
QUERY=""

usage() {
  cat <<EOF
Usage: $(basename "$0") <branch|PR|#N|issue-id> [options]
       $(basename "$0") --list

Ensure \$ROOT/worktrees/<branch>/apaleo exists, quit Rider, open Apaleo.sln.

Options:
  --list            List local feature worktrees and exit
  --no-quit         Do not quit an already-running Rider
  --force           If Rider ignores quit (e.g. save dialog), killall Rider
  --with-development  Also ensure \$WT/development when origin/<branch> exists
  --apaleo-only     Never create a development worktree
  --dry-run         Print actions only
  -h, --help        This help

Examples:
  $(basename "$0") SL-100
  $(basename "$0") <github-login>/<issue-id>-<slug>
  $(basename "$0") 12945
  $(basename "$0") https://github.com/apaleo/apaleo/pull/12945
  $(basename "$0") HC-3328
EOF
}

die() { echo "error: $*" >&2; exit 1; }
info() { echo "$*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --list) LIST_ONLY=1; shift ;;
    --no-quit) NO_QUIT=1; shift ;;
    --force) FORCE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --with-development) WITH_DEV=1; shift ;;
    --apaleo-only) APALEO_ONLY=1; shift ;;
    --) shift; break ;;
    -*) die "unknown option: $1" ;;
    *)
      if [[ -n "$QUERY" ]]; then die "unexpected extra arg: $1"; fi
      QUERY="$1"
      shift
      ;;
  esac
done

[[ -f "$ROOT/AGENTS.md" ]] || die "APALEO_ROOT invalid (no AGENTS.md): $ROOT"
[[ -d "$ROOT/apaleo/.git" || -f "$ROOT/apaleo/.git" ]] || die "missing \$ROOT/apaleo: $ROOT/apaleo"
[[ -d "$RIDER_APP" ]] || die "Rider not found at $RIDER_APP (set RIDER_APP=…)"

# True apaleo feature worktrees only (skip mistaken …/development/apaleo nests)
iter_apaleo_worktrees() {
  [[ -d "$ROOT/worktrees" ]] || return 0
  find "$ROOT/worktrees" -type d -name apaleo -print0 2>/dev/null | sort -z | while IFS= read -r -d '' apaleo_dir; do
    case "$apaleo_dir" in
      */development/*) continue ;;
    esac
    printf '%s\0' "$apaleo_dir"
  done
}

list_worktrees() {
  local found=0
  if [[ ! -d "$ROOT/worktrees" ]]; then
    echo "(no worktrees under $ROOT/worktrees)"
    return
  fi
  while IFS= read -r -d '' apaleo_dir; do
    local branch
    branch="$(git -C "$apaleo_dir" branch --show-current 2>/dev/null || true)"
    [[ -n "$branch" ]] || continue
    local sha dirty="clean"
    sha="$(git -C "$apaleo_dir" rev-parse --short HEAD 2>/dev/null || echo "?")"
    if [[ -n "$(git -C "$apaleo_dir" status --porcelain 2>/dev/null)" ]]; then
      dirty="dirty"
    fi
    local rel="${apaleo_dir#"$ROOT/worktrees/"}"
    local wt_branch="${rel%/apaleo}"
    printf '%s\t%s\t%s\t%s\n' "$wt_branch" "$branch" "$sha" "$dirty"
    found=1
  done < <(iter_apaleo_worktrees)
  [[ "$found" -eq 1 ]] || echo "(no apaleo worktrees found)"
}

if [[ "$LIST_ONLY" -eq 1 ]]; then
  list_worktrees
  exit 0
fi

[[ -n "$QUERY" ]] || { usage; echo; echo "Local worktrees:"; list_worktrees; exit 1; }

normalize_hc() {
  local s
  s="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  s="${s/hc-/hc-}"
  if [[ "$s" =~ ^hc([0-9]+)$ ]]; then
    s="hc-${BASH_REMATCH[1]}"
  fi
  printf '%s' "$s"
}

gh_pr_head() {
  local n="$1" repo="$2"
  gh pr view "$n" --repo "$repo" --json headRefName -q .headRefName 2>/dev/null
}

resolve_branch() {
  local q="$1"
  local n head matches m shared

  shared="$(resolve_feature_branch "$q")"
  if [[ "$shared" != "$q" || -d "$ROOT/worktrees/$shared/apaleo" ]]; then
    printf '%s' "$shared"
    return
  fi

  # PR URL
  if [[ "$q" =~ github\.com/[^/]+/[^/]+/pull/([0-9]+) ]]; then
    n="${BASH_REMATCH[1]}"
    head="$(gh_pr_head "$n" "$REPO_APALEO" || true)"
    [[ -n "$head" ]] || head="$(gh_pr_head "$n" "$REPO_DEV" || true)"
    [[ -n "$head" ]] || die "PR #$n not found in $REPO_APALEO or $REPO_DEV"
    printf '%s' "$head"
    return
  fi

  # #123 or bare digits (PR number) — 3+ digits to avoid tiny false positives
  if [[ "$q" =~ ^#([0-9]{3,})$ ]] || [[ "$q" =~ ^([0-9]{3,})$ ]]; then
    n="${BASH_REMATCH[1]}"
    head="$(gh_pr_head "$n" "$REPO_APALEO" || true)"
    [[ -n "$head" ]] || head="$(gh_pr_head "$n" "$REPO_DEV" || true)"
    [[ -n "$head" ]] || die "PR #$n not found"
    printf '%s' "$head"
    return
  fi

  # Exact worktree folder
  if [[ -d "$ROOT/worktrees/$q/apaleo" ]]; then
    printf '%s' "$q"
    return
  fi

  # HC-#### → unique match under worktrees/ or ai-plans/
  if [[ "$q" =~ ^[Hh][Cc]-?[0-9]+$ ]]; then
    local hc ap rel br
    hc="$(normalize_hc "$q")"
    matches=()
    while IFS= read -r -d '' ap; do
      rel="${ap#"$ROOT/worktrees/"}"
      br="${rel%/apaleo}"
      if [[ "$br" == *"$hc"* ]]; then
        matches+=("$br")
      fi
    done < <(iter_apaleo_worktrees)
    if [[ ${#matches[@]} -eq 0 && -d "$ROOT/ai-plans" ]]; then
      while IFS= read -r -d '' d; do
        br="${d#"$ROOT/ai-plans/"}"
        if [[ "$br" == *"$hc"* ]]; then
          matches+=("$br")
        fi
      done < <(find "$ROOT/ai-plans" -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null)
    fi
    if [[ ${#matches[@]} -eq 0 ]]; then
      head="$(gh pr list --repo "$REPO_APALEO" --search "$hc in:title" --state all --limit 5 \
        --json headRefName,number,title -q '.[0].headRefName' 2>/dev/null || true)"
      [[ -n "$head" ]] || die "no worktree/plan/PR match for $hc"
      printf '%s' "$head"
      return
    fi
    if [[ ${#matches[@]} -gt 1 ]]; then
      echo "ambiguous $hc — pick one (full branch name or PR #):" >&2
      printf '  %s\n' "${matches[@]}" >&2
      exit 1
    fi
    printf '%s' "${matches[0]}"
    return
  fi

  # Treat as branch name (may need worktree create from origin)
  printf '%s' "$q"
}

main_on_master() {
  local repo="$1"
  local b
  b="$(git -C "$repo" branch --show-current)"
  [[ "$b" == "master" ]] || die "$repo is on '$b' (need master). Park it before attaching a worktree."
}

ensure_worktree() {
  local branch="$1"
  local kind="$2" # apaleo | development
  local main="$ROOT/$kind"
  local dest="$ROOT/worktrees/$branch/$kind"

  if [[ -e "$dest" ]]; then
    local cur
    cur="$(git -C "$dest" branch --show-current 2>/dev/null || true)"
    [[ "$cur" == "$branch" ]] || die "$dest is on '$cur', expected '$branch'"
    info "reuse $kind worktree: $dest"
    return
  fi

  main_on_master "$main"
  info "fetch $kind…"
  git -C "$main" fetch --prune

  mkdir -p "$(dirname "$dest")"

  if git -C "$main" show-ref --verify --quiet "refs/heads/$branch"; then
    info "create $kind worktree from local $branch → $dest"
    [[ "$DRY_RUN" -eq 1 ]] && return
    git -C "$main" worktree add "$dest" "$branch"
  elif git -C "$main" show-ref --verify --quiet "refs/remotes/origin/$branch"; then
    info "create $kind worktree from origin/$branch → $dest"
    [[ "$DRY_RUN" -eq 1 ]] && return
    git -C "$main" worktree add --track -b "$branch" "$dest" "origin/$branch"
  else
    if [[ "$kind" == "development" ]]; then
      info "development: no local/origin branch '$branch' — skip"
      return 1
    fi
    die "branch '$branch' not found in $kind (local or origin). Create it via /specify first."
  fi
}

rider_running() {
  pgrep -iq "[Rr]ider" 2>/dev/null
}

quit_rider() {
  if ! rider_running; then
    info "Rider not running"
    return
  fi
  if [[ "$NO_QUIT" -eq 1 ]]; then
    info "leaving Rider running (--no-quit)"
    return
  fi
  info "quitting Rider…"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    return
  fi
  osascript -e 'tell application "Rider" to quit' 2>/dev/null || true
  local i
  for i in $(seq 1 40); do
    rider_running || return 0
    sleep 0.25
  done
  if [[ "$FORCE" -eq 1 ]]; then
    info "Rider still open — --force killall"
    killall Rider 2>/dev/null || killall rider 2>/dev/null || true
    sleep 1
    rider_running && die "could not quit Rider"
    return
  fi
  die "Rider still running (unsaved changes?). Save/close the dialog, or re-run with --force"
}

open_rider() {
  local sln="$1"
  [[ -f "$sln" ]] || die "solution not found: $sln"
  info "open Rider → $sln"
  [[ "$DRY_RUN" -eq 1 ]] && return
  # -n: new instance/process after quit; pass .sln so Rider loads the solution
  open -na "$RIDER_APP" --args "$sln"
}

BRANCH="$(resolve_branch "$QUERY")"
info "resolved: $BRANCH"
WT="$ROOT/worktrees/$BRANCH"
APALEO_WT="$WT/apaleo"
SLN="$APALEO_WT/Apaleo.sln"

ensure_worktree "$BRANCH" "apaleo"

if [[ "$APALEO_ONLY" -eq 0 ]]; then
  if [[ "$WITH_DEV" -eq 1 ]] || git -C "$ROOT/development" show-ref --verify --quiet "refs/remotes/origin/$BRANCH" 2>/dev/null \
      || git -C "$ROOT/development" show-ref --verify --quiet "refs/heads/$BRANCH" 2>/dev/null; then
    ensure_worktree "$BRANCH" "development" || true
  fi
fi

# Confirm mains still parked
main_on_master "$ROOT/apaleo"
if [[ -d "$ROOT/development/.git" || -f "$ROOT/development/.git" ]]; then
  main_on_master "$ROOT/development"
fi

quit_rider
open_rider "$SLN"

info "done"
info "  worktree: $WT"
info "  branch:   $BRANCH"
info "  solution: $SLN"
