#!/usr/bin/env bash
# Create or reuse $ROOT/worktrees/<branch>/{apaleo?,development?,identity?,agent-skills?,angular-api-proxy?}
# Mains stay on master. Prints a short parseable report. Exit 2 = ask.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../pipeline/root.sh
source "$SCRIPT_DIR/../pipeline/root.sh"
ROOT="$(resolve_root)"
FROM_MASTER=0
WITH_DEV=0
WITH_ID=0
WITH_SKILLS=0
WITH_AAP=0
APALEO_ONLY=0
SKILLS_ONLY=0
AAP_ONLY=0
BRANCH=""
EXTRA_WITH=()

usage() {
  cat <<EOF
Usage: worktree-start.sh <branch> [--from-master]
         [--with-development] [--with-identity] [--with-agent-skills] [--with-angular-api-proxy]
         [--with <repository>]
         [--apaleo-only] [--agent-skills-only] [--angular-api-proxy-only]

Optional repos attach only when asked for, or when origin/<branch> already exists in the
parked clone. Use an *-only flag for a branch that does not touch apaleo.
--with <repository> attaches another apaleo org repository for this branch. Repeat it
for each one. An existing \$ROOT/<repository> checkout of that repo is the source;
otherwise the first attach creates a bare mirror at \$ROOT/.repos/<repository>.git.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --from-master) FROM_MASTER=1; shift ;;
    --with-development) WITH_DEV=1; shift ;;
    --with-identity) WITH_ID=1; shift ;;
    --with-agent-skills) WITH_SKILLS=1; shift ;;
    --with-angular-api-proxy) WITH_AAP=1; shift ;;
    --with)
      shift
      [[ $# -gt 0 ]] || die_ask "--with needs a repository name"
      case "$1" in
        apaleo) ;;
        development) WITH_DEV=1 ;;
        identity) WITH_ID=1 ;;
        agent-skills) WITH_SKILLS=1 ;;
        angular-api-proxy) WITH_AAP=1 ;;
        *)
          python3 "$PIPELINE_DIR/common.py" valid-extra-name --name "$1" \
            || die_ask "refusing repository name $1"
          EXTRA_WITH+=("$1")
          ;;
      esac
      shift
      ;;
    --apaleo-only) APALEO_ONLY=1; shift ;;
    --agent-skills-only) SKILLS_ONLY=1; shift ;;
    --angular-api-proxy-only) AAP_ONLY=1; shift ;;
    -*) echo "unknown option $1" >&2; exit 2 ;;
    *) BRANCH="$1"; shift ;;
  esac
done
[[ -n "$BRANCH" ]] || die_ask "pass a branch name"
[[ "$BRANCH" != "master" && "$BRANCH" != "main" ]] || die_ask "refusing to create a feature worktree named $BRANCH"
ONLY_COUNT=$(( APALEO_ONLY + SKILLS_ONLY + AAP_ONLY ))
[[ "$ONLY_COUNT" -le 1 ]] || die_ask "pass at most one of --apaleo-only, --agent-skills-only, --angular-api-proxy-only"
if [[ "$SKILLS_ONLY" == "1" && ( "$WITH_DEV" == "1" || "$WITH_ID" == "1" || "$WITH_AAP" == "1" ) ]]; then
  die_ask "--agent-skills-only cannot be combined with development/identity/angular-api-proxy flags"
fi
if [[ "$AAP_ONLY" == "1" && ( "$WITH_DEV" == "1" || "$WITH_ID" == "1" || "$WITH_SKILLS" == "1" ) ]]; then
  die_ask "--angular-api-proxy-only cannot be combined with development/identity/agent-skills flags"
fi
REQUEST="$BRANCH"
RESOLVED_BRANCH="$(resolve_feature_branch "$REQUEST")"
if [[ "$RESOLVED_BRANCH" != "$REQUEST" ]] || feature_worktree_exists "$ROOT/worktrees/$RESOLVED_BRANCH"; then
  BRANCH="$RESOLVED_BRANCH"
