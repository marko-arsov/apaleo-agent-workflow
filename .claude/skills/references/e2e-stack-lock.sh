#!/usr/bin/env bash
# Shared localhost E2E stack lock + FIFO queue for Apaleo worktrees.
# See $ROOT/.claude/skills/references/e2e-stack.md
set -euo pipefail

ROOT="${APALEO_ROOT:-}"
if [[ -z "$ROOT" ]]; then
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
fi

if [[ -z "${ROOT:-}" || ! -f "$ROOT/AGENTS.md" ]]; then
  echo "error: could not resolve APALEO_ROOT" >&2
  exit 2
fi

LOCAL_DIR="$ROOT/.local"
LOCK_FILE="$LOCAL_DIR/e2e-stack.lock"
QUEUE_FILE="$LOCAL_DIR/e2e-stack.queue.json"
POLL_SECONDS="${E2E_STACK_POLL_SECONDS:-30}"
MAX_WAIT_SECONDS="${E2E_STACK_MAX_WAIT_SECONDS:-7200}"
STALE_SECONDS=$((6 * 3600))
DOCKER_BUILD_CACHE_MAX_USED_SPACE="${APALEO_DOCKER_BUILD_CACHE_MAX_USED_SPACE:-20GB}"

mkdir -p "$LOCAL_DIR"

py() { python3 "$@"; }

short_slug() {
  local base="${1##*/}"
  echo "$base" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g' | cut -c1-40
}

image_for_branch() { echo "apaleo-ui-api:wt-$(short_slug "$1")"; }
identity_image_for_branch() { echo "apaleo-identity:wt-$(short_slug "$1")"; }

docker_available() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
}

remove_temporary_image() {
  local image="$1"
  if ! docker image inspect "$image" >/dev/null 2>&1; then
    echo "docker_image_cleanup=absent image=$image"
    return 0
  fi

  # Never force removal: a missed restoration must preserve the image instead of
  # breaking the shared stack or an exited container that still needs inspection.
  if docker ps -a --filter "ancestor=$image" --format '{{.ID}}' 2>/dev/null | grep -q .; then
    echo "docker_image_cleanup=retained-in-use image=$image"
    return 0
  fi

  if docker image rm "$image" >/dev/null 2>&1; then
    echo "docker_image_cleanup=removed image=$image"
  else
    echo "docker_image_cleanup=retained-remove-failed image=$image" >&2
  fi
}

cleanup_docker_artifacts() {
  local branch="$1"
  if ! docker_available; then
    echo "docker_cleanup=skipped-daemon-unavailable" >&2
    return 0
  fi

  # These names are allocated solely by this lock. They are removed only after
  # the caller has restored the previous compose image and before the next
  # worktree can acquire the shared stack.
  remove_temporary_image "$(image_for_branch "$branch")"
  remove_temporary_image "$(identity_image_for_branch "$branch")"

  # BuildKit otherwise retains every worktree's expensive publish layers. A
  # size cap removes least-recently-used cache records; it never touches images,
  # containers, volumes, or networks.
  if docker buildx prune --all --force \
    --max-used-space "$DOCKER_BUILD_CACHE_MAX_USED_SPACE" >/dev/null 2>&1; then
    echo "docker_build_cache_cleanup=capped via=buildx max_used_space=$DOCKER_BUILD_CACHE_MAX_USED_SPACE"
  elif docker builder prune --all --force \
    --keep-storage "$DOCKER_BUILD_CACHE_MAX_USED_SPACE" >/dev/null 2>&1; then
    # Older Docker installations may not provide buildx or its size-cap flag.
    echo "docker_build_cache_cleanup=capped via=builder max_used_space=$DOCKER_BUILD_CACHE_MAX_USED_SPACE"
  else
    echo "docker_build_cache_cleanup=failed max_used_space=$DOCKER_BUILD_CACHE_MAX_USED_SPACE" >&2
  fi
}

pid_alive() {
  local pid="$1"
  [[ -n "$pid" && "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null
}

now_iso() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
now_epoch() { date +%s; }

iso_to_epoch() {
  local iso="$1"
  date -j -f "%Y-%m-%dT%H:%M:%SZ" "$iso" +%s 2>/dev/null \
    || date -u -d "$iso" +%s 2>/dev/null \
    || echo 0
}

jget() {
  # jget <file|json-string> <key>  — if arg1 is a file path, read file
  local src="$1" key="$2"
  if [[ -f "$src" ]]; then
    py -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2],""))' "$src" "$key"
  else
    py -c 'import json,sys; print(json.loads(sys.argv[1]).get(sys.argv[2],""))' "$src" "$key"
  fi
}

ensure_queue() {
  [[ -f "$QUEUE_FILE" ]] || echo '[]' >"$QUEUE_FILE"
}

