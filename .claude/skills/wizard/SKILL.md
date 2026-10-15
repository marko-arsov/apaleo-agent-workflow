---
name: wizard
description: >-
  Create a small interactive bash wizard for manual Apaleo setup, credential,
  dashboard, migration, or cutover steps that the agent cannot perform itself.
argument-hint: "[manual procedure / setup name]"
---

# Wizard

Use this only when the work is genuinely human/manual: third-party dashboards,
credentials, local secrets, one-off account setup, deployment cutovers, or
repeatable setup that needs browser clicks. Do **not** make a wizard for normal
repo edits, tests, git operations, or anything the agent can safely do directly.

## Contract

Produce a bash script that walks Marko through the manual procedure with clear
stage progress, confirmation gates, opened URLs, hidden secret input, and
idempotent local writes. Default to an ephemeral script under
`$ROOT/.local/wizards/<slug>.sh`. Put a script in a repo only if Marko explicitly
wants a repeatable team artifact.

Never invent third-party UI steps, secret names, or destructive cutover actions.
If the source of truth is missing, ask for that one missing detail.

## Process

1. Resolve `$ROOT`, read `$ROOT/AGENTS.md`, then inspect only the relevant repo
   context: nearest README/docs, `.env*`, `docker-compose*`, framework config,
   `.github/workflows/*`, and existing setup scripts. For cutovers/migrations,
   inspect current state, target state, rollback path, and irreversible steps.
2. Show a compact ordered stage list: what the user will do, values captured,
   files or GitHub secrets/variables touched, and irreversible gates. Confirm
   before writing the wizard.
3. Start from `$ROOT/.claude/skills/wizard/template.sh`. Keep the helper library
   above `# ===== STAGES =====` intact; replace the example stages below it.
4. Use helpers: `stage`, `say`, `step`, `open_url`, `ask`, `ask_secret`,
   `write_env`, `set_secret`, `set_var`, `pause`, and `confirm`.
5. Verify without doing the manual flow:
   - `bash -n <script>`
   - `shellcheck <script>` if available
   - `chmod +x <script>`
   - Static trace: every captured value is used; no secret is echoed or written
     to tracked files; every irreversible action has `confirm`.

Return the script path and the exact command to run it. Do not run it
end-to-end unless Marko explicitly asks.