elif [[ "$REQUEST" == http* || ( "$REQUEST" != */* && "$(normalize_feature_query "$REQUEST")" =~ ^[a-z]+-[0-9]+$ ) ]]; then
  die_ask "could not resolve '$REQUEST' to an existing branch — pass the full new branch name (for example <github-login>/<issue-id>-<slug>)"
fi

for main in "${FEATURE_REPOS[@]}"; do
  is_git_checkout "$ROOT/$main" || continue
  cur="$(git -C "$ROOT/$main" branch --show-current 2>/dev/null || true)"
  if [[ -n "$cur" && "$cur" != "master" ]]; then
    die_ask "main $main is on '$cur', not master — park it first"
  fi
  if [[ -n "$(git -C "$ROOT/$main" status --porcelain --untracked-files=no 2>/dev/null)" ]]; then
    die_ask "main $main has dirty tracked files"
  fi
done

WT="$ROOT/worktrees/$BRANCH"
mkdir -p "$WT"

main_has_branch() {
  local main="$1"
  is_git_checkout "$ROOT/$main" || return 1
  git -C "$ROOT/$main" show-ref --verify --quiet "refs/heads/$BRANCH" || \
    git -C "$ROOT/$main" show-ref --verify --quiet "refs/remotes/origin/$BRANCH"
}

for main in "${FEATURE_REPOS[@]}"; do
  is_git_checkout "$ROOT/$main" || continue
  git -C "$ROOT/$main" fetch --prune --quiet origin || true
done

ensure_repo() {
  local main="$1" dest="$2" required="$3" source="${4:-}"
  [[ -n "$source" ]] || source="$ROOT/$main"
  if is_git_checkout "$dest"; then
    local cur
    cur="$(git -C "$dest" branch --show-current)"
    if [[ "$cur" != "$BRANCH" ]]; then
      die_ask "$dest is on '$cur', expected $BRANCH"
    fi
    echo "$main: reused $dest $(git -C "$dest" rev-parse --short HEAD)"
    return 0
  fi
  if [[ -e "$dest" ]]; then
    die_ask "$dest exists but is not a git worktree"
  fi
  git -C "$source" rev-parse --git-dir >/dev/null 2>&1 || {
    if [[ "$required" == "1" ]]; then
      die_ask "clone https://github.com/apaleo/$main.git into $ROOT/$main first"
    fi
    echo "$main: skipped (no parked clone)"
    return 0
  }
  git -C "$source" fetch --prune --quiet origin || true
  if [[ "$FROM_MASTER" == "1" ]]; then
    if git -C "$source" show-ref --verify --quiet "refs/heads/$BRANCH"; then
      die_ask "branch $BRANCH already exists in $main — omit --from-master"
    fi
    local base_ref="origin/master"
    git -C "$source" show-ref --verify --quiet refs/remotes/origin/master || base_ref="master"
    git -C "$source" worktree add -b "$BRANCH" "$dest" "$base_ref" \
      || die_ask "could not create $dest from $base_ref"
    echo "$main: created-from-master $dest $(git -C "$dest" rev-parse --short HEAD)"
    return 0
  fi
  if git -C "$source" show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git -C "$source" worktree add "$dest" "$BRANCH"
  elif git -C "$source" show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
    git -C "$source" worktree add --track -b "$BRANCH" "$dest" "origin/$BRANCH"
  else
    if [[ "$required" == "1" ]]; then
      die_ask "$main has no branch $BRANCH (pass --from-master to create)"
    fi
    echo "$main: skipped (no branch)"
    return 0
  fi
  echo "$main: created $dest $(git -C "$dest" rev-parse --short HEAD)"
}

origin_is_apaleo_repo() {
  local dest="$1" name="$2" url
  url="$(git -C "$dest" config --get remote.origin.url 2>/dev/null || true)"
  url="${url%.git}"
  [[ "$url" == *":apaleo/$name" || "$url" == */apaleo/"$name" ]]
}

ensure_extra() {
  local name="$1" dest source mirror
  dest="$WT/$name"
  python3 "$PIPELINE_DIR/common.py" valid-extra-name --name "$name" \
    || die_ask "refusing repository name $name"
  if is_git_checkout "$dest"; then
    local cur
    cur="$(git -C "$dest" branch --show-current)"
    [[ "$cur" == "$BRANCH" ]] || die_ask "$dest is on '$cur', expected $BRANCH"
    python3 "$PIPELINE_DIR/common.py" record-extra --root "$ROOT" --branch "$BRANCH" --name "$name"
    echo "$name: reused $dest $(git -C "$dest" rev-parse --short HEAD)"
    return 0
  fi
  [[ ! -e "$dest" ]] || die_ask "$dest exists but is not a git worktree"
  if is_git_checkout "$ROOT/$name"; then
    origin_is_apaleo_repo "$ROOT/$name" "$name" \
      || die_ask "$ROOT/$name is not a checkout of apaleo/$name"
    local cur
    cur="$(git -C "$ROOT/$name" branch --show-current 2>/dev/null || true)"
    [[ -z "$cur" || "$cur" == "master" ]] || die_ask "main $name is on '$cur', not master — park it first"
    [[ -z "$(git -C "$ROOT/$name" status --porcelain --untracked-files=no 2>/dev/null)" ]] \
      || die_ask "main $name has dirty tracked files"
    source="$ROOT/$name"
  else
    mirror="$ROOT/.repos/$name.git"
    if [[ ! -d "$mirror" ]]; then
      gh repo view "apaleo/$name" --json name -q .name >/dev/null 2>&1 \
        || die_ask "apaleo/$name is not a repository you can see"
      mkdir -p "$ROOT/.repos"
      if ! git clone --bare "git@github.com:apaleo/${name}.git" "$mirror"; then
        rm -rf "$mirror"
        die_ask "could not mirror apaleo/$name"
      fi
    fi
    source="$mirror"
  fi
  ensure_repo "$name" "$dest" 1 "$source"
  python3 "$PIPELINE_DIR/common.py" record-extra --root "$ROOT" --branch "$BRANCH" --name "$name"
}

