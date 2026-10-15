---
name: peer-rfc-review
description: >-
  Reviews another author's Apaleo RFC on Notion (or pasted markdown): loads the
  page via Notion MCP when possible, builds a durable understanding for follow-up
  questions, and suggests senior-product-engineer review comments and design
  improvements. Use when the user invokes /peer-rfc-review or asks to review an
  RFC / Notion design doc. If Notion cannot be read, stop and ask the user to
  paste the RFC. Not for drafting RFCs (drafting-rfcs), not for GitHub PR review
  (peer-pr-review).
disable-model-invocation: true
argument-hint: "[Notion URL | page title | pasted RFC]"
---

# Peer RFC review

Help **you** review someone else’s **RFC** like a senior product / platform engineer: understand it deeply, then suggest high-signal Notion comments and design improvements. This is a **design** review, not a copy-edit.

Do **not** edit the Notion page or post comments unless the user explicitly asks after seeing drafts.

Load `$ROOT/.claude/skills/peer-rfc-review/references/rfc-review-lens.md`. Optionally file-read `drafting-rfcs@apaleo` for Apaleo RFC bar (direction-level, API-first) — do not draft a replacement RFC unless asked.

## Model gate

**Preferred host: Claude Code** — session `opus` + high.
**Budget:** before starting, run `python3 "$ROOT/.claude/skills/pipeline/claude_usage_check.py"` (exit 0 = enough). If not enough (or check fails with fallback policy), run this skill on **Cursor Grok** instead.
**Cursor:** never Cursor on-demand Claude. If budget OK → hand off to Claude Code; if budget low → continue here on Grok (`peer-rfc-review-cursor`).
Read `$ROOT/.claude/skills/references/model-routing.md`.



## Speak-as-user guard (special publishes)

Comments / Slack / Linear / Notion posts: follow `$ROOT/.claude/skills/references/speak-as-user.md` (ask first). Does **not** apply to normal `/draft-pr` creation.

Do not edit Notion or post RFC comments until speak-as-user confirmation on the exact text.
## Not this skill

| Skill | Role |
|---|---|
| `drafting-rfcs` | Author an RFC from a PRD |
| `/peer-pr-review` | Review GitHub PRs (apaleo + development) |
| `/review` / `/review-guide` | Code review / walkthrough |

## Stance

1. **Assume good faith and competence** — still challenge load-bearing decisions.
2. **Depth over volume** — prefer fewer, sharper comments. Typical useful set: **3–12**. More only if the user asks for an exhaustive pass.
3. **Argue with the design**, not the writing. Skip emoji/heading/style nits.
4. **Ground claims** — cite the RFC section (or quote a short phrase). If you need code truth for a platform claim, verify in `$ROOT` / worktree or mark `to confirm in code`.
5. **Preserve understanding** — after the review, you must be able to answer follow-ups about the RFC without re-reading from scratch; keep a structured mental model (and optional on-disk briefing).

## Steps

### 1. Obtain the RFC text

Accept: Notion URL, page id/title, or pasted markdown.

**Notion path (preferred when a link/title is given):**

1. Discover Notion tools via MCP (`plugin-notion-workspace-notion` or current Notion server): typically `get_document` / search / equivalent.
2. If the server is `needsAuth` → tell the user to authenticate Notion MCP **or** paste the RFC. Do not proceed on guesses. (Call `mcp_auth` only if the user wants auth now.)
3. Fetch the page. If fetch fails, returns empty, or content is clearly truncated/unusable → **stop** and ask them to paste the full RFC (or the missing sections). Output only that request — no partial review.
4. If they paste markdown → use that as source of truth for this session.

When both Notion and paste exist, prefer the **latest explicit paste** if the user says they updated it; otherwise Notion.

### 2. Build understanding (before commenting)

Produce an internal (and user-visible) **Understanding brief** — this is what later questions hang on:

1. Problem / motivation (2–3 lines)
2. In / out of scope
3. Core model (entities + invariants in plain language)
4. Key operations / lifecycle (create, edit, list, delete, and any fork/split/override/etc.)
5. API surface summary (endpoints + one-line purpose each)
6. Authz / tenancy model
7. Edge cases the RFC already owns
8. Alternatives rejected (and why)
9. Open questions / dependencies / risks the author already flagged
10. **Your residual uncertainties** — what you’d still need to confirm in code or with the author

Do not skip this section even if you later recommend few comments.

Optional persist: `$ROOT/ai-plans/rfc-reviews/<slug>-brief.md` (slug from title). Ask before overwriting.

### 3. Review (senior PE)

Using `rfc-review-lens.md`, walk:

- Placement & platform fit
- Model + lifecycle consistency (including worked examples vs rules)
- API contract clarity and footguns
- Authz / tenancy
- Performance / ops / rollout
- Alignment with stated PRD goals (from the RFC’s own background — don’t invent PRD text)
- Whether open questions are truly blocking

Optionally spot-check **one** load-bearing platform assumption in code (e.g. Property timezone) if `$ROOT` resolves — otherwise list under “to confirm.”

### 4. Suggested Notion comments

For each recommendation:

| Field | Content |
|---|---|
| Severity | `blocking` (should resolve before RFC approval) · `should` · `nit` (rare) |
| Where | RFC section heading (or “API contract / row …”) |
| Why | Risk or inconsistency in one sentence |
| Paste | Collegial Notion comment — question or concrete suggestion |

Also allow a short **Improvements** list that isn’t phrased as inline comments (e.g. “add a sequence diagram for split→fork”) — keep it tight.

If the design is strong: say so plainly, still list residual risks/open questions — **empty comment list is OK** when nothing design-critical remains.

### 5. Output contract

```text
Source: Notion <url|unavailable — pasted> | pasted only
Title: <title>

## Understanding brief
…

## Verdict
Approve as direction | Approve with comments | Needs rework on <themes>

## Suggested Notion comments
none | 1..N as above

## Improvements (optional, not inline)
…

## Follow-ups I can answer from this brief
- <topic bullets>

Ready for your questions on this RFC.
```

Then **wait** — do not post to Notion unless asked. Answer follow-up questions from the brief + RFC; re-fetch Notion only if the user says the page changed.

## Forbidden

- Reviewing from memory of a similar RFC without the actual text
- Continuing after a failed Notion read without pasted content
- Rewriting the whole RFC unsolicited
- Filing Linear issues / implementing code unless the user switches skills
- Nitpicking prose or emoji headers
