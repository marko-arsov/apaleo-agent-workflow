# Apaleo personal AI pipeline

For a small, established-pattern follow-up, use the manual lane:

```text
/specify HC-3333
/implement HC-3333
```

`/implement` writes/tests the focused change in one session and does not commit or push. Isolated
deterministic bugfixes stay in this lane: reproduce, prove a regression check red, fix, then green.
Use the full pipeline when the cause is unclear, several test layers are needed, the defect is
higher-risk, or you want detached stages, independent review, or automated publishing:

```text
implement-tests? → implement → review? → commit-and-push? → draft-pr?
```

`implement` is mandatory in the full lane and contains the complete verify/fix procedure;
`/test-and-fix` is not a regular stage. `implement-tests` is mandatory when tests change.
`/specify` runs the offline model evaluator, and the user confirms the routes. Review stays optional.
Any valid route can be used for every AI phase.
Implementation/publish safety gates fail closed. Pipeline review applies safe in-plan corrections
without blocking later stages; direct review is check-only. Review outcomes and diff budgets are
advisory. The runner never invents fallbacks beyond the confirmed plan.

The runner uses a cache-stable plan prefix, data context contracts, assertion-level red proof,
parsed named test output, AC traceability, diff budgets, and fast convention/secret scans. It
detaches safely in chat; `--status` and `--watch` use no model.

Use `/add-rule` for recurring conventions and `/prune-context` for proposal-only maintenance. After
a draft PR, use `/address-pr-comments`, `/diagnose-ci`, manual `/test-and-fix`, and
`/test-on-staging`. After a migration PR merges and production should apply it by hand,
`/migration-script` writes that SQL from parked master and does not run it. The staging skill takes one or several issues and PRs and runs every safe check available to its current host—including the Apaleo MCP,
browser, API, and read-only SQL—and leaves only sign-in, high-impact changes, or human judgment as a
short handoff.

On support rotation, `/support-rotation <Slack thread | Linear issue>` verifies the cloud support
agent's Outcome claim by claim, reproduces on staging when that decides it, and drafts the Slack,
Linear, and team-memory updates. It posts nothing without a yes.

See [WORKFLOW.md](WORKFLOW.md) and [pipeline/README.md](pipeline/README.md).
