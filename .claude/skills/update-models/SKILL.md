---
name: update-models
description: Refresh available models and recommend task routes and effort; review changes to this workflow's machine or project defaults.
---

Resolve the Apaleo workspace using `$ROOT/AGENTS.md`. Use `python3 "$ROOT/.claude/skills/pipeline/model_routing.py" --root "$ROOT"` followed by the action (omit the `models` prefix in examples below).

# Update models

Read `$ROOT/.claude/skills/references/model-policy.md` for the settings and task-facts format.

1. Run `models inspect`. Confirm this workflow's machine defaults, the resolved project, or both as the target. Show the actual target paths. Confirm the allowed provider subset; an installed CLI is not proof of account access. Do not update another workflow or native application preferences.
2. Run `models refresh --providers <confirmed,hosts>`. This only refreshes discovery evidence. For Claude, check the backend, applicable managed/local restrictions and actual account access with the user; pass `--confirm-model claude:<advertised-id>` only for confirmed access. Do not claim the catalogue proves entitlement. Preserve existing defaults when discovery fails.
3. Review only relevant new or changed candidates against official model/effort documentation. Native IDs and supported efforts come from discovery. Store proposed assessments with source URLs, date, family, suitability band, stable preference rank and model-specific effort mappings. Newer is not automatically better. Unreviewed candidates stay unselected. No benchmark service or API key is required.
4. Run `models evaluate` for routine defaults; use task-facts input to compare demanding work if useful. Honour project pins. Draft complete settings objects for the selected scopes, preserving existing fields and incorporating reviewed registry additions. Compare those additions with `models evaluate --settings <settings.json>` without applying them. Use the smallest supported effort suitable for the work. Maximum effort requires an explicit choice.
5. Run `models propose --scope <global|project|both> --input <settings.json> --output <proposal.json>`. Present old → new routes, effort, ordered fallbacks, reasons, confidence, and which project pins mask global changes. Ask approval of this exact scope and diff. Do not infer settings approval from permission to refresh.
6. After approval, run `models apply --input <proposal.json> --approve <digest>`. Report the reread effective values. If files changed, regenerate and show the proposal. An interrupted apply has `models recover` to restore its journaled previous values, preserving concurrent edits.

Every specify uses the offline evaluator; do not create a recurring refresh job unless requested. Do not change approved task snapshots, stages, permissions, checks or retry limits. Interactive sessions must apply model changes through their host; a recommendation cannot switch the current session by itself.
