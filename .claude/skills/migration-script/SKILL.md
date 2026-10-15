---
name: migration-script
description: >-
  Generate the production EF SQL for a merged apaleo migration. Fast-forwards
  parked master, writes gitignored Migration.sql, and does not apply it.
disable-model-invocation: true
argument-hint: "[--from <MigrationId>] <issue|pr|branch>"
---

# Migration script

Read `$ROOT/.claude/skills/references/chat-output.md` and
`$ROOT/.claude/skills/references/db-migrations.md`. Run the script first and present its
outcome according to the chat-output reference. This is the file someone runs on production
when `## Production apply` says manual. The flattened SQL in the PR stays the review copy.

```bash
"$ROOT/.claude/skills/migration-script/migration-script.sh" "$@"
```

Short ids like `sl-125`, `hc3331`, or a PR URL are resolved by the script. Do not ask the
user to confirm a unique resolution.

If it exits `0`, stop. Do **not** read the SQL, grep, explore, or generate the script another
way. Report the file path, the from and through ids, the PR, and the production assumption
from the script output.

Exit `2` (`ASK:`) means no file was written, or a mismatched file was removed. State the exact
decision in plain language and stop. Do not fast-forward, switch the parked checkout, or run
`dotnet ef` yourself.

The script refuses an unmerged PR, local changes to tracked files on the parked checkout, a
checkout that is not on `master`, and a non-fast-forward update. Untracked files do not block
unless the fast-forward would overwrite them. It runs the production runbook command, with the
repo project flags this checkout needs:

```bash
dotnet ef migrations script <last-applied> --project src/Apaleo.Data/ --startup-project src/Apaleo.Data/ --output ./Migration.sql
```

It does not pass `-i` or an end migration. `<last-applied>` is the migration immediately before
the PR's first new migration, unless `--from` is set. The file then gets
`SET statement_timeout = 0;` as its first line, with no byte-order mark. It never applies SQL,
commits, or pushes. A second execution of that file fails; a failed run rolls back with the
transaction.
