# Provider and model routing

The confirmed route for each full-pipeline AI stage lives in `ai-plans/<branch>/pipeline.json`. The
same table is rendered into `implementation.md`. `/specify` asks for routes only when the user
selects the full pipeline; the simple manual lane runs `/implement` in the current session and has
no stage routes or provider preflight.

## Refreshable defaults and per-task effort

Use `/update-models` to refresh native catalogues, confirm providers and global/project scope,
and approve an exact settings diff. See `model-policy.md` for the shared evaluator contract.
Apaleo owns separate machine settings and workspace overrides; it never reads another workflow's
mutable settings. Every specify evaluates offline using existing task facts. The evaluator gives
`implement`, `implement-tests`, and `review` different labs when a reviewed model
in band exists; a one-band step is recorded as an advisory. `models watch` records
Artificial Analysis evidence and does not change those routes. Routine work uses
reviewed balanced effort; demanding stages may escalate; maximum effort is explicitly selected.
No extra model call, effort question or automatic retry is added.

Review remains optional and selected by the user. Estimates may inform whether to offer it, but
do not fix its model. Four planned test files or 300 expected test lines escalate test-author
suitability. Mechanical delivery stages and verification within implement need no extra model.

Existing legacy routes remain the initial fallback until refreshed settings are approved. Legacy
suggestion tables stay immutable for historical validation. New manifests carry a hashed model
selection snapshot and never compare it against mutable current defaults. A one-run explicit
route override records the original snapshot separately; it never changes the approved source.

## Route syntax

```text
codex:<model>:<reasoning>
cursor:<model>
claude:<model>:<reasoning>
```

Examples:

```text
claude:sonnet:high
cursor:claude-sonnet-5-thinking-high
cursor:gpt-5.6-sol-high
claude:opus:high
```

Codex routes accept `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, or `ultra` subject to the
selected model. Omit reasoning to use the host default. Claude routes accept its CLI levels `low`, `medium`, `high`, `xhigh`, or `max`.
Cursor reasoning must be encoded in the model id; a third route component is rejected rather than
silently ignored. Preflight detects provider/model incompatibility before implementation starts.

## Exact enforcement

- Cursor runs with `agent --model <id>` and its stream initialization model is compared with the
  requested id. Display names and slug forms are normalized: context-window tokens such as `300K`
  / `272K` and Cursor's `thinking` slug suffix are ignored, so `claude-sonnet-5-thinking-high`
  matches `Claude Sonnet 5 300K High` and `gpt-5.6-sol-high` matches `GPT-5.6 Sol 272K High`.
  Effort/tier tokens (`high`, `medium`) still have to match.
- Codex runs with `codex exec --model <id>` and
  `model_reasoning_effort="<level>"`.
- Claude runs with `claude -p --model <id> --effort <level>`; stream output
  is checked against the requested model.
- Runtime never selects a different model automatically; specify records evaluator recommendations before approval.
- Frontmatter `model:` is documentation for direct invocation; the detached runner's manifest is
  authoritative.

## Overrides and fallbacks

One-run override:

```bash
/implement-pipeline HC-3333 \
  --route review=cursor:claude-opus-5-5-high \
  --fallback review=cursor:grok-4.7-high \
  --fallback review=claude:opus:high \
  --fallback review=codex:gpt-5.6-sol:high
```

Repeated fallback assignments create an ordered list. They replace that stage's confirmed fallback
list for the current run only. The runtime routing copy is stored in the run directory.

`/specify` pre-populates evaluator fallback chains as suggestions. The user may keep, reorder,
replace, or clear them before implementation; the confirmed manifest is authoritative. Never infer
an undeclared fallback from CLI availability, cost, or a provider failure. A route change means a
new process and a fresh context; sessions are never transferred between stages or routes. Only a
user-input continuation resumes the exact same route/session that asked the question (`agent --resume`,
`codex exec resume`, or `claude --resume`).

## Health and provider circuits

Preflight makes a minimal read-only probe for every selected route and caches a healthy result for
ten minutes. Billing/spend-limit, exhausted credit/quota, authentication, disabled account, and
invalid-model errors are permanent for that route. Cursor hosted-model allowance exhaustion is
model-scoped, so it advances to the next confirmed fallback instead of opening a Cursor-wide circuit.
Cursor authentication/account failures and native-provider permanent failures open that provider's
circuit for the rest of the run. Temporary throttling/network/overload may retry once in a new session.

This avoids the HC-3333 failure mode: a long silent provider process is killed by inactivity policy,
and a spend-limit response is not repeatedly retried or silently redirected to another provider.
