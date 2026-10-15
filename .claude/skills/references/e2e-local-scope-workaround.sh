#!/usr/bin/env bash
# Temporary local-only strip of missing Identity scopes from development/src/config.ts.
# NEVER commit the patched file. Always restore before commit/push/PR and on pipeline EXIT.
# See e2e-missing-identity-scopes.md
set -euo pipefail

ROOT="${APALEO_ROOT:-}"
DEV=""
SCOPES=""
CMD=""

usage() {
  cat <<'USAGE'
Usage:
  e2e-local-scope-workaround.sh apply  --dev <development-worktree> --scopes a,b
  e2e-local-scope-workaround.sh restore [--root <APALEO_ROOT>] [--dev <development-worktree>]
  e2e-local-scope-workaround.sh status  [--root <APALEO_ROOT>]
  e2e-local-scope-workaround.sh check-commit --dev <development-worktree>

apply         Strip listed scopes from src/config.ts allowedScopes (backs up original).
restore       Copy the backup back; clear state. Idempotent.
status        Print applied|clean and paths.
check-commit  Exit 1 if workaround is still applied (commit must restore first).
USAGE
}

resolve_root() {
  if [[ -n "$ROOT" && -f "$ROOT/AGENTS.md" ]]; then
    return 0
  fi
  local cwd d
  cwd="$(pwd -P 2>/dev/null || pwd)"
  if [[ "$cwd" == */worktrees/* ]]; then
    ROOT="${cwd%%/worktrees/*}"
  else
    d="$cwd"
    while [[ "$d" != "/" ]]; do
      if [[ -f "$d/AGENTS.md" && -d "$d/apaleo" && -d "$d/development" && "$d" != */worktrees/* ]]; then
        ROOT="$d"
        break
      fi
      d="$(dirname "$d")"
    done
  fi
  [[ -n "${ROOT:-}" && -f "$ROOT/AGENTS.md" ]] || {
    echo "error: could not resolve APALEO_ROOT" >&2
    exit 2
  }
}

STATE_DIR=""
STATE_FILE=""
BACKUP_FILE=""

init_paths() {
  resolve_root
  STATE_DIR="$ROOT/.local/e2e-scope-workaround"
  STATE_FILE="$STATE_DIR/state.json"
  BACKUP_FILE="$STATE_DIR/config.ts.orig"
  mkdir -p "$STATE_DIR"
}

die() { echo "error: $*" >&2; exit 2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    apply|restore|status|check-commit) CMD="$1"; shift ;;
    --root) ROOT="${2:?}"; shift 2 ;;
    --dev) DEV="${2:?}"; shift 2 ;;
    --scopes) SCOPES="${2:?}"; shift 2 ;;
    *) die "unknown arg: $1" ;;
  esac
done

[[ -n "$CMD" ]] || { usage; exit 2; }
init_paths

config_path() {
  local d="${1:-$DEV}"
  [[ -n "$d" ]] || die "need --dev <development-worktree>"
  echo "$d/src/config.ts"
}

py_strip() {
  python3 - "$1" "$2" <<'PY'
import pathlib, re, sys
path = pathlib.Path(sys.argv[1])
scopes = [s.strip() for s in sys.argv[2].split(",") if s.strip()]
text = path.read_text(encoding="utf-8")
lines = text.splitlines(keepends=True)
out = []
in_block = False
removed = []
for line in lines:
    stripped = line.strip()
    if not in_block and re.search(r"allowedScopes\s*:\s*\[", line):
        in_block = True
    skip = False
    if in_block:
        for s in scopes:
            if re.fullmatch(r"['\"]" + re.escape(s) + r"['\"],?", stripped):
                skip = True
                removed.append(s)
                break
        if "]" in line:
            in_block = False
    if skip:
        continue
    out.append(line)
new = "".join(out)
if not removed:
    sys.stderr.write("warning: none of the requested scopes were found in allowedScopes\n")
path.write_text(new, encoding="utf-8")
print(",".join(dict.fromkeys(removed)))
PY
}

write_state() {
  python3 - "$STATE_FILE" "$DEV" "$SCOPES" "$BACKUP_FILE" <<'PY'
import json, sys, datetime, pathlib
state_path, dev, scopes, backup = sys.argv[1:5]
pathlib.Path(state_path).write_text(json.dumps({
    "applied": True,
    "dev": dev,
    "file": "src/config.ts",
    "scopes": [s.strip() for s in scopes.split(",") if s.strip()],
    "backup": backup,
    "applied_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}, indent=2) + "\n", encoding="utf-8")
PY
}

read_state_dev() {
  [[ -f "$STATE_FILE" ]] || return 1
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("dev",""))' "$STATE_FILE"
}

is_applied() {
  [[ -f "$STATE_FILE" ]] || return 1
  python3 -c 'import json,sys; raise SystemExit(0 if json.load(open(sys.argv[1])).get("applied") else 1)' "$STATE_FILE"
}

cmd_status() {
  if is_applied; then
    echo "applied"
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("dev="+d.get("dev","")); print("scopes="+",".join(d.get("scopes") or [])); print("backup="+d.get("backup",""))' "$STATE_FILE"
  else
    echo "clean"
  fi
}

cmd_apply() {
  [[ -n "$DEV" ]] || die "apply requires --dev"
  [[ -n "$SCOPES" ]] || die "apply requires --scopes"
  local cfg
  cfg="$(config_path "$DEV")"
  [[ -f "$cfg" ]] || die "missing $cfg"
  if is_applied; then
    echo "already applied — restoring first so backup stays the unpatched file" >&2
    cmd_restore
  fi
  cp "$cfg" "$BACKUP_FILE"
  local removed
  removed="$(py_strip "$cfg" "$SCOPES")"
  write_state
  echo "stripped: ${removed:-none}"
  echo "backup: $BACKUP_FILE"
  echo "WARNING: local-only — restore before commit/push. Never git add this patch."
}

cmd_restore() {
  local dev="${DEV:-}"
  if [[ -z "$dev" ]] && [[ -f "$STATE_FILE" ]]; then
    dev="$(read_state_dev || true)"
  fi
  if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "clean (no backup)"
    rm -f "$STATE_FILE"
    return 0
  fi
  if [[ -z "$dev" ]]; then
    echo "warning: backup exists but no --dev / state.dev — leaving backup in place" >&2
    return 1
  fi
  local cfg
  cfg="$(config_path "$dev")"
  mkdir -p "$(dirname "$cfg")"
  cp "$BACKUP_FILE" "$cfg"
  rm -f "$BACKUP_FILE" "$STATE_FILE"
  echo "restored $cfg"
}

cmd_check_commit() {
  [[ -n "$DEV" ]] || die "check-commit requires --dev"
  if is_applied; then
    echo "workaround still applied at $(read_state_dev) — restore before commit" >&2
    exit 1
  fi
  echo "ok"
}

case "$CMD" in
  apply) cmd_apply ;;
  restore) cmd_restore ;;
  status) cmd_status ;;
  check-commit) cmd_check_commit ;;
esac
