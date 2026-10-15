# Deferred scope — "that hole is a later ticket"

Apaleo work is sliced into small sequential issues (`HC-3327` entity → `HC-3328` occurrence
entity → `HC-3329` endpoints → …). Automated reviewers — **Cursor Bugbot**, CodeRabbit,
`claude[bot]`, and our own `/review` — routinely flag the *next slice* as a bug in this one:
"nothing expands the recurrence", "this value is never validated", "this seam has no caller".

Those are **not defects**. Fixing them pulls a future ticket into this PR, inflates the diff,
and breaks the deploy-ahead ordering the plan chose on purpose.

This file defines the **`deferred`** verdict: *real gap, real owner, not this ticket.*

Used by `/review` and `/address-pr-comments`, including its Bugbot and reply-drafting modes.

---

## 1. The three-question test

A finding is `deferred` only when **all three** are yes:

1. **Absent, not wrong.** The finding is about something *missing* (a capability, validation,
   handler, caller, expansion step) — not about incorrect logic, naming, or structure in code
   this PR actually adds.
2. **Outside this ticket.** No acceptance criterion in `product.md` / `implementation.md`
   claims it, and the plan's `Scope — Out`, `Open Questions / Follow-ups`, or a `D#` decision
   says it is later (or the Linear slicing plainly shows it).
3. **Named owner.** A **real, live Linear issue** (state not `Done` / `Canceled`) or an
   **explicit plan line** covers it. You must be able to quote the identifier or the line.

Any "no" → judge the finding normally (fix it, or call it invalid/out-of-scope with a reason).

**Never invent a ticket id.** If you cannot cite one that exists, the verdict is not `deferred`.
"Presumably a follow-up will handle this" is a fabrication, not evidence.

## 2. Veto list — never deferrable

Even when all three questions pass, these are **fix now or require user input** (`PIPELINE_INPUT_REQUIRED`),
because they are wrong in the code being merged, not merely incomplete:

- **Tenancy / property scoping** — missing `IScopeContext` filter or OPA property check (IDOR).
- **Identity catalog when this ticket's ACs include property-user authz E2E** — OPA keys without `Constants.cs` / `permission_mappings` (`references/identity.md`). Do **not** defer that to a later "scopes" ticket unless a **live** Linear issue owns it and the ACs here do not claim role authz.
- **Money / tax** — wrong type, rounding, or currency handling.
- **Data loss or corruption** — destructive migration, unguarded delete, lost writes.
- **Migration safety** — drop/rename ordering, deploy-ahead violation (`db-migrations.md`).
- **Public contract break** — `v1` / committed swagger incompatibility.
- **Secret exposure** — credentials or connection strings in code, logs, or artifacts.
- **A crash or wrong result on a path this ticket's ACs claim to support.**

## 3. The seam must be safe while it waits

A deferred gap is acceptable only if the incomplete path **cannot hurt production before the
follow-up lands**: unreachable (no route, no caller, entity not yet consumed), gated off by a
feature flag, or additive-only schema deployed ahead of its use.

If the gap is **reachable and wrong today**, it is a defect in this PR regardless of what a
future issue promises. Fix it, or hard-stop.

## 4. Evidence, cheapest first

1. **`ai-plans/<branch>/deferred-scope.md`** — the cached map (§5). Written by `/specify`
   (which already loads Linear) or refreshed by the first judging stage that needs it.
2. **Plan text** — `implementation.md` / `product.md` `Scope — Out`, `Open Questions /
   Follow-ups`, `D#` decisions, `prompt.md`. Free; no MCP.
3. **Linear** (only when 1 and 2 do not settle it) — via Linear MCP:
   - `get_issue` on this ticket → its **project**, **parent**, description follow-up mentions.
   - `list_issues` for that project / the parent's sub-issues → siblings that own the gap.
   - Check each candidate's **state**: `Done` / `Canceled` means it is *not* a live owner —
     if the work was supposedly done and the gap is still there, that is a finding, not a deferral.

**Confirm a cached Linear citation.** The `State` column in `deferred-scope.md` is a snapshot from
when the map was written. Before relying on a **Linear-backed** row, spend one `get_issue` call on the
cited id to confirm it still exists and is not `Done` / `Canceled`; refresh the row if it moved. Skip
this only when the citation is a **plan line** (plan text does not go stale) or when the map was
refreshed in this same session. A cancelled owner means the gap is **nobody's** — judge it normally.

**Linear MCP unavailable:** use plan evidence only, and say so in the artifact and the ledger
(`evidence: plan-only, Linear MCP unavailable`). Do not guess ticket numbers to fill the gap.

Reads only. Never comment on, create, or re-state a Linear issue from these stages
(`speak-as-user.md`).

## 5. Cached map — `ai-plans/<branch>/deferred-scope.md`

Write it once per branch; refresh when it is missing or plainly stale. Later rounds and
stages read it instead of re-querying Linear.

```markdown
# Deferred scope — <branch>

- Ticket: HC-3328 · Project: <name> (<url or id>) · Parent: <HC-#### or none>
- Linear MCP: available | unavailable (plan-only)
- Refreshed: <ISO-8601 UTC>

| Intentionally missing here | Owned by | State | Evidence |
|---|---|---|---|
| RRULE → occurrence expansion | HC-3330 Expand occurrences on read | Todo | Linear sibling in project |
| Pattern bound validation | plan `Scope — Out` §3 | — | implementation.md line "Out: bound validation" |
| Public endpoint exposure | HC-3329 Add POST /events | In Progress | Linear sibling |

## Not deferrable (veto list applies)
- Property scoping on the new endpoint — must be correct in this PR.
```

An empty table is a valid result: "nothing is deferred here" — record it so the next stage
does not re-query.

A finding the map does not cover is simply **not settled by the map** — fall through to the plan text
and then Linear (§4). A stale map therefore costs a lookup, never a wrong verdict.

## 6. Recording the verdict

Wherever the stage keeps its judgment ledger, the disposition is:

```text
deferred — <HC-####> <short title> (<state>)      # Linear-backed
deferred — plan Scope-Out: "<quoted line>"        # plan-backed
```

Requirements:

- The **quote or id must be real** and checkable by the human later.
- Say what the follow-up owns in one line — enough for a reply without re-reading the thread.
- `deferred` is a **separate disposition** from `unfixable` (wrong / N/A) and
  `should-not-fix` (contradicts the plan or clean-code). Do not collapse them: the human
  reply differs — "tracked in HC-3330" versus "the current code is correct".
- Never GitHub-resolve or reply from a judging stage. `/address-pr-comments
  --draft-bugbot-replies` writes the paste-ready text; the human posts it.

## 7. Anti-abuse

`deferred` is the easiest verdict to hide a real bug behind. Guards:

- Cite or drop it (§1.3). No id, no plan line → not deferred.
- A `Done` / `Canceled` owner is **not** an owner (§4.3).
- The veto list (§2) wins over any citation.
- Reachable-and-wrong wins over any promise (§3).
- Count them: if a majority of a PR's findings come back `deferred`, the slice was probably
  mis-scoped — say that in the stage summary rather than quietly deferring everything.
