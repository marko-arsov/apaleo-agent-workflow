# Support rotation: cloud and local agents

Used by `/support-rotation`. The cloud agent is `rotation-processor` in `apaleo/agent-skills`
(branch `data/engineering-tech-support`, Cursor Cloud, started by n8n). Its rules live in that
plugin's `SKILL.md` and `references/output.md`; read them there when its behaviour matters.

## Why two agents

The pattern is proposer and independent verifier, the same idea as a second reviewer on a PR:

- **Division of labour, not duplication.** The cloud agent is a static analyst (thread, Linear,
  Notion, Graphify, code, logs). It cannot run the product, change data, or see flag state. The
  local agent verifies the static claims cheaply and spends its budget on dynamic evidence:
  reproduction, flags, history, and targeted questions.
- **Blind first, then compare.** Writing hypotheses before reading the Outcome keeps the first
  answer from framing the second.
- **Competing hypotheses.** Each hypothesis states what it predicts. Evidence that fits every
  hypothesis decides nothing; look for the observation that splits them.
- **Claim ledger.** Every load-bearing statement gets a verdict and the evidence behind it, so the
  disagreement is concrete and reviewable.
- **Falsifiable reproduction.** A reproduction counts only with a control case that does not show
  the bug.
- **One human gate.** Agents draft; the engineer posts. Feedback flows back so the cloud agent improves.

## Shared state (the sync channel)

Linear comments on the issue are the single record both agents read.

| Comment starts with | Written by | Meaning |
|---|---|---|
| `## Claimed` | cloud | Lock while it works (45-minute lease) |
| `Outcome:` or `## Outcome` | cloud | Its recommendation |
| `## Verification` | local, via the engineer | Claim ledger, reproduction, root cause |
| `## Feedback` | The engineer (local draft) | Verdict on the cloud Outcome, per the Support Rotation guidelines |

Never start a local comment with `Outcome:` or `## Outcome`: the cloud agent treats that as a
finished recommendation and skips re-runs. A re-summon in Slack (a plain reply mentioning the team
handle) makes the cloud agent re-investigate with every comment as context.

## Cloud state

| State | How to tell | Local action |
|---|---|---|
| Outcome present | Outcome comment exists | Blind pass, then verify the ledger |
| In progress | `## Claimed` under 45 minutes, no Outcome | Investigate independently; re-read comments before concluding and reconcile |
| Missed | Handle mentioned, but no 👀, no bot reply, and no issue | Investigate alone; tell the engineer the summon did not trigger (often an edited or formatted message) and suggest a plain thread reply with the handle, or a manual issue in Support Rotation |
| No summon | Team handle never tagged | Check it is this team's inquiry before spending time; another team's handle means another rotation |

## Evidence file

`$ROOT/.local/support-rotation/<ISSUE or thread-ts>/investigation.md`, untracked. Sections:

1. Inputs: thread, issue, team, cloud state, date.
2. Blind pass: question, numbers, hypotheses with predictions.
3. Claim ledger: claim, source, evidence checked, verdict.
4. Experiments: purpose, control and trigger, expected, observed, surface (MCP or API).
5. Cleanup: each staging write with before-state, status `pending` or `done`, verification.
6. Conclusion: root cause, confidence, verdict on the cloud Outcome.
7. Drafts and what was sent (only after the engineer confirmed).

## Least-intervention ladder

Stop at the first rung that resolves it, as the cloud agent does:
Answer → Point to an existing issue, doc, flag, or workaround → Ask one question → Escalate →
Refinement issue → Code fix (via `/specify`). A defect needs a traced path and a contradicted
contract, not only an unhappy customer.

## When to tell the team lead now

The guidelines say high or critical issues go to the team leads right away. Recommend it when any
of these holds:

- the colleague marked it High or Critical, or several customers or accounts are affected;
- money, invoices, fiscal documents, payments, or accounting data are wrong or blocked;
- data is lost or corrupted, or a tenancy or security boundary may be crossed;
- a hotel cannot operate (check-in, check-out, night audit, availability, or distribution is down);
- there is a deadline within about 48 hours (tonight's night audit, tomorrow's arrivals);
- a recent production deploy looks like the cause (possible revert);
- the fix needs a decision the engineer cannot make (product behaviour, a production flag, another team).

Otherwise the normal flow applies: reply, then the journey table.

## Next-step templates

### Question for the thread

One message, at most two questions, each one deciding something:

```text
Hi <name>, to pin this down, could you check:
1. <exact screen or API, exact field, exact date or entity>
2. <second item, only if needed>
A screenshot is enough.
```

