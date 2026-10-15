# Pull requests and automated reviewers

- `gh` must be authenticated and may run from apaleo, development, or identity worktrees.
- `/draft-pr` creates draft PRs using the repository template and writes `pr.md`.
- `/implement-pipeline` ends at the draft PR when that stage is selected. It does not wait for or
  act on later reviewers.
- `/address-pr-comments` handles human, CodeRabbit, Claude bot, and Bugbot findings. Use
  `--bugbot` for the temporary ready/wait/fix/restore-draft loop and
  `--draft-bugbot-replies` for paste-ready unfixable replies.
- Later-ticket gaps are not automatically defects. Use `deferred-scope.md` only with a verified
  live issue or explicit plan line. Never defer security/tenancy, money/tax, data loss, migration
  safety, public contracts, secrets, or a crash on a claimed acceptance path.
- Development CI may force-push an automatic formatting commit. Treat local/remote divergence as
  expected evidence; never force-push.
- Never approve, merge, resolve review threads, post bot-control commands, or comment as the user
  without explicit approval.
- `/diagnose-ci` and `/test-on-staging` are manual post-PR/post-merge flows.
