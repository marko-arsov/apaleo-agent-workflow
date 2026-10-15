#!/usr/bin/env bash
# Regenerate portal when skills or progress artifacts change.
set -euo pipefail
SKILLS="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
GEN="$(cd "$(dirname "$0")" && pwd)/generate.py"
echo "Watching skills + ai-plans + pipeline-state — Ctrl+C to stop"
last=""
while true; do
  sig="$(
    {
      find "$SKILLS" -name SKILL.md -not -path '*/portal/*' -print0 2>/dev/null
      find "$ROOT/ai-plans" -type f \( -name '*.md' -o -name 'pipeline-progress.json' \) -print0 2>/dev/null
      find "$ROOT/.local/pipeline-state" -type f -name 'progress.json' -print0 2>/dev/null
    } | xargs -0 stat -f '%m %N' 2>/dev/null | sort | md5
  )"
  if [[ "$sig" != "$last" ]]; then
    python3 "$GEN"
    last="$sig"
  fi
  sleep 2
done
