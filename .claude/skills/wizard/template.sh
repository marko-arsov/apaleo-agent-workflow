#!/usr/bin/env bash
# Copy this file, then edit only below "# ===== STAGES =====".
set -euo pipefail

TOTAL_STAGES=${TOTAL_STAGES:-1}
CURRENT_STAGE=0

say() { printf '%s\n' "$*"; }
step() { printf '  - %s\n' "$*"; }

stage() {
  CURRENT_STAGE=$((CURRENT_STAGE + 1))
  printf '\n[%s/%s] %s\n' "$CURRENT_STAGE" "$TOTAL_STAGES" "$*"
}

pause() {
  local prompt="${1:-Press Enter to continue}"
  read -r -p "$prompt"
}

confirm() {
  local prompt="${1:-Continue?}"
  local answer
  read -r -p "$prompt [y/N] " answer
  case "$answer" in
    y|Y|yes|YES) return 0 ;;
    *) say "Stopped."; exit 1 ;;
  esac
}

ask() {
  local prompt="$1"
  local value
  read -r -p "$prompt: " value
  printf '%s' "$value"
}

ask_secret() {
  local prompt="$1"
  local value
  read -r -s -p "$prompt: " value
  printf '\n' >&2
  printf '%s' "$value"
}

open_url() {
  local url="$1"
  if command -v open >/dev/null 2>&1; then
    open "$url"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 &
  elif command -v wslview >/dev/null 2>&1; then
    wslview "$url"
  else
    say "Open this URL: $url"
  fi
}

write_env() {
  local file="$1"
  local key="$2"
  local value="$3"
  mkdir -p "$(dirname "$file")"
  touch "$file"
  local tmp
  tmp="$(mktemp)"
  if grep -qE "^${key}=" "$file"; then
    awk -v k="$key" -v v="$value" 'BEGIN{FS=OFS="="} $1==k{$0=k"="v} {print}' "$file" > "$tmp"
  else
    cp "$file" "$tmp"
    printf '%s=%s\n' "$key" "$value" >> "$tmp"
  fi
  mv "$tmp" "$file"
}

set_secret() {
  local repo="$1"
  local name="$2"
  local value="$3"
  command -v gh >/dev/null 2>&1 || { say "gh CLI is required."; exit 1; }
  printf '%s' "$value" | gh secret set "$name" --repo "$repo" --body-file -
}

set_var() {
  local repo="$1"
  local name="$2"
  local value="$3"
  command -v gh >/dev/null 2>&1 || { say "gh CLI is required."; exit 1; }
  gh variable set "$name" --repo "$repo" --body "$value"
}

# ===== STAGES =====

TOTAL_STAGES=1

main() {
  stage "Replace this example"
  say "Edit the stages below the marker for the real manual flow."
}

main "$@"
