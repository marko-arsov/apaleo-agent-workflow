# Feature flags (ConfigCat / config service)

Apaleo **does not** embed the ConfigCat SDK in the monolith. Flags live in the **`config` service** (Features API), which is backed by **ConfigCat**. Core reads flags over HTTP; E2E toggles them via the same API.

Agents **must** read this when a change introduces, depends on, or removes a rollout flag — and **must give the user concrete setup instructions** (ConfigCat + local `config` + how to verify) so the feature works as intended.

## Do not confuse two systems

| System | What it is | How to change |
|--------|------------|---------------|
| **ConfigCat / Features API** (`config` service) | Rollout / gating flags (`hurdleRatesEnabled`, …) | ConfigCat dashboard (shared envs) **or** `PUT /features/v0-nsfw/settings` (local/E2E) |
| **Property FeatureSettings** (core DB + settings API) | Per-property product settings (invoice patterns, custom subaccounts, …) | Core settings / JSON Patch — **not** ConfigCat |

If unsure which one the ticket means, ask. Helpers:

- ConfigCat-style: `apaleo/e2e/tests/helpers/features.ts`
- Property settings: `apaleo/e2e/tests/helpers/settings/features.ts`

## Architecture

```text
ConfigCat dashboard / CDN
        │
        ▼
 config service  (apaleo-config, local :50100)
        │  GET/PUT /features/v0-nsfw/settings
        ▼
 Apaleo.Core  IFeatureSettingsProvider
   ← CachedFeatureSettingsProvider
   ← FeatureSettingsProvider  (HTTP via Apaleo.NetStandard.Config)
        │
        ▼
 Domain services / validators / filters
```

- Endpoint config: `configApiEndpoint` in `Apaleo.Api` appsettings (Development → `http://config.apaleo.local:50100`).
- Fail-closed: if Config API fails or body is not a bool → **log error → treat as `false`**.
- Optional targeting: `propertyId`, `countryCode` (resolution order owned by `config`).
- Request-scoped cache via `CachedFeatureSettingsProvider` (key = feature + property + country).

Key code:

| Piece | Path |
|-------|------|
| Interface | `apaleo/src/Apaleo.Core/Interfaces/IFeatureSettingsProvider.cs` |
| HTTP reader | `apaleo/src/Apaleo.Core/Services/FeatureSettingsProvider.cs` |
| Cache | `apaleo/src/Apaleo.Core/Services/CachedFeatureSettingsProvider.cs` |
| Flag constants | `apaleo/src/Apaleo.Core/Common/Constants.cs` → `Constants.FeatureFlags` |
| Client factory | `apaleo/src/Apaleo.Core/ClientFactories/FeatureConfigApiFactory.cs` |
| E2E helpers | `apaleo/e2e/tests/helpers/features.ts` |
| Property FeatureSettings helpers | `apaleo/e2e/tests/helpers/settings/features.ts` |
| E2E specs | `apaleo/e2e/tests/settings/` |
| Cleanup skills | `apaleo/.agents/skills/remove-feature-flag/`, `development/.agents/skills/remove-feature-flag/` |
| Code refs scan | `apaleo/.github/workflows/configCatScan.yml` (master) |

## Naming

- **API / ConfigCat key:** camelCase string, often `…Enabled` / `is…Enabled` (e.g. `hurdleRatesEnabled`).
- **C# constant:** PascalCase under `Constants.FeatureFlags`, value **identical** to the ConfigCat key.
- Keep the same string in ConfigCat, C#, and E2E helpers. Renaming breaks scan + targeting.

## Agent rules when adding a flag

1. **Ask early** in `/specify`: is this gated? global vs property vs country? default when unset (almost always off / fail-closed)?
2. **Create the flag in ConfigCat before relying on it in shared envs** — own Linear/setup issue if needed. Agent cannot create ConfigCat flags via the monolith; **instruct the user** (see checklist below).
3. Add `public const string …` to `Constants.FeatureFlags`.
4. Gate with `IFeatureSettingsProvider.GetFeatureFlagAsync(Constants.FeatureFlags.X, propertyId?, countryCode?)`. Prefer validators / `BusinessValidationException` for new public APIs when disabled.
5. Unit tests: Moq the provider — never call Config API from unit tests.
6. E2E: add a named helper in `apaleo/e2e/tests/helpers/features.ts`; `beforeAll` enable / `afterAll` restore. Use property/country args when targeting requires them.
7. Do **not** add per-flag keys to apaleo `appsettings` or invent `FEATURE_X` env vars in core.
8. Plan a **cleanup** issue (`featureFlagCleanup` / `remove-feature-flag` skills) after full rollout.
9. In the plan and in chat, always include a **Setup for humans** section (template below).

## Setup for humans (agent must output this when flags are involved)

Copy and fill. Be specific about flag key, targeting, and which env.

### A. ConfigCat (staging / production / shared)

1. Open the Apaleo **ConfigCat** project used by the `config` service (team ConfigCat org — SDK/init lives in the **config** repo, not apaleo).
2. Create a **boolean** flag with key exactly: `` `<flagKey>` `` (must match `Constants.FeatureFlags` / E2E).
3. Set defaults: usually **Off** globally; add targeting rules for property/country/percentage only if product asked for them.
4. Confirm the environment the `config` deployment uses (Staging vs Production) matches where you will test.
5. After merge to `master`, ConfigCat **code reference scan** may pick up the new string — keep the key stable.

### B. Local Docker (developer machine / localhost E2E)

1. Ensure compose **`config`** is running (`config.apaleo.local:50100`, image typically `apaleo-config:…`). Core Development appsettings already point `configApiEndpoint` there.
2. If the API returns flags as always false / errors in logs (`Unable to retrieve feature flag`), fix **config** connectivity first — core will fail closed.
3. Toggle locally via Features API (needs token with **`config:admin`**), e.g.:

```http
PUT http://config.apaleo.local:50100/features/v0-nsfw/settings
Content-Type: application/json

{
  "featureKey": "<flagKey>",
  "enabled": true,
  "propertyId": "<optional>",
  "countryCode": "<optional>"
}
```

4. Or from E2E/helpers after account bootstrap:

```ts
await set<YourFlag>FeatureFlag(true /*, propertyId? */);
```

5. Verify: hit the gated endpoint/UI path once with flag off (expect reject / old behavior) and on (expect new behavior). Check API logs if still off.

### C. What will not work

- Flipping only an apaleo `appsettings` value for this flag
- Expecting core to talk to ConfigCat CDN directly
- Mixing ConfigCat helpers with Core **settings** FeatureSettings Patch APIs for the same concern

## String-valued flags

E2E supports `PUT /features/v0-nsfw/settings/value` (`setFeatureFlagValue` in helpers). Core `IFeatureSettingsProvider` is **bool-only**. If the product needs a string/percentage flag in C#, call the Config client explicitly or extend the provider — do not pretend `GetFeatureFlagAsync` returns strings.

## Plan / PR checklist (agents)

When the work uses a flag, the lean plan / implementation plan must include:

- [ ] Flag key (camelCase) + C# constant name
- [ ] Targeting: global / property / country
- [ ] Default when Config API down: `false`
- [ ] **Setup for humans** (ConfigCat + local steps above)
- [ ] E2E helper name + enable/restore lifecycle
- [ ] Cleanup ticket reminder

## Related

- Team landscape: `config` = Features API proxy for ConfigCat (`agent-skills` system landscape).
- DB schema flags are unrelated — see `references/db-migrations.md`.
