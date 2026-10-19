#!/usr/bin/env bash
# Run one read-only query against the staging core database (Aurora PostgreSQL).
# Uses AWS IAM database authentication; never prints the token.
#
#   staging-sql.sh --check                  # VPN, token, and login check
#   staging-sql.sh 'SELECT ... LIMIT 20'    # CSV with a header row on stdout
#   staging-sql.sh -f query.sql
#
# Read-only is enforced three times: the statement must start with SELECT, WITH, EXPLAIN,
# SHOW, TABLE, or VALUES; the session sets default_transaction_read_only=on; and the query
# runs inside BEGIN TRANSACTION READ ONLY ... ROLLBACK.
#
# Environment (all optional):
#   STAGING_DB_HOST  default apaleo-staging-aurora-cluster.cluster-ck4y76z3d9vq.eu-west-1.rds.amazonaws.com
#   STAGING_DB_NAME  default apaleo
#   STAGING_DB_USER  default: the IAM user name with "." replaced by "_" (marko.arsov -> marko_arsov)
#   AWS_PROFILE      AWS CLI profile for the staging account (default profile when unset)
#
# Exit codes: 0 ok, 1 query error, 2 usage, 3 network/VPN, 4 authentication.
set -euo pipefail

HOST="${STAGING_DB_HOST:-apaleo-staging-aurora-cluster.cluster-ck4y76z3d9vq.eu-west-1.rds.amazonaws.com}"
DB="${STAGING_DB_NAME:-apaleo}"
PORT=5432
REGION=eu-west-1

usage() { sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

PSQL="$(command -v psql 2>/dev/null || true)"
if [[ -z "$PSQL" ]] && command -v brew >/dev/null 2>&1; then
  PSQL="$(brew --prefix libpq 2>/dev/null)/bin/psql"
fi
[[ -x "$PSQL" ]] || { echo "psql not found. Install it with: brew install libpq" >&2; exit 2; }

mode="query"
query=""
case "${1:-}" in
  ""|-h|--help) usage; exit 0 ;;
  --check) mode="check"; query="SELECT current_user AS db_user, current_setting('default_transaction_read_only') AS session_read_only" ;;
  -f) [[ -f "${2:-}" ]] || { echo "No such file: ${2:-}" >&2; exit 2; }; query="$(cat "$2")" ;;
  *) query="$1" ;;
esac

# Defence in depth: one statement, and it must start with a reading keyword.
stripped="$(printf '%s\n' "$query" | sed -E 's/--.*$//' | tr '\n' ' ' | sed -E 's/^[[:space:]]+//; s/[[:space:];]+$//')"
first="$(printf '%s' "$stripped" | awk '{print toupper($1)}')"
case "$first" in
  SELECT|WITH|EXPLAIN|SHOW|TABLE|VALUES) ;;
  *) echo "Refused: only read-only statements (SELECT, WITH, EXPLAIN, SHOW, TABLE, VALUES)." >&2; exit 2 ;;
esac
if [[ "$stripped" == *";"* ]]; then
  echo "Refused: one statement per call." >&2
  exit 2
fi

if ! nc -z -G 5 "$HOST" "$PORT" >/dev/null 2>&1; then
  echo "Cannot reach $HOST:$PORT. Connect the staging VPN (AWS VPN Client) and retry." >&2
  exit 3
fi

USER_NAME="${STAGING_DB_USER:-}"
if [[ -z "$USER_NAME" ]]; then
  arn="$(aws sts get-caller-identity --query Arn --output text 2>/dev/null || true)"
  [[ -n "$arn" ]] || { echo "AWS CLI is not authenticated for the staging account." >&2; exit 4; }
  USER_NAME="$(basename "$arn" | tr '.' '_')"
fi

token="$(aws rds generate-db-auth-token --hostname "$HOST" --port "$PORT" --region "$REGION" \
  --username "$USER_NAME" 2>/dev/null || true)"
[[ -n "$token" ]] || { echo "Could not generate an IAM database token." >&2; exit 4; }

set +e
output="$(PGPASSWORD="$token" PGSSLMODE=require PGCONNECT_TIMEOUT=10 PGAPPNAME=staging-sql-readonly \
  PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=30000" \
  "$PSQL" -X -q -v ON_ERROR_STOP=1 --csv -h "$HOST" -p "$PORT" -U "$USER_NAME" -d "$DB" \
  -c "BEGIN TRANSACTION READ ONLY" -c "$stripped" -c "ROLLBACK" 2>&1)"
status=$?
set -e
unset token

if (( status != 0 )); then
  if grep -qiE "password authentication failed|PAM authentication failed|no pg_hba" <<<"$output"; then
    echo "Authentication failed for $USER_NAME (IAM user or rds_iam grant missing?)." >&2
    exit 4
  fi
  printf '%s\n' "$output" >&2
  exit 1
fi
printf '%s\n' "$output"
