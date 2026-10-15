# Speak-as-user guard

Ask before an action that represents the user personally commenting, messaging, reviewing, or
changing tracker state. Show the exact text/action and wait for an explicit yes.

| Surface | Ask before |
|---|---|
| GitHub | comments/replies, resolve/unresolve, approve/request changes, creating issues, ad-hoc PR body edits |
| Linear | comments, status/assignee/label changes, issue creation |
| Slack | any post |
| Notion | page edits or comments |
| Other | email, chat, tracker, or customer-facing message |

Local paste-ready drafts need no approval. Reads need no approval.

Normal authorized delivery actions also need no extra confirmation once selected:

- `/draft-pr` creates draft PRs and routine companion links;
- `/commit`, `/push`, and `/commit-and-push` perform their named git actions;
- `/implement-pipeline` may invoke those selected mechanical stages;
- `/address-pr-comments --bugbot` may temporarily mark a draft ready and must restore it to draft.

Bugbot/comment handling never posts replies or resolves threads by default. Reply drafting remains
paste-only. Still never force-push, approve, merge, post bot-control commands, or add AI attribution.

State when relevant: `Speak-as-user: n/a (authorized delivery) | asked | confirmed | draft-only`.
