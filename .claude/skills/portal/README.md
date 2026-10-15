# Pipeline reference portal

Regenerate the dependency-free page after workflow changes:

```bash
python3 $ROOT/.claude/skills/portal/generate.py
```

The page summarizes selected-stage execution, default routes, fresh stage isolation, same-session
input continuation, progress commands, and provider failure behavior. Its latest-event card is a build-time snapshot only; live
progress remains `/implement-pipeline <task> --watch` so it works in every chat without a model.

Canonical sources: `../WORKFLOW.md`, `../references/pipeline-stages.md`, and
`../references/model-routing.md`.
