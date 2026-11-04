---
name: draft-pr
description: Mechanical wrapper. Runs the sibling script and presents its outcome clearly. Stops on ASK.
disable-model-invocation: true
---

# Draft PR

Read `$ROOT/.claude/skills/references/chat-output.md`. Run the script, present its outcome
according to that reference, and stop.

```bash
"$ROOT/.claude/skills/draft-pr/draft-pr.sh" "$@"
```

Do **not** read repo files, grep, explore, restate rules, or "verify" another way.

The script opens **draft** PRs (`gh pr create --draft`) and then `gh pr edit` for companion links.
Every new body uses the established PR template: **Issue ticket number and links**, **Changes**, and
**Checklist**. Its **Summary** is the product plan's `## Observable outcome`, `## Outcome`, or
legacy `## Product Summary`. Its **Details** are the in-scope items under `## Scope` (`### In`,
`**In:**`, or `In:`). When a plan has no in-scope list, the acceptance-criterion bullets are used. Never use `git log` as PR copy: stacked-branch history includes unrelated
ancestor work. When `migration.sql` exists, the body includes that flattened script. When the plan
has `## Production apply`, that recommendation is included above the script.
On a re-run, it refreshes only the generated **Changes** section of an existing draft, retaining
the checklist state and any notes appended after it. When `test-judge.md` exists in the plan
directory, that note is appended after the checklist. A local restore that failed is not a passed
verification.

- **Title:** the imperative summary from the prompt or product heading. Process suffixes such as
  `Prompt and research`, `Prompt & decisions`, and `Decisions and research` are ignored. If both
  headings are only a process label, the Linear issue title in the prompt is used. An apaleo plan
  that states `` `[DB-MIGRATION] <issue> <summary>` `` for this PR uses that full title. A development
  PR that still contains payment E2E uses `Cover … in E2E`.

- **Related to:** Linear issue URL when known.
- **E2E tests:** `this PR` when that repo's diff touches `e2e/` (core, identity, and other migrated services). `N/A — no e2e changes` when it does not. A development PR is the E2E link only when its diff touches `src/tests` (payment). Agent-skills and angular-api-proxy stay `N/A — no e2e changes`.

No issue, branch, or PR → follow `$ROOT/.claude/skills/references/feature-argument.md` before
running the script. Ask only when that feature is not certain.

Ambiguity (dirty worktree, diverged branch, lock held by another branch) → stop and ask. Do not investigate.

## Automated use (`/implement-pipeline`)

When selected, this stage is **required**. The runner/script should create draft PRs without speak-as-user
confirmation. Stop only for real mechanical blockers: missing branch/push, `gh` failure, ambiguous
repos, or unsafe non-draft/outward-facing action. Fix the blocker externally, then rerun; keep PRs
draft.
