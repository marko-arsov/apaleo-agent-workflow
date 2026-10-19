#!/usr/bin/env bash
# Call the Apaleo staging API with a client-credentials token.
# Never prints the client secret or the access token.
#
#   staging-api.sh whoami
#   staging-api.sh GET    '/booking/v1/blocks/BER-X?expand=timeSlices'
#   staging-api.sh PUT    /booking/v1/block-actions/BER-X/amend '<json>'
#   staging-api.sh POST|PATCH|DELETE <path> ['<json>']
#   staging-api.sh logout
#
# Credentials: APALEO_STAGING_CLIENT_ID + APALEO_STAGING_CLIENT_SECRET, or
# $ROOT/.local/staging-api/staging-client.json {"clientId","clientSecret"}.
# The response body goes to stdout and "HTTP <code>" to stderr; exit 1 on >= 400.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../pipeline/root.sh"
ROOT="$(resolve_root)"

IDENTITY="${APALEO_STAGING_IDENTITY:-https://identity.apaleo-staging.com}"
API="${APALEO_STAGING_API:-https://api.apaleo-staging.com}"
STATE_DIR="$ROOT/.local/staging-api"
CLIENT_FILE="$STATE_DIR/staging-client.json"
TOKEN_FILE="$STATE_DIR/.token"

usage() {
  sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

claims() {
  local payload
  payload="$(cut -d. -f2 "$TOKEN_FILE" | tr '_-' '/+')"
  while (( ${#payload} % 4 )); do payload="$payload="; done
  printf '%s' "$payload" | base64 -d 2>/dev/null
}

token_valid() {
  [[ -s "$TOKEN_FILE" ]] || return 1
  local exp
  exp="$(claims | jq -r '.exp // 0' 2>/dev/null || echo 0)"
  (( exp > $(date +%s) + 60 ))
}

fetch_token() {
  local id secret
  if [[ -n "${APALEO_STAGING_CLIENT_ID:-}" && -n "${APALEO_STAGING_CLIENT_SECRET:-}" ]]; then
    id="$APALEO_STAGING_CLIENT_ID"
    secret="$APALEO_STAGING_CLIENT_SECRET"
  elif [[ -f "$CLIENT_FILE" ]]; then
    id="$(jq -r '.clientId // empty' "$CLIENT_FILE")"
    secret="$(jq -r '.clientSecret // empty' "$CLIENT_FILE")"
  fi
  if [[ -z "${id:-}" || -z "${secret:-}" ]]; then
    echo "No staging client credentials. Set APALEO_STAGING_CLIENT_ID/SECRET or create $CLIENT_FILE." >&2
    exit 2
  fi
  mkdir -p "$STATE_DIR"
  umask 077
  local response
  response="$(curl -sS -u "$id:$secret" -d grant_type=client_credentials "$IDENTITY/connect/token")"
  unset secret
  if ! jq -e -r '.access_token' <<<"$response" >"$TOKEN_FILE" 2>/dev/null; then
    rm -f "$TOKEN_FILE"
    echo "Token request failed: $(jq -r '.error // "unknown error"' <<<"$response" 2>/dev/null)" >&2
    exit 1
  fi
}

case "${1:-}" in
  ""|-h|--help)
    usage
    exit 0
    ;;
  logout)
    rm -f "$TOKEN_FILE"
    echo "Token removed."
    exit 0
    ;;
  whoami)
    token_valid || fetch_token
    claims | jq '{client_id, account_code: (.account_code // .acc), expires: (.exp | todate), scopes: .scope}'
    exit 0
    ;;
esac

method="$(tr '[:lower:]' '[:upper:]' <<<"$1")"
path="${2:?path required}"
body="${3:-}"
case "$method" in
  GET|POST|PUT|PATCH|DELETE) ;;
  *) echo "Unknown method: $1" >&2; exit 2 ;;
esac
[[ "$path" == /* ]] || { echo "Path must start with /" >&2; exit 2; }

token_valid || fetch_token

args=(-sS -X "$method" -H "Accept: application/json" -H "Authorization: Bearer $(cat "$TOKEN_FILE")"
  -o /dev/stdout -w '%{stderr}HTTP %{http_code}\n')
if [[ -n "$body" ]]; then
  args+=(-H "Content-Type: application/json" --data "$body")
fi

status_file="$(mktemp)"
trap 'rm -f "$status_file"' EXIT
curl "${args[@]}" "$API$path" 2>"$status_file"
cat "$status_file" >&2
code="$(grep -Eo 'HTTP [0-9]+' "$status_file" | tail -1 | cut -d' ' -f2)"
[[ -n "$code" && "$code" -lt 400 ]]
