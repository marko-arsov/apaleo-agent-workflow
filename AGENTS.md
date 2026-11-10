# Apaleo workspace — agent map

Compact, always-loaded facts for the personal AI coding pipeline. The nearest repository
`AGENTS.md` wins on conflict. Detailed policy lives in `.claude/skills/references/` and is loaded
only when relevant.

## Workspace

```text
$ROOT/                         # workflow checkout; product directories here are separate repositories
├── apaleo/                    # parked master checkout
├── development/               # parked master checkout
├── identity/                  # parked master checkout
├── agent-skills/              # parked master checkout (team plugins)
├── angular-api-proxy/         # parked master checkout (generated Angular API clients)
├── package-essential-api/     # parked master checkout (Apaleo.Essential.Api NuGet package; attach with --with)
├── .repos/<name>.git          # bare mirror of another apaleo org repo, created on first attach
├── worktrees/<branch>/        # feature code for the parked repos, plus <name> when that branch attaches it
├── ai-plans/<branch>/         # complete, revisable plans + mutable evidence
├── .claude/                   # linked checkout of the workflow repository
└── .cursor/                   # editor adapters from that same checkout
```

If cwd contains `/worktrees/`, `$ROOT` is the prefix before it. Otherwise walk upward to this file
plus sibling `apaleo/` and `development/`, outside `worktrees/`. Stop if both mains cannot be verified.

Feature code belongs only under `$ROOT/worktrees/<branch>/`. This directory is the
`marko-arsov/apaleo-agent-workflow` checkout. Change the workflow on a branch and open a pull request.
`_legacy-skills/` is read-only.

## Git invariants

| Repo | Remote | Base |
|---|---|---|
| `apaleo`, `development`, `identity`, `agent-skills`, `angular-api-proxy` | `github.com/apaleo/<repo>` | `master` |

- Parked mains stay on `master`; never check out a feature branch in them.
- Feature branches use worktrees and normally share one branch name across repositories.
- `identity`, `agent-skills`, and `angular-api-proxy` are **optional**: they attach only when a plan
  needs them (`--with-<repo>`) or when `origin/<branch>` already exists in the parked clone. A branch
  may be `--agent-skills-only` or `--angular-api-proxy-only`. `$ROOT` resolution still depends only
  on `AGENTS.md` + `apaleo/` + `development/`.
- Any other `apaleo` org repository attaches for one branch with `worktree-start --with <name>`.
  Confirm the name first. If `$ROOT/<name>` is already a checkout of `apaleo/<name>`, that checkout
  is the source and stays on `master`. Otherwise the first attach creates `$ROOT/.repos/<name>.git`.
  Later stages include that checkout only when the branch recorded it in `pipeline.json` `extra_repos`
  or `worktrees/<branch>/.extra-repos`.
- `package-essential-api` is such a repository with a parked clone: attach it with
  `--with package-essential-api`. apaleo consumes it only as a released NuGet version
  (`Directory.Packages.props`), so a change merges and is released in the package (GitHub release)
  before an apaleo branch bumps the version. Never commit a local package feed or unreleased version.
- Never push to a base branch. Never force-push or use `--force-with-lease`.
- Default branch: Linear's `gitBranchName`, shaped `<github-login>/<issue-id>-<slug>`. Only
  `/specify` derives a new slug. Current tickets are `sl-<id>` (team Sell); `hc-<id>` branches
  predate the team rename and stay as they are.
- Commit subject: `<ISSUE-ID> <imperative summary>` — `SL-29 …` for current work, `HC-<id> …` only
  on existing `hc-` branches. Schema-only uses `[DB-MIGRATION] <ISSUE-ID> …`. Use the Linear
  identifier, never the legacy Swarmia id of a renamed issue.
- Resolve ticket text, PR URLs, `c3331`, `hc3331`, `sl-29`, and `sl29` with `resolve_feature_branch`.
  A team id matches with or without the dash (`sl129` is `sl-129`). `c3331` stays `hc-3331`.
- Never add AI attribution, model names, or generated-by trailers to commits.

Worktree details: `.claude/skills/references/worktrees.md`.

## Commands

