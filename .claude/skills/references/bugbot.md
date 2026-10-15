# Bugbot mode of `/address-pr-comments`

Bugbot handling is a mode of `/address-pr-comments`, not a separate skill or pipeline stage.

```text
/address-pr-comments <branch> --bugbot
/address-pr-comments <branch> --draft-bugbot-replies
```

Helper: `$ROOT/.claude/skills/address-pr-comments/bugbot.py`.

## Temporary ready loop

Draft PRs must temporarily become ready for Cursor Bugbot to comment:

1. Resolve open draft PRs for apaleo and companion development/identity worktrees.
2. Run `gh pr ready` for those PRs.
3. Wait and poll in shell without model use.
4. Judge each Bugbot thread against the plan, diff, and deferred-scope ledger.
5. Fix valid in-scope findings; record deferred or unfixable findings in `bugbot.md`.
6. If code changed, run `/commit-and-push`, wait for the new pass, and repeat, up to three rounds.
7. Always restore every PR that this mode changed from draft to ready with `gh pr ready --undo`,
   including on failure or interruption. Preserve PRs that were already ready before the run.

The ready/draft toggle is the only normal exception to keeping pipeline-created PRs draft. Never
approve or merge.

## Identifying Bugbot

Treat an inline/review comment as Bugbot only when the normalized author is `cursor`,
`cursor-bugbot`, `bugbot`, or its login/display name contains `bugbot`. CodeRabbit, Claude bot, and
humans remain ordinary comment handling.

## Default limits

| Control | Default |
|---|---:|
| Fix rounds | 3 |
| Initial wait | 90 seconds |
| Poll interval | 15 seconds |
| Polls after initial wait | 8 |

A timeout with zero Bugbot comments is a completed pass, not an infinite wait.

## Dispositions

| Disposition | Meaning |
|---|---|
| `fixed` | Valid defect fixed in this PR |
| `deferred` | Real gap owned by a verified later issue or explicit plan line |
| `unfixable` | Incorrect, already correct, irrelevant, or outside approved scope |
| `should-not-fix` | Contradicts a documented plan decision or project rule |
| `max-rounds` | Actionable work remains after the safety cap |

Never use deferred as a generic dismissal. The veto list in `deferred-scope.md` always applies.

## Ledger and replies

`ai-plans/<branch>/bugbot.md` is the living internal ledger. Use a stable fingerprint:

```text
<repo>|<path>|<normalized first significant comment line, max 120 chars>
```

Never post replies or resolve threads during the loop. The reply mode creates paste-ready text for
the user, and posting still requires speak-as-user approval. Never issue `@cursor` or another bot
control command.
