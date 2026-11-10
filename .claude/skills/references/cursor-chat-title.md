# Cursor chat title

On Cursor, the chat that runs `/specify`, `/implement`, `/implement-tests`, `/review`, or
`/implement-pipeline` is renamed to the issue and the live status. Invoking one of those skills
is the user's request to rename this chat. Call `rename_chat` for this conversation. Do not rename
any other chat.

Skip this on a host that has no `rename_chat` tool. If the call fails, say so once and continue.
A title is never a reason to stop the task.

## Title

```text
SL-129 negative folio charges · implement
```

`<ISSUE-ID> <subject> · <status>`

- Issue id: the Linear identifier in commit style (`SL-129`, `HC-3331`). Use the id already
  resolved for this task. If only a branch is known, use the issue id inside that branch.
- Subject: two or three words from the issue title, in the title's order, that name the work.
  Drop a leading issue id and drop articles (`a`, `an`, `the`). Use four words only when three
  would not name the change. Do not invent a new phrase.
- If the Linear title is not loaded, use the first heading of `product.md` the same way. If
  neither is available, use the first two or three words of the branch slug after the issue id.
- Keep that subject for later renames in the same chat.
- One status, lowercase, from the list below. The separator is ` · ` (space, middle dot, space).
- No branch, model, repository, or route. Stay well under 200 characters; shorten the subject
  before the status.
- If this chat already has this exact title, do not call again until the status changes.

```text
SL-129 city tax · specify
SL-129 city tax · implement-tests
SL-129 deposit invoice rounding · waiting
```

## Status

| Status | When |
|---|---|
| `specify` | This chat is planning |
| `preflight` | The pipeline is starting, before the first selected stage |
| `implement-tests` | Test-only stage |
| `implement` | Product implementation |
| `review` | Review |
| `commit-and-push` | Commit and push stage |
| `draft-pr` | Draft pull request stage |
| `waiting` | This chat is blocked on the user |
| `failed` | Hard failure |
| `done` | This chat's lane finished |

`implement-tests` is the stage name. Do not shorten it to `implement-test`.

## Stage session

`/specify`, `/implement`, `/implement-tests`, and `/review` name only this session.

Set the title as soon as the issue id and subject are known. Update the subject once if the
first title had only the id.

| Skill | While working | When it stops |
|---|---|---|
| `/specify` | `specify` | Stays `specify`. The next skill in this chat replaces it. |
| `/implement` | `implement` | `waiting` when blocked on the user. `done` when plan verification finishes. |
| `/implement-tests` | `implement-tests` | `waiting` when blocked on the user. `done` when the stage report is complete. |
| `/review` | `review` | `waiting` when blocked on the user. `done` when the review report is complete. |

A later skill in the same chat replaces the status and keeps the subject. A pipeline stage
session does not retitle the orchestrator chat.

## Pipeline orchestrator

The chat that runs `/implement-pipeline`, including `--status`, `--watch`, and the default wait,
tracks the live stage.

- Set the title immediately: `preflight`, or the stage `--status` already shows.
- A watcher line with `stage_started` sets that stage.
- `input_required` sets `waiting`.
- `run_completed` sets `done`.
- `run_failed` sets `failed`.
- `stage_completed` does not change the title. The next `stage_started` does.
- A heartbeat (`watcher: worker alive`) does not change the title.

On Cursor, a foreground watcher can hide those lines until the process exits. Background that
watcher and subscribe to lines matching `stage_started:`, `input_required:`, `run_completed:`,
or `run_failed:`. Rename on each match, then keep waiting on the same run. Do not start a second
watcher and do not poll on a timer.

`--dry-run` and `--preflight-only` use `preflight` and do not move through stages. `--no-wait`
sets the stage that is starting, then returns. A later `--status` or `--watch` in this chat
updates the title.