```bash
# apaleo
dotnet restore Apaleo.sln && dotnet build Apaleo.sln -c Debug
APALEO_TreatWarningsAsErrors=True APALEO_RunAnalyzersDuringBuild=True dotnet build Apaleo.sln -c Release
dotnet test Apaleo.sln -c Debug --no-build
dotnet test test/Apaleo.<Area>.Tests/Apaleo.<Area>.Tests.csproj -c Debug
dotnet test Apaleo.sln -c Debug --no-build --filter 'FullyQualifiedName~Foo'

# package-essential-api
dotnet restore Apaleo.Essential.Api.sln && dotnet build Apaleo.Essential.Api.sln -c Debug
dotnet test Apaleo.Essential.Api.sln -c Debug --no-build

# identity
dotnet restore Apaleo.Identity.sln && dotnet build Apaleo.Identity.sln -c Debug
dotnet test Apaleo.Identity.sln -c Debug --no-build

# development (compose stack, and payment E2E only)
yarn && npm run build && npm run lint
npm run format && npm run lint-fix
```

Jest E2E for core lives in `apaleo/e2e/tests`. Identity and the other migrated services use `e2e/tests` in that service repo. Generated clients live in `e2e/proxy/<module>` and publish on merge to master. Shared setup is the `@apaleo/e2e-sdk-lib` package. Payment specs stay in `development/src/tests/payment`.

Local one-file run, from that repo's `e2e/` directory, needs GitHub Packages auth (`NPM_CONFIG_USERCONFIG=$HOME/.npmrc` or a `.npmrc` in the `e2e/` folder):

```bash
yarn test -- tests/<area>/<file>-spec.ts
```

Never run the full `yarn test` locally. Payment: `npm run test:file -- ./src/tests/payment/<file>-spec.ts` from `development`. Never target staging/production destructively without confirmation. Load `.claude/skills/references/e2e-stack.md` before localhost E2E. The compose stack still lives in `development`.

## High-risk conventions

- Existing patterns first: cite the nearest same-domain neighbor before creating a type.
- Tenancy: account via `IScopeContext` plus EF `AccountCode`; property via OPA plus
  `IEntityPropertyIdsRetriever`. Missing property enforcement is IDOR.
- Authorization is OPA-first. Property unions/write-every belong in `[Scope]`, resource metadata,
  and Rego—not a new API wrapper service. Prefer default `core/decision` when that axis is already
  correct; named decisions only when default would be wrong. Every new action needs matching
  `endpoint_permissions`.
- Public v1 Swagger contracts are stable and committed. Regenerate the service's `e2e/proxy/<module>` with the Jenkins shared-library generators. Do not hand-edit generated proxies.
- Migrations use Taskfile and deploy-ahead sequencing; never invent schema or combine a destructive
  drop/rename with entity removal.
- Never weaken, skip, delete, quarantine, or filter out a test to obtain green.

The C#, authorization, and E2E details are path-scoped under `.claude/rules/`. Endpoint work also
loads `.claude/skills/references/api-endpoint-patterns.md`; authorization loads `identity.md`.

## Prohibitions

- Never put secrets in tracked files, plans, stage reports, PR text, or public replies.
- Never make opportunistic refactors outside the confirmed plan.
- Never commit an Identity-scope strip, a `.npmrc` token, or a patch of `@apaleo/e2e-sdk-lib`. `development/src/config.ts` is not on development master; do not recreate it.
- Never invoke `setup-new-service` automatically.
- Never post tracker/GitHub comments, resolve threads, or message people as the user without the
  explicit action-specific confirmation in `references/speak-as-user.md`.
- Plans stay complete and auditable. Revise all plan artifacts in place or use a complete `v2/`, then
  `v3/`; the full pipeline archives/rebinds its state automatically.

## On-demand index

| Topic | Reference |
|---|---|
| Pipeline stages, autonomy, routing | `pipeline-stages.md`, `pipeline-autonomy.md`, `model-routing.md` |
| Cursor chat titles | `cursor-chat-title.md` |
| Specification and deferred scope | `specify-process.md`, `deferred-scope.md` |
| Worktrees | `worktrees.md` |
| API endpoints and authorization | `api-endpoint-patterns.md`, `identity.md` |
| Architecture and Graphify | `apaleo-architecture.md`, `graphify.md` |
| E2E stack and scopes | `e2e-stack.md`, `e2e-missing-identity-scopes.md` |
| Migrations and feature flags | `db-migrations.md`, `feature-flags.md` |
| API enum wire values | `api-enum-wire-values.md` |
| PR review and speaking as user | `pr-review.md`, `speak-as-user.md` |
| Support rotation inquiries | `support-rotation.md` |
| Security boundary | `security-boundary.md` |
| Team skills | `team-plugins.md` |
