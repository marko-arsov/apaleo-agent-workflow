#!/usr/bin/env bash
# Ordered, fail-fast direct entry point for /commit-and-push.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/../commit/commit.sh" "$@"
"$SCRIPT_DIR/../push/push.sh" "$@"
