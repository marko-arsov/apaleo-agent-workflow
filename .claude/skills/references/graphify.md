# Graphify (Apaleo `apaleo` repo)

Package name on PyPI is **`graphifyy`**; CLI command is **`graphify`**.

Apaleo CI builds knowledge graphs under the feature worktree’s `apaleo/` checkout. Agents should **query the graph before broad grep/read** when it is available — smaller context, fewer tokens, better blast-radius answers.

## Layout (in `$APALEO` = `$WT/apaleo`)

| Path | Role |
|---|---|
| `src/graphify-out/graph.json` | CI/committed graph for `src/` (large) |
| `test/graphify-out/graph.json` | CI/committed graph for `test/` |
| `graphify-out/graph.json` | **Merged** local graph (usually gitignored) — preferred for `query` / `path` / `explain` |
| `merge-graphify.sh` | Merges src+test graphs → root `graphify-out/` |
| `.graphifyignore` | Extract exclusions |
| `CLAUDE.md` § graphify | Repo-local rules (also apply here) |

Root `graphify-out/` is for **local agent use**. Do **not** commit CI graph refresh noise unless the user/CI process expects it (`chore: refresh graphify-out` is a Jenkins/CI concern).

## Ensure CLI + merged graph

```bash
# Install once if needed
pip install --user graphifyy   # or project .graphify-venv

# From $APALEO — merge CI graphs for querying
./merge-graphify.sh
# → writes graphify-out/graph.json
```

Resolve binary: `command -v graphify`, else `$APALEO/.graphify-venv/bin/graphify`.

If `src/graphify-out/graph.json` is missing → branch is behind Graphify CI; `git fetch` / `/sync-master`, or skip Graphify and say so (fall back to LSP/grep).

## Query first (research)

When answering “where is X / what calls Y / blast radius” inside **apaleo**:

```bash
cd "$APALEO"
[[ -f graphify-out/graph.json ]] || ./merge-graphify.sh

graphify query "<question>"
graphify path "<SymbolOrFileA>" "<SymbolOrFileB>"
graphify explain "<concept>"
```

Prefer these over reading `GRAPH_REPORT.md` or grepping the whole solution. Use wiki (`graphify-out/wiki/index.md`) only if present for broad navigation.

Then open **cited** files under `$APALEO` (worktree), not parked `$ROOT/apaleo`.

**development/** has no Graphify graph — keep normal search for E2E/specs.

## After code changes

AST-only refresh (no API cost), from `$APALEO` when you edited C# meaningfully:

```bash
graphify update .
# and/or re-run ./merge-graphify.sh if you rely on the merged file
```

Do not block the skill if Graphify is unavailable — note `graphify: skipped — <reason>` and continue.

## Conflict tip (`/sync-master`)

`src/graphify-out/graph.json` / `test/graphify-out/graph.json` conflicts are usually **generated**. Prefer taking the newer CI/master side or re-running extract/merge rather than hand-merging 50MB JSON. Ask only if both sides look like intentional non-CI edits.

## Skill checklist

| Skill | Use Graphify for |
|---|---|
| `specify` | Blast radius, callers/callees, module ownership before the plan is finalized |
| `implement` / `review` | Navigate to touch points; after edits `graphify update` when cheap |
| `peer-pr-review` | Map changed symbols to dependents before commenting |
| `sync-master` | AUTO-resolve graph.json conflicts via regenerate/take CI side |
| `implement` verify/fix or manual `test-and-fix` | Optional — locate test projects related to a type |

State in skill output: `Graphify: queried | merged | updated | skipped — <reason>`.