Record next to each question which answer confirms or rules out which hypothesis.

### Message to the team lead

```text
Hi <lead>, heads-up on <ISSUE link>: <one-line impact: who, how many, since when>.
Cause: <known | suspected | unknown>. Proposal: <action>. I need <decision or help> by <time>.
```

### Linear issues to offer

Two kinds, drafted in the `linear-issue-writer` style (short, scannable, self-contained), on the
ticket's team:

| Kind | Status | Contents |
|---|---|---|
| **Fix** | Triage | Title in the imperative; expected vs actual; reproduction (the staging steps); suspected cause with `file:line`; regression check; link to the support issue and thread |
| **Improvement** | Triage | The general lesson: a missing guard, a flag rollout, a doc or runbook, a cloud agent prompt change; why it would have prevented or shortened this inquiry |

Both get the Strategic Category (Support & Bug Fixing, or Customer-Driven Development), the team
label, and `customer` when a named customer reported it. Link them to the support issue as
related. Create them only after the engineer says yes to each one.

## Staging tools

The Apaleo MCP, `references/staging-api.sh`, and the test account are described once in
`staging-smoke.md` (section "API surfaces: MCP, then helper"). Both `/support-rotation` and
`/test-on-staging` use them the same way.

## Templates

### Slack reply to the colleague

Short, friendly, plain. No greeting padding, no class names or paths, no promised timelines. Say
what is true, why, and what they can do now.

```text
Hi <name>, we found the cause 🙂

<What the numbers mean, in one or two sentences.>

<Why it happens, in product terms. Say if it was reproduced on staging.>

<One precise question, only if it is still needed.>

What the hotel can do:
• Right now: <workaround or action>
• Longer term: <fix, flag, or issue>, if relevant
```

### Message to a code or flag owner

```text
Hi <name>, a question about <flag or component> (<related issue>).

<Account> hit <symptom> (<issue link>). I reproduced it on staging: <control> vs <trigger>.

<Current state, for example the flag rules per environment.>
1. <Decision you need>
2. <Background question, if any>
```

### Linear verification comment

```markdown
## Verification

**Root cause.** <One or two sentences.>

**Claims.**
| Claim | Verdict | Evidence |
| -- | -- | -- |

**Reproduction** (<account>, <entities>), restored afterwards:
| Case | Expected | Observed |
| -- | -- | -- |

**Change or action.** <What was done or proposed, who approved it, how to revert.>

## Feedback
Verdict: correct | partially correct | wrong
Actual resolution: <one or two sentences>
```

Proposed state follows the guidelines' journey table: answered and confirmed → Done; answered,
waiting on CS → stays in Support Rotation until Friday; real bug needing scoping → Triage; scoped
→ Backlog; feature request → Triage; not an issue → Canceled; duplicate → Duplicate. Moving to
Backlog or Triage also needs a Strategic Category. Keep the team label
(`hotel-cartel-tech-support` for Hotel Ops) and add `customer` when a named customer reported it.

### Team memory note

Follow the cloud plugin's `references/memory.md`: one topic per file, symptom, what is true with
evidence, reply shape, canonical issue. No secrets, no PII, no thread dumps. Update the existing
note on the same topic instead of adding a second one, and correct it when it is wrong.

After the engineer says yes, publish without touching the parked clone:

```bash
MEM="$ROOT/.local/support-rotation/memory-worktree"
git -C "$ROOT/agent-skills" fetch origin data/engineering-tech-support
git -C "$ROOT/agent-skills" worktree add --detach "$MEM" origin/data/engineering-tech-support
# write or edit plugins/rotation-processor/skills/rotation-processor/teams/<slug>/<topic>.md
git -C "$MEM" add <that file> && git -C "$MEM" commit -m "Update <slug> memory: <topic>"
git -C "$MEM" push origin HEAD:data/engineering-tech-support
git -C "$ROOT/agent-skills" worktree remove "$MEM"
```

If the push is rejected, fetch, re-create the worktree, re-apply the one file, and push again.
Never force-push. No AI attribution in the commit.

## Feedback to the cloud agent

Every verdict other than `correct` should reach the cloud agent:

- the `## Feedback` block on the issue (the guidelines' format), and
- a memory note when the miss is a reusable trap (for example, "check
  `newGroupAvailabilityForLateCheckoutsEnabled` per account before blaming the block math").

When the same miss repeats, propose a change to the cloud plugin's `SKILL.md` instead. That is an
`agent-skills` contribution on its own branch and pull request, not part of this skill.
