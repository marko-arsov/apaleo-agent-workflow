# Identity repo + authz permissions

How this pipeline treats **`apaleo/identity`** (OAuth, roles, permission catalog) versus **apaleo OPA** and **development authz E2E**.

Guide for registering new permissions (team, Identity):  
[Adding New Permissions](https://app.notion.com/p/apaleo/Adding-New-Permissions-34104b9ee10b804b9ccfdb84881a65d7)  
(`https://app.notion.com/p/apaleo/Adding-New-Permissions-34104b9ee10b804b9ccfdb84881a65d7`)

Do **not** confuse this with `e2e-missing-identity-scopes.md` (local `config.ts` strip when Identity’s **OAuth ApiScopes** seed is missing `storefront:admin` etc.). That workaround cannot create a **backend permission** that is not in Identity’s catalog.

---

## Three layers (do not collapse)

| Layer | Where | Example | Typical ticket |
|---|---|---|---|
| OPA endpoint keys | `apaleo` `Infrastructure/Authorization/**/data.json` + Rego | `core.calendar_events.create` | Feature endpoint PR |
| Identity catalog + role mapping | **`identity`** `Constants.cs` + `permission_mappings/data.json` (+ optional default-role arrays / business migration) | Same `core.calendar_events.*` keys, mapped under a UI perm PropertyAdmin already has | This reference |
| OAuth `[Scope]` | `apaleo` `SecurityConstants.cs` + `[Scope]` on controllers | `calendar-events.read` | Often a **last** slice (e.g. HC-3338). Identity must also list the scope in `ApiScopes` if non-admin clients will request it |

Account-admin / default E2E **credential client** can often hit a new OPA key via account-level allow **before** Identity maps it. **Property users and custom roles cannot.** Authz specs like `authorization-authz-spec.ts` / `market-segments-authz-spec.ts` need the catalog + mapping or PropertyAdmin-on-own-property is 403.

---

## Register every new endpoint (OPA `data.json`)

Every new controller action that exposes an HTTP route must be registered in **`endpoint_permissions`** in the matching file under `apaleo/src/Apaleo.Api/Infrastructure/Authorization/**/data.json` — **including list routes**, not only get-by-id or POST.

| Piece | Rule |
|---|---|
| Key | `{method}:{swagger path}` — e.g. `get:/calendar/v0-nsfw/events`, `get:/calendar/v0-nsfw/events/{id}`, `post:/calendar/v0-nsfw/events` |
| Value | Array of OPA permission keys (`core.*`). List GET uses the same **read** key as get-by-id; write verbs use **create** / **modify** / **delete** per the sibling routes on that resource |
| Neighbor | Open the `data.json` for the same resource (e.g. `settings/market-segment/data.json` when adding `GET /settings/v0-nsfw/market-segments`) and mirror its list + by-id + write entries |

A new **slice** that adds `GET /…/things` when `GET /…/things/{id}` already exists still needs the list entry — registering the OPA key on the first slice does not auto-cover later routes.

Missing registration → property-user authz fails or behaves inconsistently (Bugbot often flags list endpoints added after create/get-by-id).

**OPA, not a C# wrapper.** Property-union and write-every checks belong in `[Scope]` + OPA
(`[ResourceMetadata]`, `IPropertyLevelRequestModel`, concat `property_ids`, default `core/decision`).
A named custom decision is required only when that axis is wrong. Do not add an API service whose
job is GetFilteredPropertyIds / 404-vs-422. OPA deny is **403**.
PUT is a full replace. Details: `references/api-endpoint-patterns.md`.

---

## Repo

| | |
|---|---|
| GitHub | `https://github.com/apaleo/identity.git` |
| Main checkout | `$ROOT/identity` — **PARKED on `master`** (same rule as apaleo/development) |
| Feature work | `$WT/identity` = `$ROOT/worktrees/<branch>/identity` |
| Branch name | **Identical** to apaleo/development (`<github-login>/<issue-id>-<slug>`) |
| PR host | GitHub (`gh`) from `$WT/identity`; template `.github/pull_request_template.md` |
| Solution | `Apaleo.Identity.sln` (`/open-rider` still opens **apaleo** `Apaleo.sln` — open Identity in Rider only if asked) |

**Opt-in worktree.** Create `$WT/identity` only when specify/plan says Identity is needed, or when `origin/<branch>` already exists on identity. Never “just in case.”

If `$ROOT/identity` is missing: ask, then `git clone https://github.com/apaleo/identity.git "$ROOT/identity"` and leave it on `master`. Do not clone into `$WT`.

---

## When Identity is needed (`/specify` verdict)

**Needed** if any of:

- New OPA backend permission keys (`core.*` / other service prefixes) that **property users** or **custom roles** must hold
- Authz E2E: “user without permission → 403” **and** “user with permission on property A cannot act on property B”
- New **UI-level** permission, default built-in role list, or Identity business migration to sync OPA
- New OAuth scopes Identity must **issue** (`ApiScopeModel` in `Constants.cs` + `Clients.cs`) so non-admin clients can request them

**Not needed** if all of:

- Only account-admin / default E2E client exercises the endpoint
- OPA unit tests mock `permission_mappings`; no property-user E2E
- `[Scope]` is explicitly deferred (later ticket) **and** no new catalog keys are required this slice

Ask A/B only when research is ambiguous. Recommend **needed** whenever the plan includes `*-authz-spec.ts` for built-in roles.

Record in `prompt.md`:

```markdown
## Identity
Verdict: needed | not needed
Reason: <one line>
Notion: Adding New Permissions (link above) — backend vs UI-level path
Worktree: created | not needed | declined — risk recorded
```

---

## What to change in Identity (from the Notion guide)

**New backend permission** (usual for a new OPA key — prefer this):

1. Register the key in `src/Apaleo.Identity.Common/Constants.cs` (permission-definitions dictionary — same 7-tuple shape as `core.schedules.*` / `core.market_segments.*`).
2. Add it as a **dependency** of an existing UI-level permission in  
   `src/Apaleo.Identity/Infrastructure/Authorization/PermissionsBundle/permission_mappings/data.json`.

Hang **create/manage** off a UI perm PropertyAdmin already has (often `property.manage`). Hang **read** off view perms the RFC/product named (e.g. `roomRack.read`, `availability.read`, `rates.read`) — confirm in specify; do not silently grant Accountant write.

**New UI-level permission** (users pick it on custom roles): also add to default-role constants (`PropertyAdminPermissions` etc.) and an Identity **business migration** to notify/sync built-in roles / OPA. See the Notion page.

Custom roles and credential-client permission assignment **look up the key in Identity’s Permissions table**. If it is not registered, E2E cannot assign it (`Permission '…' not found` / invalid property permission key). There is no development-only workaround.

Team plugin `setup-new-service` identity notes are a related checklist — **never auto-invoke** that plugin.

---

## Build / test (from `$WT/identity`)

```bash
cd $WT/identity   # never $ROOT/identity on a feature branch
dotnet restore Apaleo.Identity.sln && dotnet build Apaleo.Identity.sln -c Debug
dotnet test Apaleo.Identity.sln -c Debug --no-build
```

Filter to touched test projects when the plan names them. Business migrations: copy an existing one and register in `IdentityModule` (see identity `README.md`).

---

## Local E2E image (implement verify/fix or manual `test-and-fix`)

Compose uses `${IDENTITY_IMAGE:-…/apaleo-identity:master-latest}`. Catalog changes are **invisible** to authz E2E until the **identity container** runs a build that includes them.

When `$WT/identity` exists and this branch has Identity commits (or the plan says to rebuild):

1. Hold the e2e-stack lock (`references/e2e-stack.md`).
2. Tag from acquire: `apaleo-identity:wt-<short-slug>` (lock script prints `identity_image=…` when `$WT/identity` exists).
3. Build from the **identity worktree** (Release, repo-root context — same pattern as other service images in `development/AGENTS.md`):

   ```bash
   docker build -t apaleo-identity:wt-<slug> \
     -f src/Apaleo.Identity/Dockerfile \
     --build-arg BUILD_CONFIGURATION=Release \
     "$WT/identity"
   ```

4. Pin in the **owner** worktree’s gitignored `development/apaleo/.env` (do not commit):

   ```bash
   # keep existing UI_API_IMAGE line; append or merge
   IDENTITY_IMAGE=apaleo-identity:wt-<slug>
   ```

5. Recreate **only** `identity` (mem_limit workaround as in development AGENTS). Verify  
   `docker inspect apaleo-identity-1 --format '{{.Config.Image}}'`.
6. New accounts in E2E pick up mappings via Identity seed + OPAL sync. After recreate, wait for OPAL bundle load (or re-run authz specs once) — same race as other authz E2E.
7. Do **not** recreate the whole `db` volume to pick up permissions (wipes Identity ApiScopes).

If Identity is **not** on this branch: leave `IDENTITY_IMAGE` unset (master-latest).

---

## Git / PRs

`/commit`, `/push`, and `/draft-pr` operate on **every worktree repo that exists** for the branch (`apaleo`, `development` if present, `identity` if present, `agent-skills` if present, `angular-api-proxy` if present).

- Identity draft PR: `gh pr create --draft --base master` from `$WT/identity`, fill identity’s PR template.
- Cross-links: Identity **Related to** = Linear + apaleo PR; apaleo/development bodies mention the Identity PR when authz/catalog depends on it.
- Save URL under `ai-plans/<branch>/pr.md` `## identity`.
- Merge order for humans: **Identity catalog** should be on the environment Identity uses before property-user authz E2E can pass on CI that still runs `identity:master-latest`. Local implementation verification uses the worktree image so it need not wait for merge.
- `/peer-pr-review`, `/address-pr-comments`, and `/diagnose-ci` include the identity PR when it exists (`gh pr checks` from `$WT/identity`). Identity may use GitHub Actions rather than the apaleo Jenkins job — still read-only; never trigger builds.

---

## Specify / plan / implement

- `/specify` step **4f** Identity verdict (this file). Create identity worktree with `--create-from-master --with-identity` only after permission, same as development.
- `/specify`, `/implement-tests`, and `/implement`: ensure `$WT/identity` when the plan says needed; do not invent it.
- Implementation packet: Identity file map (Constants, `data.json`, optional role arrays / migration) **before** development authz specs that assume PropertyAdmin can POST.
- When Identity is needed and authz E2E must run, select `implement-tests`; recommend `review` (`pipeline-stages.md`). The E2E run is part of `implement`.
