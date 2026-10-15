---
name: diagnose-ci
description: >-
  Manually diagnoses failing CI for an existing Apaleo draft PR using read-only
  GitHub and latest-branch Jenkins evidence, proposes a fix, and waits for user
  confirmation before edits. Not an implementation-pipeline stage.
disable-model-invocation: true
model: grok-4.7-high
effort: high
argument-hint: "[branch-name | PR url]"
---

# Diagnose CI

This is a manual after-PR flow. It is never selected by `/implement-pipeline`.

## First turn: diagnose only

1. Resolve the target branch and feature worktrees; parked mains stay on `master`.
2. Read open PRs and `gh pr checks` for apaleo, development, identity, agent-skills, and angular-api-proxy worktrees that exist.
3. If all checks are green, write `ci-report-<n>.md`, report green, and stop without edits.
4. For a red Jenkins check, fetch only that branch job's latest completed build metadata and console
   via the read-only procedure in `references/jenkins-fetch.md`.
5. Classify the failure and write a concrete proposal with log and `file:line` evidence.
6. Write `ai-plans/<branch>/ci-report-<n>.md`, show the proposal, and wait for explicit approval.

Never implement, commit, or push on the diagnosis turn.

## Jenkins limits

Allowed: read-only GET of the exact branch job's `lastCompletedBuild/api/json` and
`lastCompletedBuild/consoleText` (or `lastBuild` when the user asks for live status). Confirm the
returned job URL/display name contains the target branch before reading the console.

Never trigger, replay, rebuild, cancel, delete, reconfigure, inspect unrelated jobs, or print
credentials. If authentication is missing, ask the user to fix `JENKINS_URL`, `JENKINS_USER`, and
`JENKINS_TOKEN`, or paste the failed-stage log.

Save large consoles to `$LOG_DIR/logs/jenkins-<job>.log` and summarize with:

```bash
python3 "$ROOT/.claude/skills/pipeline/summarize_output.py" \
  --mode jenkins "$LOG_DIR/logs/jenkins-<job>.log"
```

## Classification

| Class | Response |
|---|---|
| Product/test failure | propose the smallest in-scope fix and focused verification |
| Formatting/expected CI bot update | explain; usually no code change |
| Infrastructure/flaky/shared environment | report evidence; do not alter product code or tests |
| Missing companion branch/swagger/migration dependency | propose the exact workflow correction |
| Ambiguous | ask numbered questions |

Never weaken, skip, delete, or quarantine a test.

## After the user approves

Implement only the approved fix, run the narrowest useful local validation, update the same CI
report and `progress.md`, then follow `/commit-and-push`. Do not create a second PR or trigger CI.

## Output

Diagnosis turn:

```text
Resolved: <branch>
PRs: <urls>
Checks: <summary>
Jenkins: build #<n> <result> <url> | skipped | unreachable
Report: ai-plans/<branch>/ci-report-<n>.md
Classification: <class>
Proposal: <bullets>
Awaiting confirmation to implement. No code changes made.
```

Confirmed-fix turn:

```text
Implemented: <bullets>
Checks run: <command → result>
Report: <path> updated
Commit/push: <result>
Next: wait for CI or run /diagnose-ci again if red
```
