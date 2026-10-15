# Fix policy for `/review` and `/address-pr-comments` (including Bugbot mode)

| Finding type | Action |
|---|---|
| Unambiguous defect, single correct fix | Fix, record |
| Missing null/error path, missing CT, missing test | Fix, record — **unless** a later ticket owns it (see below) |
| Missing capability / validation / handler / caller that a **later sliced ticket** owns | Do **not** fix — dispose `deferred — <HC-####\|plan Scope-Out>` with a citation |
| Violation of a specific `clean-code` rule | Fix, record, cite rule |
| New C# file with classic `namespace { }` (must be file-scoped per `$ROOT/AGENTS.md`) | Fix, record |
| Duplication with clear existing abstraction | Fix, record |
| Duplicate existence/load (`Exists` then `Get`; extra 404 when `ResourceMetadata` already 404s) | Fix, record |
| API wrapper / C# union-authz when OPA `[ResourceMetadata]` + request ids + `every` on concat can do it | Fix toward OPA; delete the wrapper; record — `api-endpoint-patterns.md` |
| PUT omit-to-keep field (not a full replace) | Fix to require the field or move to PATCH; stop and ask only if a plan `D#` chose omit-keep |
| Naming/readability/dead code where `clean-code` has a rule | Fix, record, cite rule |
| Style opinion with no backing rule | Do not raise |
| Display-string / RFC-label API enum converters (`"Concerts & Music"`, iCalendar `DAILY` on JSON) when the plan did not choose custom wire values | Fix to CLR member names (`references/api-enum-wire-values.md`), record — unless a `D#` explicitly chose custom strings |
| Changes agreed behaviour, public contract, or plan `D#` | Stop and ask — propose, do not apply |
| New dependency, migration, or schema change | Stop and ask |
| Two defensible fixes (design choice) | Stop and ask with options |

Intent boundary: repairing what the code got wrong is allowed; changing what it was supposed to do is the user's decision.

## Deferred scope (later ticket owns the gap)

Apaleo tickets are sliced into small sequential Linear issues, so Bugbot / CodeRabbit /
`claude[bot]` — and our own review — regularly report the **next** slice as a defect in this one.
Fixing it inflates the diff and breaks the deploy-ahead ordering the plan chose.

Dispose such a finding `deferred` when **all three** hold (`$ROOT/.claude/skills/references/deferred-scope.md`):

1. **Absent, not wrong** — something is missing, not wrong in code this change adds.
2. **Outside this ticket** — no AC claims it; plan `Scope — Out` / `Follow-ups` / a `D#` says later.
3. **Named owner** — a **real** Linear issue not in `Done`/`Canceled`, or an explicit plan line, that you can quote.

Evidence order: `ai-plans/<branch>/deferred-scope.md` → plan text → Linear MCP (`get_issue` → project
/ parent → `list_issues` siblings). Never invent a ticket id; an uncited deferral is invalid — judge
the finding normally instead.

**Never deferrable** (fix now, or stop and ask): tenancy / property scoping, money / tax, data loss,
migration safety, public `v1` / swagger break, secret exposure, or a crash on a path this ticket's
ACs claim. And a gap that is **reachable and wrong today** is a defect now, whatever a future ticket
promises — deferral requires the seam to be unreachable, flagged off, or additive-only.
