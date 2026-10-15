# RFC review lens — senior product engineer

Use when running `/peer-rfc-review`. Challenge the design; do not copy-edit.

## What “good” looks like (Apaleo RFCs)

Align with `drafting-rfcs@apaleo` intent: high-level technical direction a reviewer can approve or argue with — placement, behaviour, edge cases that matter, API contract when the API changes. Not class/method breakdowns.

## Prioritize comments that change the design

Worth raising when the RFC (or its silence) risks:

1. **Wrong placement** — new service vs extend existing; cross-service coupling; reinventing a platform capability
2. **Authz / tenancy / property scope** — IDOR, role cardinality tricks, “derived from property count” permission rules that drift
3. **Lifecycle holes** — create/edit/delete/fork/split/override interactions that contradict each other or the worked example
4. **API contract traps** — same route meaning two things; unstable vs v1 choice without reason; breaking shapes; typos that imply wrong resources (`occurences` vs `occurrences`); path vs query-action inconsistency
5. **Data model vs behaviour mismatch** — stored fields that can’t support claimed behaviour; missing keys for claimed lookups
6. **Product/PRD misalignment** — design makes a PRD requirement inert, or invents scope the PRD didn’t ask for
7. **Operational risk** — unbounded queries, background jobs vs live cost, feature-flag/rollout gaps, supportability
8. **Open questions that should block approval** — dependencies marked “to confirm” that are load-bearing

## Deprioritize / skip

- Prose polish, emoji section headers, tone
- Restating the RFC back as praise without a decision
- Implementation micro-advice (class names, DI, file layout) unless it invalidates the direction
- Hypothetical scale problems the RFC already bounds with a clear escape hatch — unless the bound is missing

## Comment style (Notion paste)

- One concern per comment
- Lead with the **decision or risk**, then the concrete RFC claim it conflicts with
- Prefer a **question** when the author may have context; prefer a **recommendation** when the trap is clear
- Short enough to paste under a Notion heading; no “as an AI”
