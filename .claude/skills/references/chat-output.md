# Chat output for mechanical skills

Command output is evidence for the agent, not a user-facing transcript. After a mechanical skill
runs its prescribed script, present the result as readable Markdown:

- Lead with the outcome: completed, no changes, needs a decision, or failed.
- Summarize only decision-relevant facts (affected branch/repository, changed resource, and the
  next action). Use short bullets or a compact table when there are several items.
- Do not reproduce routine command, fetch, progress, or diagnostic output. Give the raw stdout
  only when the user asks for it or when a short fenced error excerpt is necessary to explain a
  failure.
- An `ASK:` result means no action was taken. State the exact safe decision in plain language and
  stop; do not infer approval from an ambiguous response.
- Do not perform extra exploration or verification beyond the skill's prescribed script.

This is a presentation rule only. It does not change exit-code handling, safety gates, or the
script's authority.
