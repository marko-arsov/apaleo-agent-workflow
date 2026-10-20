---
paths:
  - "worktrees/**/apaleo/**/*.cs"
---

# Apaleo C# paths

- Match the nearest same-domain neighbor before adding a type; cite `path:line`.
- New C# files use file-scoped namespaces.
- Application C# uses `Check.NotNull` / `Check.NotEmpty`, not `ArgumentNullException.ThrowIfNull` or `throw new ArgumentNullException`.
- AutoWire / DI types that only capture dependencies use a primary constructor with `Check.NotNull` field initializers, not a classic constructor body. Extra constructor logic, `base(...)`, and multiple overloads may keep a classic constructor.
- Do not add XML `<summary>` comments that only restate the member name, especially on private or internal helpers.
- Application-service methods whose arguments are a resource id plus more than one additional primitive, and that have no body DTO, take a named command or query record. Keep HTTP `*Request` / query models at the controller; map there.
- When collecting ChangeTracker entries of a known entity type or interface, use `Entries<T>()` rather than untyped `Entries()` plus `is T`.
- Propagate `CancellationToken`; do not add `.Result` or `.Wait()` in application code.
- Money uses `decimal` plus `IsoCurrency` and established financial rounding.
- PUT is a full replacement; PATCH is partial.
- Do not introduce ConfigCat SDK usage in core services; use `config` plus `IFeatureSettingsProvider`.
- When selecting the time slice a night belongs to, use `TimeRange.IsPrimarilyWithin`. A slice that only clips the next night by the check-in/check-out offset does not qualify. Use `Overlaps` to test whether two ranges intersect.
- Apply migration, public-contract, and API-enum rules from the indexed references in `AGENTS.md`.
- When an aggregate already has a create or delete application service, call that service to persist it. Do not copy Insert/Delete, id generation, or entity mapping into a sibling service.
- Writes that must fail on an archived property go through `ArchivedPropertyReadOnlyInterceptor`, including delete. If the entity is not visible to it (for example `PropertyIds[]`), extend the interceptor instead of adding an application-layer archived check.
- A response creator maps one response shape; do not inject a second application service for a different list or get action. An in-memory index, scope, or grouping type is filled by the calling application service from already-loaded values; do not inject services so that type can load itself.
