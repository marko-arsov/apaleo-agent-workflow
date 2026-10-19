# Jenkins fetch (read-only, latest build for this branch)

## Env (required for log download)

```bash
# already in ~/.zshrc or ~/.config/jenkins.env — never print TOKEN
JENKINS_URL   # e.g. https://jenkins.apaleo.local
JENKINS_USER
JENKINS_TOKEN
```

If missing in the agent shell: `source ~/.zshrc` or `source ~/.config/jenkins.env` (if that is how the user stores them). Still never echo the token.

## Discover the job URL

Prefer GitHub (no Jenkins write):

```bash
cd "$ROOT/apaleo"   # or development
gh pr checks
# or:
gh api repos/:owner/:repo/commits/$(gh pr view --json headRefOid -q .headRefOid)/status \
  --jq '.statuses[] | select(.context|test("jenkins";"i")) | {context, state, target_url}'
```

`target_url` looks like:

`https://jenkins.apaleo.local/job/apaleo/job/apaleo/job/<branch-encoded>/<build>/display/redirect`

Strip `/display/redirect`. The **job** root is everything before the numeric build id.

Branch encoding: `/` in branch names appears as `%252F` in the job path.

## Latest build only

```bash
JOB="<job-root-without-trailing-build-number>"   # .../job/<login>%252Fhc-...
AUTH=(-u "$JENKINS_USER:$JENKINS_TOKEN" -k)

# metadata — confirm branch + pick build number
curl -sS "${AUTH[@]}" "$JOB/lastCompletedBuild/api/json"

# console — THIS build only
curl -sS "${AUTH[@]}" "$JOB/lastCompletedBuild/consoleText" -o /tmp/jenkins-console.txt
```

Before trusting the log: check `api/json` fields `url` / `fullDisplayName` include the expected branch. If they do not, **stop** (wrong job).

If `lastCompletedBuild` 404: try `lastBuild` and report whether it is still running (`building: true`). Do not walk build numbers downward to older failures unless the user explicitly asks for a specific build.

## Allowed HTTP

- GET `…/lastCompletedBuild/api/json`
- GET `…/lastCompletedBuild/consoleText`
- GET `…/lastBuild/api/json` and `consoleText` only as fallback above

No other Jenkins paths. No POST.

## Chat hygiene

- Do not paste multi‑MB logs. Tail + failure-focused excerpts.
- Redact tokens if they ever appear inside logs.