attach_optional_product_repos() {
  if [[ "$WITH_DEV" == "1" ]] || git -C "$ROOT/development" show-ref --verify --quiet "refs/remotes/origin/$BRANCH" 2>/dev/null; then
    ensure_repo development "$WT/development" "$WITH_DEV"
  else
    echo "development: skipped (no origin/$BRANCH)"
  fi
  if [[ "$WITH_ID" == "1" ]] || git -C "$ROOT/identity" show-ref --verify --quiet "refs/remotes/origin/$BRANCH" 2>/dev/null; then
    ensure_repo identity "$WT/identity" "$WITH_ID"
  else
    echo "identity: skipped (no origin/$BRANCH)"
  fi
  if [[ "$WITH_AAP" == "1" ]] || git -C "$ROOT/angular-api-proxy" show-ref --verify --quiet "refs/remotes/origin/$BRANCH" 2>/dev/null; then
    ensure_repo angular-api-proxy "$WT/angular-api-proxy" "$WITH_AAP"
  else
    echo "angular-api-proxy: skipped (no origin/$BRANCH)"
  fi
}

if [[ "$SKILLS_ONLY" == "1" ]]; then
  ensure_repo agent-skills "$WT/agent-skills" 1
elif [[ "$AAP_ONLY" == "1" ]]; then
  ensure_repo angular-api-proxy "$WT/angular-api-proxy" 1
elif [[ "$APALEO_ONLY" == "1" ]]; then
  ensure_repo apaleo "$WT/apaleo" 1
else
  want_apaleo=0
  want_skills=0
  want_aap=0
  [[ "$FROM_MASTER" == "1" ]] && want_apaleo=1
  if main_has_branch apaleo || is_git_checkout "$WT/apaleo"; then
    want_apaleo=1
  fi
  if [[ "$WITH_SKILLS" == "1" ]] || main_has_branch agent-skills || is_git_checkout "$WT/agent-skills"; then
    want_skills=1
  fi
  if [[ "$WITH_AAP" == "1" ]] || main_has_branch angular-api-proxy || is_git_checkout "$WT/angular-api-proxy"; then
    want_aap=1
  fi
  if [[ "$want_apaleo" == "1" ]]; then
    ensure_repo apaleo "$WT/apaleo" 1
    if [[ "$want_skills" == "1" ]]; then
      ensure_repo agent-skills "$WT/agent-skills" "$WITH_SKILLS"
    else
      echo "agent-skills: skipped (no origin/$BRANCH)"
    fi
    attach_optional_product_repos
  elif [[ "$want_skills" == "1" ]]; then
    ensure_repo agent-skills "$WT/agent-skills" 1
  elif [[ "$want_aap" == "1" ]]; then
    ensure_repo angular-api-proxy "$WT/angular-api-proxy" 1
  else
    if [[ ${#EXTRA_WITH[@]} -eq 0 ]]; then
      die_ask "no repo has branch $BRANCH (pass --from-master, or --agent-skills-only / --angular-api-proxy-only with --from-master)"
    fi
    echo "apaleo: skipped (no branch)"
  fi
fi

attach_extra_names() {
  local name seen=" "
  for name in "$@"; do
    [[ -n "$name" ]] || continue
    case "$seen" in *" $name "*) continue ;; esac
    seen+="$name "
    ensure_extra "$name"
  done
}

RECORDED=()
while IFS= read -r recorded_name; do
  [[ -n "$recorded_name" ]] && RECORDED+=("$recorded_name")
done < <(python3 "$PIPELINE_DIR/common.py" extra-repos --root "$ROOT" --branch "$BRANCH")
attach_extra_names "${EXTRA_WITH[@]:-}" "${RECORDED[@]:-}"
feature_worktree_exists "$WT" \
  || die_ask "no repo has branch $BRANCH (pass --from-master, or --with <repository>)"

echo "ROOT=$ROOT"
echo "WT=$WT"
echo "BRANCH=$BRANCH"
mains=""
for main in "${FEATURE_REPOS[@]}"; do
  is_git_checkout "$ROOT/$main" || continue
  mains+="${mains:+ }$main:$(git -C "$ROOT/$main" branch --show-current)"
done
echo "mains=$mains"
