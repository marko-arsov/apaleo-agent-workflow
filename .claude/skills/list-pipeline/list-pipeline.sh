#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../pipeline/root.sh"
ROOT="$(resolve_root)"
cat <<'EOF'
Apaleo implementation pipeline
==============================

Plan
----
  /specify                 concise complete plan → manual /implement or full pipeline

Simple manual lane
------------------
  /specify HC-3333
  /implement HC-3333        focused tests + implementation in one session; no runner, review, or publish
                            isolated bugfix: reproduce, red regression check, fix, green — still this lane

Selected execution lane
-----------------------
  /implement-tests         test-only TDD red phase; required when tests change
  /implement               product code + internal verify/fix loop; always required
  /review <branch> [focus] fresh manual check-only review; ambiguity stops for confirmation
  /commit-and-push         optional deterministic publish
  /draft-pr                optional draft PR; requires commit-and-push
  /implement-pipeline      detached fresh stages + autonomous recovery + progress/verification

Progress and continuation
-------------------------
  /implement-pipeline HC-3333 --status
  /implement-pipeline HC-3333 --watch
  /implement-pipeline HC-3333 --answer '<answer>'   resume the exact paused stage session

  The shell-only watcher reports about every 90 seconds and uses no model tokens.

Manual after draft PR
---------------------
  /address-pr-comments                 human review comments
  /address-pr-comments --bugbot        Cursor Bugbot loop; always restore draft
  /address-pr-comments --draft-bugbot-replies
  /diagnose-ci                         read-only diagnosis, then confirmed fix
  /test-on-staging                     autonomous post-merge smoke; minimal human handoff

Utilities
---------
  /commit  /push  /checkout-branch  /sync-master  /migration-script  /open-rider
  /worktree-start  /worktree-list  /worktree-remove
  /e2e-stack-status  /e2e-stack-release  /e2e-test-overview
  /peer-pr-review  /peer-rfc-review  /wizard  /update-agent-skills
  /update-models  /add-rule  /prune-context  /pipeline-workflow  /list-pipeline

Manual recovery
---------------
  /test-and-fix            reusable procedure after PR-comment/manual changes; not a pipeline stage

Default AI routes
-----------------
  /update-models   confirmed machine/project model and effort defaults
  /specify         offline task evaluator; approved routes remain frozen

Audit
-----
  python3 "$ROOT/.claude/skills/pipeline/workflow_audit.py" --root "$ROOT"

Docs: $ROOT/.claude/skills/WORKFLOW.md
EOF
echo "ROOT=$ROOT"
