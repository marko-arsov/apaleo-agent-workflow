---
name: add-rule
description: >-
  Captures a recurring Apaleo development rule from plain English and an optional
  violating example, deriving blocking, advisory, or scoped-prose enforcement
  from diff checkability. Supports promotion and the recurrence ratchet. Proposes
  changes first and never writes product repositories.
disable-model-invocation: true
argument-hint: "<rule> [violating example or source URL]"
---

# Add rule

This is the single user-facing convention entry point. `/add-convention` is an internal Tier-1
generator, not an alternative route.

Read the existing metadata in `$ROOT/.claude/conventions/rules/` and run:

```bash
python3 "$ROOT/.claude/skills/pipeline/rule_registry.py" --root "$ROOT" validate
```

## Derive the tier

Answer this question from the rule and example: **can a deterministic script decide whether the
rule was violated by looking at the diff?** Importance does not affect the answer and the operator
cannot override it.

- **No → Tier 3.** Before proposing prose, check existing metadata. If the matching Tier-3 rule has
  two or more violations, refuse more prose and require a newly defined mechanical signal for Tier
  1 or 2. Prose gets one chance.
- **Yes → decide whether every match is wrong.** Always wrong is Tier 1; legitimate unenumerated
  exceptions is Tier 2.

Use `rule_registry.py route --checkable yes|no --always-wrong yes|no` to record the derived result;
there is deliberately no `--tier` or force-Tier-3 option.

Promotion is explicit. After the approved stronger detector/Semgrep/architecture diffs are ready,
apply them together with:

```bash
python3 "$ROOT/.claude/skills/pipeline/rule_registry.py" --root "$ROOT" \
  promote --id <rule-id> --checkable yes --always-wrong yes
```

## Emit a proposal

Every tier proposes a metadata file with these required maintained fields: `id`, `tier`, `added`,
`source`, `statement`, `violations`, and `last_violation`. Artifact pointers may be added when they
make the mechanical implementation auditable.

- **Tier 1:** read and follow `$ROOT/.claude/skills/add-convention/SKILL.md`. Propose a blocking hook,
  architecture-test patch, or both as appropriate. The OPA reference template is
  `.claude/conventions/examples/authorization-must-use-opa.txt`. Product-repository patches remain
  proposals only.
- **Tier 2:** propose a narrow Semgrep warning plus a shared registry entry with advisory severity.
  It must appear in implementation/review evidence but return success. List known false-positive
  shapes. Promotion later re-derives `checkable=yes, always-wrong=yes` and changes Tier 2 to Tier 1.
- **Tier 3:** propose one path-scoped `.claude/rules/*.md` edit or one focused
  `.claude/skills/references/*.md` edit. Never add it to global `AGENTS.md`.

Show unified diffs, expected matches, false-positive risks, source, and cost. Stop for explicit
approval. Only after approval may workflow metadata/artifacts be applied. For a new rule, create its
metadata with the derived answers (do not also apply a duplicate metadata-file patch):

```bash
python3 "$ROOT/.claude/skills/pipeline/rule_registry.py" --root "$ROOT" register \
  --id <rule-id> --statement '<one sentence>' --source '<URL or manual>' \
  --checkable yes|no --always-wrong yes|no --date YYYY-MM-DD
```

Never edit `apaleo`, `development`, `identity`, `agent-skills`, `angular-api-proxy`, or immutable plans.

After an approved change, validate metadata, conventions, skills, and workflow tests. A promotion
must remove or supersede the weaker enforcement so one rule has one effective tier.

The next pipeline review receives the complete registry, rule metadata, allowlist, and scoped-rule
set directly from the runner. Do not add a one-off prompt note or mutate a plan to surface a new
rule. Its review report must name the applicable rule and record the final deterministic scan;
Tier-1 violations are repaired before the review stage completes, while Tier-2/Tier-3 assessment
remains explicit review evidence.
