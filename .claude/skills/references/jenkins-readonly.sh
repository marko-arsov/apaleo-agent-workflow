#!/usr/bin/env bash
# Read-only Jenkins queries for staging and production readiness. GET requests only.
# Never prints the Jenkins token.
#
#   jenkins-readonly.sh builds <repo> [count]      # last master builds: number, result, sha, finished
#   jenkins-readonly.sh build-for <repo> <sha>     # first master build whose commit contains <sha>
#   jenkins-readonly.sh console <repo> <build> [lines]   # tail of one master build's console
#   jenkins-readonly.sh prod <param> [count]       # latest Deployment/Core run that set <param>
#                                                  # (e.g. apiVersion, uiVersion, identityVersion)
#
# <repo> is the GitHub repository name (apaleo, development, identity, ...). Master builds deploy
# to staging when green; production is deployed by hand through Deployment/Core.
# Credentials: JENKINS_URL, JENKINS_USER, JENKINS_TOKEN from the environment, ~/.config/jenkins.env,
# or the login shell (~/.zshrc). Needs the VPN.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../pipeline/root.sh"
ROOT="$(resolve_root)"

usage() { sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

load_credentials() {
  if [[ -z "${JENKINS_URL:-}" || -z "${JENKINS_USER:-}" || -z "${JENKINS_TOKEN:-}" ]]; then
    [[ -f "$HOME/.config/jenkins.env" ]] && set -a && source "$HOME/.config/jenkins.env" && set +a
  fi
  if [[ -z "${JENKINS_URL:-}" || -z "${JENKINS_USER:-}" || -z "${JENKINS_TOKEN:-}" ]]; then
    eval "$(zsh -ic 'printf "JENKINS_URL=%q\nJENKINS_USER=%q\nJENKINS_TOKEN=%q\n" "$JENKINS_URL" "$JENKINS_USER" "$JENKINS_TOKEN"' 2>/dev/null)"
  fi
  if [[ -z "${JENKINS_URL:-}" || -z "${JENKINS_USER:-}" || -z "${JENKINS_TOKEN:-}" ]]; then
    echo "Jenkins credentials missing (JENKINS_URL/USER/TOKEN)." >&2
    exit 4
  fi
  JENKINS_URL="${JENKINS_URL%/}"
}

get() {
  local out code
  out="$(curl -sS -k -g --max-time 20 -u "$JENKINS_USER:$JENKINS_TOKEN" -w '\n%{http_code}' "$JENKINS_URL$1" 2>/dev/null)" || {
    echo "Cannot reach Jenkins. Connect the VPN and retry." >&2; exit 3; }
  code="${out##*$'\n'}"
  out="${out%$'\n'*}"
  case "$code" in
    200) printf '%s' "$out" ;;
    401|403) echo "Jenkins refused the credentials (HTTP $code)." >&2; exit 4 ;;
    404) echo "Not found in Jenkins: $1" >&2; exit 1 ;;
    *) echo "Jenkins returned HTTP $code for $1" >&2; exit 1 ;;
  esac
}

master_job() { printf '/job/apaleo/job/%s/job/master' "$1"; }

BUILD_TREE='builds[number,result,building,timestamp,duration,actions[lastBuiltRevision[SHA1],remoteUrls]]'
BUILD_JQ='{number, result: (if .building then "RUNNING" else .result end),
  sha: ([.actions[]? | select(.lastBuiltRevision != null)
          | select(any(.remoteUrls[]?; endswith("/" + $repo + ".git") or endswith("/" + $repo)))
          | .lastBuiltRevision.SHA1][0]),
  finished: (if .building then null else ((.timestamp + .duration) / 1000 | todate) end)}'

cmd="${1:-}"
case "$cmd" in
  ""|-h|--help) usage; exit 0 ;;
esac
load_credentials

case "$cmd" in
  builds)
    repo="${2:?repo required}"; count="${3:-10}"
    get "$(master_job "$repo")/api/json?tree=${BUILD_TREE}{0,${count}}" \
      | jq -c --arg repo "$repo" ".builds[] | $BUILD_JQ | .sha = (.sha // \"\" | .[0:7])"
    ;;
  build-for)
    repo="${2:?repo required}"; sha="${3:?sha required}"
    repo_dir="$ROOT/$repo"
    [[ -d "$repo_dir/.git" ]] || { echo "No local clone at $repo_dir for ancestry checks." >&2; exit 2; }
    git -C "$repo_dir" fetch -q origin master 2>/dev/null || true
    full="$(git -C "$repo_dir" rev-parse --verify -q "${sha}^{commit}" || true)"
    [[ -n "$full" ]] || { echo "Commit $sha not found in $repo_dir." >&2; exit 2; }
    # Oldest build first, so the first descendant is the build that shipped the commit.
    get "$(master_job "$repo")/api/json?tree=${BUILD_TREE}{0,60}" \
      | jq -c --arg repo "$repo" ".builds | reverse | .[] | $BUILD_JQ" \
      | while IFS= read -r row; do
          b_sha="$(jq -r '.sha // empty' <<<"$row")"
          [[ -n "$b_sha" ]] || continue
          if git -C "$repo_dir" merge-base --is-ancestor "$full" "$b_sha" 2>/dev/null; then
            jq -c '.sha = (.sha | .[0:7])' <<<"$row"
            exit 0
          fi
        done
    ;;
  console)
    repo="${2:?repo required}"; build="${3:?build number required}"; lines="${4:-80}"
    get "$(master_job "$repo")/${build}/consoleText" | tail -n "$lines"
    ;;
  prod)
    param="${2:?parameter required, e.g. apiVersion}"; count="${3:-100}"
    get "/job/Deployment/job/Core/api/json?tree=builds[number,result,building,timestamp,actions[parameters[name,value]]]{0,${count}}" \
      | jq -c --arg p "$param" '[.builds[]
          | {number, result: (if .building then "RUNNING" else .result end),
             started: (.timestamp / 1000 | todate),
             value: ([.actions[]?.parameters[]? | select(.name == $p) | .value][0] // "")}
          | select(.value != "")][0] // {"error": "no Deployment/Core run set this parameter in the scanned builds"}'
    ;;
  *) echo "Unknown command: $cmd" >&2; usage >&2; exit 2 ;;
esac
