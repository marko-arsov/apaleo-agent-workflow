# Existing patterns first

The **highest-priority rule** while planning and implementing in this pipeline:

**Match the repos as they already are.** A nearby working example beats a cleaner invented design.

New folders, helpers, base classes, or “more SOLID” shapes lose to the local neighbor — controller, service, entity, validator, mapping, Jest spec — unless a cited `D#` explains why that neighbor cannot be followed.

## What this means

1. **Find the neighbor before designing.** Same domain, same verb (create / update / list / cancel), same layer. Cite `repo/path:line`.
2. **Copy the local shape.** Naming, file placement, `[AutoWire]`, error types (`MessageItemCollection`), test fixtures, E2E helpers — do what that neighbor does. `clean-code` is the review bar *for that local pattern*, not a license to redesign the module.
3. **Reuse before create.** Search for an existing type/helper/spec pattern. Record the search. A new type needs one line: why the existing one does not fit.
4. **Standards that already live here beat invented ones.** Nearest `AGENTS.md` / `CLAUDE.md`, committed swagger, existing E2E helpers, Identity catalog style. Do not introduce a parallel convention.
5. **Scope stays small.** Following a pattern is not a license to refactor the neighbor. Touch only what the ticket needs.

For API work, the neighbor is the resource's **action family**, not just the requested verb. Read
`references/api-endpoint-patterns.md`: survey the sibling `GET`/`POST`/`PUT`/`PATCH`/`DELETE`
actions, then compare the nearest same-verb resource. This is where controller/service layering,
`Model` versus `Request` terminology, OPA/property authorization, and reuse decisions are made.

## Where it is required

| Stage | Must show |
|---|---|
| `/specify` | Cited neighbor(s) in Approach / blast radius, plus a mandatory reuse audit. For endpoint work, include the action-family matrix and each authorization/error/property decision. Chosen approach is “same as \<cited\>” unless a `D#` explains why not. Steps name existing types, not invented ones. |
| `/implement` | Search + cite before adding a file or type. Re-check the action matrix before deviating from it. If the plan invents a shape the repo does not have → stop and ask. |
| `/review` | Repository-wide semantic searches and strongest matching paths for every added responsibility; reuse or extract at the smallest established seam when behaviour remains unchanged. |

## Anti-patterns

- Greenfield layering inside a brownfield module
- New base classes or generic helpers “for reuse later”
- API wrapper whose only job is property-union authorization or Exists-then-Get (`api-endpoint-patterns.md`)
- Rewriting a neighbor so it matches *your* new code
- Display-string API enums, classic `namespace { }` on new files, raw ConfigCat SDK — already banned in `$ROOT/AGENTS.md`

If Graphify is available in apaleo, use `query` / `path` / `explain` to find the neighbor (`references/graphify.md`), then open that file. Do not skip the cite.
