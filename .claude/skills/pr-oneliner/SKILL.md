---
name: pr-oneliner
description: >-
  Prints a short pull-request line and the links for an Apaleo feature.
  No greeting. Use when sharing a branch with the team for review.
disable-model-invocation: true
argument-hint: "[issue id | branch | PR URL]"
---

# PR one-liner

Print one short line from the pull request title, then each link. The shape is:

```text
Price picked-up block nights from their stored GrossRate:
• github.com/apaleo/apaleo/pull/13315
• github.com/apaleo/development/pull/6544
```

Do not add a greeting, a "Hi", or a rewritten sentence. Do not print the product Outcome paragraph.

Read `$ROOT/.claude/skills/references/chat-output.md`. Run the script and present its
stdout as the message. Stop on ASK.

```bash
"$ROOT/.claude/skills/pr-oneliner/pr-oneliner.sh" "$@"
```

Accepts a full branch, `sl100`, `sl-100`, `hc3331`, or a PR URL. No issue, branch, or PR → follow
`$ROOT/.claude/skills/references/feature-argument.md` before running the script. Ask only when
that feature is not certain.
