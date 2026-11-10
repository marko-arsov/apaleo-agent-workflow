# Using the Apaleo implementation pipeline

## 1. Specify the contract

Run `/specify HC-3333`. It researches before writing, asks until important choices are settled,
and produces the immutable five-file plan set. The final confirmation includes:

- the outcome, scope, risk, and diff budget;
- every acceptance criterion mapped to a named test and exact parseable command;
- selected stages and exact provider/model routes;
- explicit fallback routes, if any.

Inspect `ai-plans/<branch>/implementation.md`; `pipeline.json` is the runner-enforced form. A plan
revision may update the complete set in place or create a complete `vN/`; the runner archives and
rebinds state automatically.

## 2. Preview and run

For a small follow-up, use the simple manual lane instead of the runner:

```text
/specify HC-3333
/implement HC-3333
```

`/implement` creates/updates the focused tests and product code in one session, runs its named
checks, and does not commit or push. For an isolated bugfix it reproduces the failure, adds a
regression check that fails for the original defect, then fixes and reruns it green. Use the full
pipeline when the cause is unclear, several test layers are needed, the defect is higher-risk, or
you need detached recovery, independent review, or automated publishing:

```text
/implement-pipeline HC-3333 --dry-run
/implement-pipeline HC-3333 --preflight-only
/implement-pipeline HC-3333
```

The fixed order is:

```text
implement-tests? → implement → review? → commit-and-push? → draft-pr?
```

In the full pipeline, `implement-tests` uses Cursor Claude Sonnet 5.5 high by default and Cursor Opus 5.5 for
four or more planned test files or a substantial expected diff, with matching Claude Code fallback;
implementation uses Cursor Grok 4.7 high. `/specify` offers review by estimate (1 skip; 2 Cursor Sonnet;
3 Cursor Sol; 5 Cursor Opus) with editable ordered fallbacks. The user confirms the actual selection and
route. The evaluator suggests a different lab for test authoring and review. Any confirmed provider/model remains valid, and an explicit route wins.
`implement` then loads the complete `/test-and-fix`
procedure in its own session, runs every named test command, parses output, and writes traceability
evidence. `/test-and-fix` is no longer a regular pipeline stage.

The runner may detach while a model-free watcher reports events:

```text
/implement-pipeline HC-3333 --status
/implement-pipeline HC-3333 --watch
/implement-pipeline HC-3333 --answer 'answer to the genuine paused-stage question'
```

On Cursor, the chat running `/specify`, `/implement`, or `/implement-pipeline` is renamed to the
issue id, two or three words from the issue title, and the live status. The pipeline chat updates
as the stage changes (`specify`, `implement-tests`, `implement`, `review`, `waiting`, `done`).
Details: `references/cursor-chat-title.md`.

## 3. What is mechanically gated

- Test authoring can write only manifest `test_paths` and must prove assertion-level red; compile,
  fixture, import, and environment failures do not count.
- Implementation can write only planned product/test paths. It cannot defer all tests to an
  optional later stage.
- Named command output—not a report's claim—is parsed for success.
- Every acceptance criterion must map to a named test that exists, ran, and passed.
- Diff budgets are advisory; the default planning threshold is 4,000 changed lines.
- Plan revisions are archived and rebound automatically.
- Review evidence and findings are advisory; a missing report never stalls delivery.
- Diff-scoped convention and secret scans run before publish and on direct commit. Semgrep/gitleaks
  augment deterministic local checks when installed.
- Mutation testing is never default; only an explicitly confirmed authorization/billing plan may
  run `dotnet stryker --since:main`.

## 4. Context and trust boundaries

Each stage has read/deny/write declarations in `pipeline.json`. Prompts share one byte-stable prefix
(`AGENTS.md` + current plan revision) and append dynamic stage context at the end, improving cache reuse
without sharing sessions.

Ticket text, PR comments, CI logs, and foreign diffs are stripped of hidden/control characters and
HTML comments, wrapped as untrusted data, and flagged when they contain injection-shaped commands.
This does not sandbox the provider. The local audit records the remaining credential, broad-tool,
and unrestricted-egress gap:

```text
python3 .claude/skills/pipeline/workflow_audit.py --root "$ROOT"
```

## 5. Capture recurring mistakes without bloating AGENTS.md

Use `/add-rule <plain-English rule> [violating example]`. The router derives the tier:

- Tier 1: always-wrong mechanical violation, blocking;
- Tier 2: mechanical signal with legitimate exceptions, advisory;
- Tier 3: not diff-checkable, scoped prose only.

The operator cannot force Tier 3. A Tier-3 rule's second recorded human-review violation must
escalate mechanically. `/address-pr-comments` proposes exact maintenance diffs and increments an
existing rule once per human comment URL; `/prune-context` only proposes deletions/escalations.

## 6. After a draft PR

Use `/address-pr-comments`, `/diagnose-ci`, manual `/test-and-fix`, then `/commit-and-push` as
needed. `/test-on-staging` remains post-merge. Nothing posts, resolves, approves, requests review,
or merges as you without explicit approval.

## 7. Support rotation

`/support-rotation` takes a `#product-inquiries` thread or the cloud agent's Linear issue. It does a
short blind pass, verifies the cloud Outcome as a claim ledger, then adds staging reproduction,
flag state, and history. A defect that needs code goes to `/specify` like any bugfix.

See [WORKFLOW.md](WORKFLOW.md) for policy and [pipeline/README.md](pipeline/README.md) for runner
flags.