prune_queue() {
  ensure_queue
  local max_age="${E2E_STACK_QUEUE_MAX_AGE_SECONDS:-86400}"
  py - "$QUEUE_FILE" "$max_age" <<'PY'
import json, sys, time
path, max_age = sys.argv[1], int(sys.argv[2])
with open(path) as f:
    q = json.load(f)
now = time.time()

def parse_ts(ts):
    # 2026-08-13T14:25:33Z
    try:
        from datetime import datetime, timezone
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return now

alive = []
seen = set()
for e in q:
    b = e.get("branch")
    if not b or b in seen:
        continue
    age = now - parse_ts(e.get("enqueued_at", ""))
    if age > max_age:
        continue
    seen.add(b)
    alive.append(e)
with open(path, "w") as f:
    json.dump(alive, f, indent=2)
    f.write("\n")
PY
}

enqueue() {
  local branch="$1" worktree="$2" skill="$3"
  prune_queue
  py - "$QUEUE_FILE" "$branch" "$worktree" "$skill" "$$" "$(now_iso)" <<'PY'
import json, sys
path, branch, worktree, skill, pid, ts = sys.argv[1:7]
with open(path) as f:
    q = json.load(f)
if not any(e.get("branch") == branch for e in q):
    q.append({
        "branch": branch,
        "worktree": worktree,
        "skill": skill,
        "pid": int(pid),
        "enqueued_at": ts,
    })
with open(path, "w") as f:
    json.dump(q, f, indent=2)
    f.write("\n")
print(next(i for i, e in enumerate(q) if e["branch"] == branch) + 1)
PY
}

dequeue_branch() {
  local branch="$1"
  ensure_queue
  py - "$QUEUE_FILE" "$branch" <<'PY'
import json, sys
path, branch = sys.argv[1:3]
with open(path) as f:
    q = json.load(f)
q = [e for e in q if e.get("branch") != branch]
with open(path, "w") as f:
    json.dump(q, f, indent=2)
    f.write("\n")
PY
}

queue_position() {
  local branch="$1"
  prune_queue
  py - "$QUEUE_FILE" "$branch" <<'PY'
import json, sys
path, branch = sys.argv[1:3]
with open(path) as f:
    q = json.load(f)
for i, e in enumerate(q):
    if e.get("branch") == branch:
        print(i + 1)
        raise SystemExit(0)
print(0)
PY
}

queue_head() {
  prune_queue
  py - "$QUEUE_FILE" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    q = json.load(f)
print(q[0]["branch"] if q else "")
PY
}

lock_held_live() {
  [[ -f "$LOCK_FILE" ]] || return 1
  local pid
  pid="$(jget "$LOCK_FILE" pid)"
  if pid_alive "$pid"; then
    return 0
  fi
  local acquired epoch now
  acquired="$(jget "$LOCK_FILE" acquired_at)"
  epoch="$(iso_to_epoch "$acquired")"
  now="$(now_epoch)"
  if [[ "$epoch" -gt 0 ]] && (( now - epoch < STALE_SECONDS )); then
    # dead pid but fresh lock — still treat as held (agent may have forked)
    return 0
  fi
  return 1  # stale → treat as free
}

