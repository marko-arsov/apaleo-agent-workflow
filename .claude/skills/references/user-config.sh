#!/usr/bin/env bash
# Read one value from the per-user workflow configuration.
#
#   user-config.sh get staging.testAccount     # prints the value; exit 1 when unset
#   user-config.sh path                        # prints the file path
#   user-config.sh init                        # creates the file from the template (no overwrite)
#
# The file is $ROOT/.local/user-config.json: untracked, one per engineer. The template is
# references/user-config.example.json. Secrets never go in this file.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../pipeline/root.sh"
ROOT="$(resolve_root)"
FILE="$ROOT/.local/user-config.json"
TEMPLATE="$SCRIPT_DIR/user-config.example.json"

case "${1:-}" in
  path)
    echo "$FILE"
    ;;
  init)
    if [[ -f "$FILE" ]]; then
      echo "Already exists: $FILE"
    else
      mkdir -p "$(dirname "$FILE")"
      cp "$TEMPLATE" "$FILE"
      echo "Created $FILE from the template. Edit staging.testAccount before using staging writes."
    fi
    ;;
  get)
    key="${2:?key required, e.g. staging.testAccount}"
    [[ -f "$FILE" ]] || exit 1
    value="$(jq -r --arg k "$key" 'getpath($k | split(".")) // empty' "$FILE")"
    [[ -n "$value" ]] || exit 1
    printf '%s\n' "$value"
    ;;
  *)
    sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
