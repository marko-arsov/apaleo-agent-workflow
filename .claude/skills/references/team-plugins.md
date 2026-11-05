# Adopted team skills

Installed as Claude Code plugins from `$ROOT/agent-skills` (`@apaleo`, commit `384516ce4512` — refresh with `/update-agent-skills`).

Feature contributions belong in `$WT/agent-skills`, never the parked clone. After merge, `/update-agent-skills --apply` fast-forwards `$ROOT/agent-skills`.

| Skill | Invoke | Role |
|---|---|---|
| `understand` | `/understand` | Post-work tutoring — not for research |
| `drafting-rfcs` | `/drafting-rfcs` | Large design docs before lean plans |
| `clean-code` | `/clean-code` | Authority on C# cleanliness |
| `review-guide` | `/review-guide` only | Human walkthrough — does not fix; cannot preload |
| `e2e-test-engineering` | `/e2e-test-engineering` | Upstream generic E2E process |
| `e2e-test-engineering-development` | `/e2e-test-engineering-development` | Service-repo Jest E2E — pipeline default. Payment stays in `development` |
| `setup-new-service` | `/scaffold`, `/wire`, `/audit` | **Never automatic** — confirm first |
| `keep-linear-updated` | `/keep-linear-updated` | Ensure a Linear issue exists; In Progress when implementing |
| `linear-issue-writer` | `/linear-issue-writer` | Draft, rewrite, or decompose Linear issues |
| `pr-preflight` | `/pr-preflight` | Pre-PR checklist |

## File-read resolution (fallback when invoke/preload fails)

1. `~/.claude/plugins/cache/apaleo/<plugin>/<sha>/skills/<name>/SKILL.md`
2. Else `$ROOT/agent-skills/plugins/<name>/skills/<name>/SKILL.md` (setup-new-service: `plugins/setup-new-service/skills/<scaffold|wire|audit>/`).
3. Pipeline: `$ROOT/.claude/skills/<name>/SKILL.md`.
4. State which path loaded. If missing, say so and continue with degraded guidance.
