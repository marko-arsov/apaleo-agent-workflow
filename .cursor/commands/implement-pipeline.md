# Implement pipeline

Run the Apaleo plan-confirmed pipeline. `/specify` must already have written `pipeline.json`.

```bash
$ROOT/.claude/skills/pipeline/implement-pipeline.sh <task-or-branch> <flags>
```

The command detaches the worker in chat, follows structured progress by default, and prints the
final recap. Common flags: `--stages`, repeated `--route` / `--fallback`, `--dry-run`,
`--preflight-only`, `--status`, `--watch`, and `--no-wait`.
