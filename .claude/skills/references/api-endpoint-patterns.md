# API endpoint, controller, and property-authorization patterns

Use this reference whenever a ticket adds or changes an HTTP endpoint, controller action, request
contract, or endpoint-facing service. It turns “existing patterns first” into a concrete comparison
across the whole resource, not just the one action being edited.

## Required operation survey

Before choosing a design, make a small operation matrix for the affected resource. Include every
existing or proposed collection and by-id action that matters: `GET`, `POST`, `PUT`, `PATCH`, and
`DELETE`.

| Concern | Record for each relevant action |
|---|---|
| HTTP contract | Verb, route, response and error status, committed Swagger impact |
| Controller | Action name, attributes, route binding, response mapping |
| Request shape | Type name, whether it is body/query/route bound, validation and mapping |
| Authorization | `[Scope]`, OPA decision/filter/retriever, `endpoint_permissions` entry, property checks |
| Application path | Called service, method, DTO, validator, persistence/readback path |
| Tests | Existing API, unit, and E2E/authz coverage |

Start with the same resource, then inspect the nearest same-verb neighbor in another module when
the resource has no equivalent. Cite each source as `repo/path:line`. The matrix is evidence, not a
reason to make every action look identical: create, full replacement, partial update, list, and
by-id read have different information and security needs.

## HTTP verb semantics (always)

Follow the HTTP meaning of the verb. Do not add convenience fields or omit-paths that fight it.

| Verb | Contract |
|---|---|
| **PUT** | Full replace. Every writable field the replace/create body owns is **required**. Omitting a field means clear/default (for example omit `recurrence` → one-off), **not** “keep the stored value.” Do not make `propertyIds` (or similar associations) optional on PUT because editing without restating them is nicer — that is **PATCH** (or a later ticket). |
| **PATCH** | Partial update. Omitted fields stay. |
| **POST** | Create. No persisted resource yet; authorize submitted ids only. |
| **GET** by-id | Read one. Existence → 404 via `[ResourceMetadata]` / `CheckResourceExistFilter`, not a second `Exists` then `Get`. |
| **GET** list | Filter/page. Empty result follows the neighbor (often 204), not 404. |
| **DELETE** | Remove the resource. |

Davide on HC-3331: PUT that overrides everything except one optional association is not PUT. Same class of mistake: `ExistsAsync` when `GetById` already 404s.

## Controller and naming decisions

- Treat `Model`, `Request`, and `Filter` as local contract vocabulary, not as aliases for
  `[FromBody]`, `[FromQuery]`, or another binder. Copy the nearest sibling's terminology and record
  the mapping in the operation matrix.
- Name the endpoint-facing method and application method for their actual semantics. In particular,
  a full `PUT` replacement, a `PATCH`, and an update convenience method are not interchangeable.
  Follow the nearest equivalent instead of creating a new naming rule for one resource.
- Controllers call the application service directly. **Do not** add an API wrapper whose job is
  property-union authorization, existence-before-get, or remapping OPA denials to 404/422.
  Put that in `[Scope]`, `endpoint_permissions`, `[ResourceMetadata]` (persisted ids),
  `IPropertyLevelRequestModel` (submitted ids), and default `core/decision` (write-`every` on
  concat `property_ids`) when write must cover old ∪ new. Add a named OPA decision only when
  that axis is wrong. HC-3331 deleted `UpdateCalendarEventService`
  for this reason.
- A thin API service is only justified for genuine API-boundary work that is **not** authorization
  (for example mapping models). It must be more than a forwarding layer; cite the matching pattern.
- Keep one clear owner for shared domain invariants. Do not leave similar create/replace flows with
  duplicated resolution, archived-property, or validation code merely because their controller
  actions have different verbs.

## Property-level authorization

Property scoping is an IDOR boundary. Assess authorization for the action family as a whole before
copying a POST or GET attribute onto another verb.

**Prefer the Scope / OPA layer.** Almost every property-access invariant belongs there, not in a
new C# orchestrator.

1. Register every new HTTP action in the matching OPA `endpoint_permissions` `data.json` (list, by-id,
   write). Use the sibling resource's permission key convention.
2. Preserve the resource's `[Scope]` unless the matrix cites a reason to change it. Do **not** add a
   parallel service-level allow/deny that duplicates OPA.
3. Use `IPropertyLevelRequestModel` when the OPA request retriever must see body/query property ids.
   Use `[ResourceMetadata]` / `IEntityPropertyIdsRetriever` when the decision needs **persisted** ids.
   PUT/PATCH that can change associations: both, so `policy_common.property_ids` is request ∪ resource.
   Default write-`every` already loops that union; default read uses `some`. Omit
   `[OpaAuthorization]` / `decisionPath` when that axis is correct. A named custom decision is
   required only when default would be wrong: write-every too strong (need `some` stored + `every`
   request), read-some too weak, per-item bulk, or extra path restrictions. Do not add a named
   decision that restates default write-every or only adds an empty-list guard.
4. OPA deny → **403**. Missing resource → **404** (`CheckResourceExistFilter`). Empty/invalid body →
   **422** (FluentValidation). Do not invent an API wrapper to turn union-access denials into 404/422
   “because GET returns 404.”
5. A named C# authorization operation is a last resort, only when OPA cannot express the invariant
   (cite why). It is not the default for persisted ∪ submitted checks.
6. Document outcomes before coding: absent, no overlap, partial overlap, invalid submitted codes.
   Prefer the status mapping above. Do not leak inaccessible ids in messages.

## Reuse and validation

- Search both the resource's create and replace/update paths for repeated invariants before adding a
  helper. Share a helper or focused service when the same domain rule has the same owner and inputs;
  otherwise keep the code local. Do not introduce generic controller/service abstractions for a
  single call site.
- Record the reuse audit: searched symbols, candidate found, chosen reuse or a concise reason it
  does not fit. This includes validators, DTOs, property resolution, archived checks, response
  creators, and endpoint-facing orchestration.
- Test the operation matrix's changed row plus its security edges: all properties accessible, no
  accessible properties, partial access, persisted-only associations, submitted-only associations,
  and property removals/replacements where applicable. Assert the intended status and safe message,
  not just that an exception occurred.