write_lock() {
  local branch="$1" worktree="$2" skill="$3" image="$4"
  local tmp
  tmp="$(mktemp "$LOCAL_DIR/e2e-stack.lock.XXXXXX")"
  py - "$tmp" "$branch" "$worktree" "$skill" "$$" "$(now_iso)" "$image" <<'PY'
import json, sys
path, branch, worktree, skill, pid, ts, image = sys.argv[1:8]
data = {
    "branch": branch,
    "worktree": worktree,
    "skill": skill,
    "pid": int(pid),
    "acquired_at": ts,
    "image": image,
}
with open(path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY
  mv "$tmp" "$LOCK_FILE"
}

try_acquire() {
  local branch="$1" worktree="$2" skill="$3" image="$4"

  # already ours
  if [[ -f "$LOCK_FILE" ]]; then
    if [[ "$(jget "$LOCK_FILE" branch)" == "$branch" ]]; then
      write_lock "$branch" "$worktree" "$skill" "$image"
      dequeue_branch "$branch"
      echo "acquired"
      echo "image=$image"
      if [[ -d "$worktree/identity" ]]; then
        echo "identity_image=$(identity_image_for_branch "$branch")"
      fi
      return 0
    fi
  fi

  if lock_held_live; then
    return 1
  fi

  # lock free/stale — FIFO: only head (or empty queue / only us) may take
  prune_queue
  local head pos
  head="$(queue_head)"
  pos="$(queue_position "$branch")"

  if [[ -n "$head" && "$head" != "$branch" ]]; then
    return 1  # someone else is ahead
  fi

  # empty queue or we are head (pos 1) or not yet queued (pos 0) with empty head
  if [[ -n "$head" && "$head" != "$branch" ]]; then
    return 1
  fi

  write_lock "$branch" "$worktree" "$skill" "$image"
  dequeue_branch "$branch"
  echo "acquired"
  echo "image=$image"
  echo "lock=$LOCK_FILE"
  if [[ -d "$worktree/identity" ]]; then
    echo "identity_image=$(identity_image_for_branch "$branch")"
  fi
  return 0
}

cmd_acquire() {
  local wait=0 branch="" worktree="" skill="test-and-fix"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --wait) wait=1; shift ;;
      --branch) branch="$2"; shift 2 ;;
      --worktree) worktree="$2"; shift 2 ;;
      --skill) skill="$2"; shift 2 ;;
      *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
  done
  [[ -n "$branch" && -n "$worktree" ]] || {
    echo "usage: acquire [--wait] --branch <b> --worktree <path> [--skill <name>]" >&2
    exit 2
  }

  local image started
  image="$(image_for_branch "$branch")"
  started="$(now_epoch)"

  while true; do
    if try_acquire "$branch" "$worktree" "$skill" "$image"; then
      exit 0
    fi

    local owner="none"
    if [[ -f "$LOCK_FILE" ]]; then
      owner="$(jget "$LOCK_FILE" branch)"
    fi
    local position
    position="$(enqueue "$branch" "$worktree" "$skill")"

    if [[ "$wait" -eq 0 ]]; then
      echo "queued"
      echo "position=$position"
      echo "owner=$owner"
      echo "next: re-run with --wait, or /e2e-stack-status"
      exit 3
    fi

    local elapsed=$(( $(now_epoch) - started ))
    if (( elapsed >= MAX_WAIT_SECONDS )); then
      echo "error: timed out after ${MAX_WAIT_SECONDS}s (owner=$owner position=$position)" >&2
      exit 4
    fi

    echo "waiting: owner=$owner position=$position poll=${POLL_SECONDS}s elapsed=${elapsed}s"
    sleep "$POLL_SECONDS"
  done
}

cmd_status() {
  echo "ROOT=$ROOT"
  if ! lock_held_live; then
    if [[ -f "$LOCK_FILE" ]]; then
      echo "Lock: stale (will be taken by next acquire)"
      cat "$LOCK_FILE"
    else
      echo "Lock: unlocked"
    fi
  else
    echo "Lock: held"
    cat "$LOCK_FILE"
    local pid
    pid="$(jget "$LOCK_FILE" pid)"
    if pid_alive "$pid"; then echo "PID: $pid alive"; else echo "PID: $pid dead (grace period)"; fi
  fi
  echo "Queue:"
  prune_queue
  cat "$QUEUE_FILE"
  echo -n "Running api image: "
  docker inspect apaleo-api-1 --format '{{.Config.Image}}' 2>/dev/null || echo "missing"
  echo -n "Running identity image: "
  docker inspect apaleo-identity-1 --format '{{.Config.Image}}' 2>/dev/null || echo "missing"
}

cmd_release() {
  local branch="" force=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --branch) branch="$2"; shift 2 ;;
      --force) force=1; shift ;;
      *) shift ;;
    esac
  done
  if [[ ! -f "$LOCK_FILE" ]]; then
    echo "already unlocked"
    [[ -n "$branch" ]] && dequeue_branch "$branch" || true
    exit 0
  fi
  local lock_branch
  lock_branch="$(jget "$LOCK_FILE" branch)"
  if [[ -n "$branch" && "$lock_branch" != "$branch" && "$force" -ne 1 ]]; then
    echo "error: lock held by $lock_branch (requested $branch). Use --force." >&2
    exit 1
  fi
  # Keep cleanup inside the lock so another worktree cannot start a concurrent
  # build while its predecessor's temporary image/cache is being reclaimed.
  cleanup_docker_artifacts "$lock_branch"
  rm -f "$LOCK_FILE"
  dequeue_branch "$lock_branch" || true
  echo "released"
  local head
  head="$(queue_head)"
  [[ -n "$head" ]] && echo "next_in_queue=$head"
}

usage() {
  cat <<EOF
Usage:
  $(basename "$0") status
  $(basename "$0") acquire [--wait] --branch <b> --worktree <path> [--skill <name>]
  $(basename "$0") release [--branch <b>] [--force]

Acquire exit codes: 0=acquired  3=queued (no --wait)  4=timeout  2=error
Env: E2E_STACK_POLL_SECONDS (default 30)  E2E_STACK_MAX_WAIT_SECONDS (default 7200)
     APALEO_ROOT (optional override)
     APALEO_DOCKER_BUILD_CACHE_MAX_USED_SPACE (default 20GB)
EOF
}

case "${1:-}" in
  status) shift; cmd_status "$@" ;;
  acquire) shift; cmd_acquire "$@" ;;
  release) shift; cmd_release "$@" ;;
  ""|-h|--help) usage ;;
  *) usage; exit 2 ;;
esac
