---
paths:
  - "worktrees/**/apaleo/src/**/*.cs"
  - "worktrees/**/apaleo/src/**/Infrastructure/Authorization/**/*"
  - "worktrees/**/identity/**/*"
---

# Authorization paths

- Account scope uses `IScopeContext` plus EF `AccountCode`.
- Property scope is enforced through OPA and `IEntityPropertyIdsRetriever`, not a global EF filter.
- Property-union/write-every rules belong in `[Scope]`, resource metadata, and OPA policy.
  Prefer default `core/decision` (write-every on request ∪ resource, read-some on reads). Omit
  `[OpaAuthorization]` / `decisionPath` when that axis is already correct.
- A named custom `*_decision` is required only when default would be the wrong axis (for example
  `some` stored property plus `every` request id). When several endpoints share that *non-default*
  allow/deny, expose one named `*_decision` and point every `[OpaAuthorization(decisionPath: ...)]`
  at it. Do not add per-endpoint `allow_*` / `decision_*` files that only rename a shared helper,
  and do not add a helper that only restates default write-every or an empty-list guard. House
  example: `core/calendar_event_action_decision`. Keep a file per endpoint only when the decision
  body actually differs.
- Every new action needs matching `endpoint_permissions`; new OPA keys may require Identity catalog work.
- Read `.claude/skills/references/identity.md` and `api-endpoint-patterns.md` before changing these paths.
