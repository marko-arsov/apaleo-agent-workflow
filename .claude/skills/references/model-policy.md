# Model routing contract

`python3 "$ROOT/.claude/skills/pipeline/model_routing.py"` owns this workflow's settings. It never writes native
agent preferences. `models inspect` resolves paths and shows effective settings.
Machine state lives under the existing user data root's `models/`; project policy
lives in `$ROOT/.claude/model-routing.json`. Catalogues remain machine-local.

## Refresh and reviewed settings

`models refresh --providers codex,claude,cursor` lists models without generation.
Supply only the confirmed, allowed providers. Claude discovery returns configured
aliases/IDs needing explicit access confirmation with `--confirm-model claude:opus`.
Check managed policy and backend restrictions first. Discovery never establishes
entitlement and never promotes an unknown model on its own.

The seed registry is a dated qualitative starting point, not benchmark truth.
Official source URLs and review dates accompany its model/effort assessments.
New model IDs appear in `unreviewed_models`. Add relevant reviewed entries through
scope settings; no package edit is required. A registry entry has `provider`,
`model`, `family`, `band` (`fast`, `strong`, `deep`), `stages`, nonnegative `rank`
(lower is preferred), `confidence` (`reviewed` or `provisional`), `sources` and
`reviewed_at`. Optional `efforts` maps `simple`, `balanced`, `demanding` to supported
host values. Cursor instead uses exact IDs, `encoded_effort`, and a `modes` array.
Do not copy capabilities between aliases that resolve to different model versions.
API cost is not subscription cost; unknown usage remains unknown.

Settings use this structure (model names below are placeholders, not recommendations):

```json
{
  "global": {
    "schema_version": 1,
    "providers": ["codex"],
    "defaults": {
      "implement": [{"provider": "codex", "model": "chosen-id", "reasoning": "medium"}]
    },
    "pins": {},
    "blocked": [],
    "registry": []
  }
}
```

Use `project` instead of `global` for a project update, or both keys for `--scope both`.
Each scope object replaces that scope's settings: start with its existing values,
not an empty object. `defaults` and `pins` merge per stage across scopes; each route
array is atomic and contains primary then at most two recommended fallbacks.
`blocked` contains `provider:model` keys and combines across scopes. Provider sets
intersect with the profile and machine restrictions, including explicitly empty sets.
Explicit project pins remain fixed. Explicit `adaptive_stages` in project
settings releases named legacy pins; explain this change in the proposal.

`models propose --scope global --input settings.json --output proposal.json`
creates a path-bound, digest-bound preview. Apply only after the user approves its
actual diff: `models apply --input proposal.json --approve <approval>`.
Backups, serialized writes, stale-file checks, atomic replacement, read-back and a
recovery journal protect settings. `models recover` restores an interrupted update;
it stops rather than overwriting external edits.

## Every specify

Write a small facts JSON using the task analysis already performed:

```json
{
  "stages": ["specify", "implement-tests", "implement", "review"],
  "kind": "code",
  "size": "medium",
  "risk": "standard",
  "uncertain": false,
  "repository_count": 1,
  "test_files": 2,
  "test_lines": 120
}
```

Use only selected AI stages, plus `specify` for an informational planning recommendation.
Size is `small|medium|large`; risk is `low|standard|high`. Missing facts retain balanced
choices. `demanding_stages` optionally narrows stage-specific escalation. `routes`
optionally records explicit user route arrays. Mechanical stages are ignored.

Run `models evaluate --input facts.json --output model-selection.json` once. The
normal output is concise; `--verbose` shows provenance. There are no network,
provider or extra model calls. No effort question or extra approval gate is added.
Small low-risk docs/config use the fast band; routine work uses strong; uncertainty,
high risk and large multi-repository work use deep for affected stages. Four planned
test files or 300 expected test lines escalate test authoring. Numeric facts must be
estimates from the plan, not invented certainty. Higher effort is not always better;
use reviewed model-specific mappings. Maximum levels are never selected automatically.

For a full plan, evaluate the executable AI stages and copy the saved result into
`pipeline.json.model_selection` and its `routes` into `pipeline.json.routes`.
Evaluate `specify` separately only if its informational recommendation is needed;
do not include a non-executable stage in the full route snapshot. An unresolved
selection may be discussed while planning but cannot be executed. Explicit pins
below the recommended capability produce advisory feedback, not silent replacement.
For manual work, keep the compact route table; no detached pipeline is required.

A missing/stale catalogue keeps valid configured routes and adds one notice. Optional
missing effort metadata uses a valid host default; it does not block work. Saved
snapshots validate against their own recorded routes, not today's defaults. Changed
facts or routes require a new snapshot and normal plan revision. Runtime never re-runs
selection on approved plans. Aliases remain mutable; inspect actual execution reports.

## Independent distribution

The standard-library component is `pipeline/model_policy` and imports
no runner code. `scripts/export_model_policy.py <target>/model_policy` exports a
standalone snapshot with checksums; `--check` detects drift. Locally edited exports
must be reviewed before replacement. Downstream adapters own their data paths and
provider restrictions. Updating this package never mutates another workflow's settings.

The Apaleo workspace is one project even inside a product repository. Its machine namespace is `apaleo-workflow/models`, separate from Agent Flow. Use the script with `--root "$ROOT"` before the action. Pass an evaluator snapshot to `pipeline_manifest.py create --model-selection <selection.json>`; the manifest builder attaches and validates it. Legacy suggestion tables are immutable compatibility data.
