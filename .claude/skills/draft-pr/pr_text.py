#!/usr/bin/env python3
"""Title + PR-body helpers for /draft-pr. Links are filled in the shell, not by the LLM."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LINEAR_RE = re.compile(r"https://linear\.app/[^\s)>\"]+")
H1_RE = re.compile(r"^#\s+(.+)$", re.M)
PRODUCT_PLAN_RE = re.compile(r"\s+[—–-]\s+Product Plan\s*$", re.I)
_PROCESS_LABEL = (
    r"(?:"
    r"prompt(?:\s+(?:and|&)\s+(?:research|decisions))?"
    r"|decisions(?:\s+and\s+research)?"
    r"|request(?:\s*,\s*research)?(?:\s*,\s*decisions|\s+(?:&|and)\s+decisions)"
    r"|product(?:\s+(?:plan|behaviour|behavior))?"
    r"|specify handoff"
    r")"
)
PROCESS_SUFFIX_RE = re.compile(rf"\s+[—–-]\s+{_PROCESS_LABEL}\s*$", re.I)
GENERIC_CORE_RE = re.compile(rf"^{_PROCESS_LABEL}$", re.I)
LINEAR_TITLE_RE = re.compile(r"""Linear\s+[A-Z]+-\d+\s+["“]([^"”]+)["”]""")
RELATED_RE = re.compile(r"^(\*\*Related to:\*\*)\s*.*$", re.M)
E2E_RE = re.compile(r"^(\*\*E2E tests:\*\*)\s*.*$", re.M)
SUMMARY_RE = re.compile(
    r"\*\*Summary\*\*\s*:?\s*\n+(.*?)(?=\n\*\*Details\*\*|\n## Checklist|\Z)",
    re.S | re.I,
)
DETAILS_RE = re.compile(
    r"\*\*Details\*\*\s*:?\s*\n+(.*?)(?=\n## Checklist|\Z)",
    re.S | re.I,
)


def section(text: str, heading: str) -> str:
    """Return the body of a level-two Markdown section, without its heading."""
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)", re.M | re.S | re.I
    )
    match = pattern.search(text or "")
    return match.group(1).strip() if match else ""


def _bullet_block(text: str) -> str:
    bullets: list[list[str]] = []
    paragraphs: list[str] = []
    for line in (text or "").splitlines():
        item = re.match(r"^\s*[-*]\s+(.+)$", line)
        if item:
            bullets.append([item.group(1).strip()])
        elif bullets and line.strip():
            bullets[-1].append(line.strip())
        elif line.strip():
            paragraphs.append(line.strip())
    if bullets:
        return "\n".join(f"- {' '.join(parts)}" for parts in bullets)
    if paragraphs:
        return "- " + " ".join(paragraphs)
    return ""


def _summary_text(product: str) -> str:
    """Reviewer-facing summary. Plans name this section Outcome or Observable outcome."""
    for heading in (
        "Observable outcome",
        "Outcome",
        "Product Summary",
        "Goal and Expected Outcome",
    ):
        body = section(product, heading)
        if body:
            return body
    body = re.sub(r"^#\s+.+\n+", "", (product or "").strip(), count=1)
    return re.split(r"\n##\s+", body, maxsplit=1)[0].strip()


def _scope_details(product: str) -> str:
    """In-scope bullets. Plans use `### In`, `**In:**`, or an `In:` label."""
    scope = section(product, "Scope")
    if not scope:
        return ""
    in_scope = re.search(r"^###\s+In\s*$\n(.*?)(?=^###\s+|\Z)", scope, re.M | re.S | re.I)
    chunk = in_scope.group(1) if in_scope else scope
    chunk = re.split(
        r"\n(?:\*\*Out:\*\*|\*\*Out\*\*|Out:|###\s+Out\b)",
        chunk,
        maxsplit=1,
        flags=re.I,
    )[0]
    if not in_scope:
        labeled = re.search(r"(?:^|\n)(?:\*\*)?In:\*?\*?\s*", chunk)
        if labeled:
            chunk = chunk[labeled.end() :]
        elif not re.search(r"^\s*[-*]\s+", chunk, re.M):
            return ""
    chunk = re.sub(r"^(?:\*\*)?In:\*?\*?\s*", "", chunk.strip())
    return _bullet_block(chunk)


def _acceptance_details(product: str) -> str:
    body = section(product, "Acceptance criteria") or section(product, "Acceptance Criteria")
    if not re.search(r"^\s*[-*]\s+", body or "", re.M):
        return ""
    return _bullet_block(body)


def product_sections(product: str, title: str) -> tuple[str, str]:
    """Derive a reviewer-facing summary and detail bullets from the approved product plan.

    Product plans are the stable description of the intended change. Git history is not: a
    stacked branch includes work from its base and commit subjects are often implementation notes.
    """
    summary = _summary_text(product).strip() or f"Implements {title}."
    details = _scope_details(product) or _acceptance_details(product)
    return summary, details


def _read(path: str) -> str:
    p = Path(path) if path else Path()
    return p.read_text(encoding="utf-8", errors="replace") if path and p.is_file() else ""


def first_h1(text: str) -> str:
    m = H1_RE.search(text or "")
    return (m.group(1) if m else "").strip()


def issue_name(prompt: str, product: str) -> str:
    """Use an optional label from the plan heading without assuming its prefix or format."""
    heading = PRODUCT_PLAN_RE.sub("", first_h1(prompt) or first_h1(product)).strip()
    match = re.match(r"^(.+?)\s+(?:—|–|-)\s+.+$", heading)
    return match.group(1).strip() if match else ""


def linear_url(*texts: str) -> str:
    for text in texts:
        m = LINEAR_RE.search(text or "")
        if m:
            return m.group(0).rstrip(".,;")
    return ""


def related_value(issue: str, linear: str, extra: str = "") -> str:
    if issue and linear:
        base = f"[{issue}]({linear})"
    elif issue:
        base = issue
    elif linear:
        base = f"[issue]({linear})"
    else:
        base = "[link to GH issue]"
    extra = extra.strip()
    return f"{base} — {extra}" if extra else base


def _feature_core(heading: str, issue: str) -> str:
    """Drop process headings such as 'Prompt and research' or 'Product'."""
    raw = (heading or "").strip()
    while True:
        nxt = PROCESS_SUFFIX_RE.sub("", raw).strip()
        nxt = PRODUCT_PLAN_RE.sub("", nxt).strip()
        if nxt == raw:
            break
        raw = nxt
    if issue:
        raw = re.sub(rf"^{re.escape(issue)}\s+[—–-]\s*", "", raw, flags=re.I).strip()
    raw = re.sub(r"\s+", " ", raw).strip(" —–-")
    if not raw or GENERIC_CORE_RE.fullmatch(raw) or (issue and raw.lower() == issue.lower()):
        return ""
    return raw


def _request_summary(prompt: str) -> str:
    quoted = LINEAR_TITLE_RE.search(prompt or "")
    if quoted:
        return re.sub(r"\s+", " ", quoted.group(1)).strip()
    for line in section(prompt, "Request").splitlines():
        line = line.strip().lstrip("-").strip()
        if not line or line.startswith(("#", "|", "http")) or line.lower().startswith("linear "):
            continue
        sentence = re.split(r"(?<=[.!?])\s+", line)[0].split(",")[0].strip()
        return sentence[:110].rstrip()
    return ""


def _core_summary(issue: str, prompt: str, product: str) -> str:
    for text in (prompt, product):
        core = _feature_core(first_h1(text), issue)
        if core:
            return core
    return _request_summary(prompt) or "Update"


def explicit_migration_title(issue: str, *texts: str) -> str:
    """Use a plan-stated `[DB-MIGRATION] <issue> <summary>` title for this PR.

    A mention of another slice (`PR1 (...)` is merged) is not this PR's title.
    """
    if not issue:
        return ""
    pattern = re.compile(rf"`\[DB-MIGRATION\]\s+{re.escape(issue)}\s+([^`]+)`")
    for text in texts:
        for match in pattern.finditer(text or ""):
            line_end = text.find("\n", match.end())
            line = text[text.rfind("\n", 0, match.start()) + 1 : line_end if line_end != -1 else None]
            if re.search(r"\bPR\d+\b", line, re.I) and not re.search(
                r"this (?:plan|PR)|One PR", line, re.I
            ):
                continue
            summary = re.sub(r"\s+", " ", match.group(1)).strip().rstrip(".")
            if summary:
                return f"[DB-MIGRATION] {issue} {summary}"
    return ""


def derive_title(issue: str, prompt: str, product: str, repo: str, implementation: str = "") -> str:
    if repo == "apaleo":
        explicit = explicit_migration_title(issue, implementation, product, prompt)
        if explicit:
            return explicit
    core = _core_summary(issue, prompt, product)
    prefix = f"{issue} " if issue else ""
    if repo == "development":
        rest = re.sub(r"^(Add|Implement|Introduce)\s+", "", core, flags=re.I)
        if not re.search(r"\bE2E\b", core, re.I):
            core = f"Cover {rest} in E2E"
        return f"{prefix}{core}".strip()
    if repo == "identity":
        if not re.search(r"identity|catalog|permission", core, re.I):
            core = f"Identity catalog for {core}"
        return f"{prefix}{core}".strip()
    return f"{prefix}{core}".strip()


def patch_field(body: str, label: str, value: str) -> str:
    pattern = RELATED_RE if label == "Related to" else E2E_RE
    repl = rf"**{label}:** {value}"
    if pattern.search(body or ""):
        return pattern.sub(repl, body, count=1)
    needle = "## Issue ticket number and links"
    line = f"**{label}:** {value}"
    if needle in (body or ""):
        return body.replace(needle, f"{needle}\n{line}", 1)
    return f"{line}\n\n{body}"


def patch_links(body: str, related: str, e2e: str) -> str:
    body = patch_field(body or "", "Related to", related)
    return patch_field(body, "E2E tests", e2e)


def extract_summary_details(text: str) -> tuple[str, str]:
    summary = ""
    details = ""
    sm = SUMMARY_RE.search(text or "")
    dm = DETAILS_RE.search(text or "")
    if sm:
        summary = sm.group(1).strip()
    if dm:
        details = dm.group(1).strip()
    if summary or details:
        return summary, details
    stripped = (text or "").strip()
    return stripped, ""


def plan_extras(product: str, implementation: str, sql: str) -> str:
    """Production-apply note and flattened SQL, when the plan recorded them."""
    apply = section(product, "Production apply") or section(implementation, "Production apply")
    if not apply:
        for text in (product, implementation):
            match = re.search(r"^\*\*Production apply:\*\*\s*(.+)$", text or "", re.M)
            if match:
                apply = match.group(1).strip()
                break
    parts: list[str] = []
    if apply.strip():
        parts.append(f"**Production apply:**\n\n{apply.strip()}")
    script = (sql or "").strip()
    if script:
        parts.append(f"**Manual migration script**\n\n```sql\n{script}\n```")
    return "\n\n".join(parts)


def assemble_body(summary: str, details: str, related: str, e2e: str, extras: str = "") -> str:
    summary = (summary or "").strip() or "Implements the approved change."
    details = (details or "").strip() or "- See the approved product plan for the scoped implementation."
    if not details.startswith("-") and "\n" not in details:
        details = f"- {details}"
    extra = f"\n\n{extras.strip()}\n" if extras.strip() else "\n"
    return (
        "## Issue ticket number and links\n"
        f"**Related to:** {related}\n"
        "\n"
        f"**E2E tests:** {e2e}\n"
        "\n"
        "## Changes\n"
        "**Summary**:\n"
        "\n"
        f"{summary}\n"
        "\n"
        "**Details**:\n"
        "\n"
        f"{details}"
        f"{extra}"
        "\n"
        "## Checklist\n"
        "\n"
        "- [ ] This PR introduces a breaking change\n"
        "- [ ] This change requires a documentation update or announcement\n"
        "- [ ] I have performed a self-review of my code\n"
        "- [ ] I have covered my changes with tests\n"
    )


def assemble_product_body(
    product: str,
    title: str,
    related: str,
    e2e: str,
    implementation: str = "",
    sql: str = "",
) -> str:
    summary, details = product_sections(product, title)
    return assemble_body(
        summary,
        details,
        related,
        e2e,
        plan_extras(product, implementation, sql),
    )


def refresh_generated_body(
    body: str,
    product: str,
    title: str,
    related: str,
    e2e: str,
    implementation: str = "",
    sql: str = "",
) -> str:
    """Refresh only a generated PR's Changes section; retain checkboxes and appended notes."""
    canonical = assemble_product_body(product, title, related, e2e, implementation, sql)
    changes = re.search(r"^## Changes\n.*?(?=^## Checklist\n)", canonical, re.M | re.S)
    existing = re.search(r"^## Changes\n.*?(?=^## Checklist\n)", body or "", re.M | re.S)
    if changes and existing:
        body = body[: existing.start()] + changes.group(0) + body[existing.end() :]
    return patch_links(body, related, e2e)


def title_needs_replace(current: str, issue: str, wanted: str) -> bool:
    cur = (current or "").strip()
    want = (wanted or "").strip()
    if not cur:
        return True
    if issue and re.fullmatch(rf"{re.escape(issue)}(?:\s+#\d+)?", cur, re.I):
        return True
    return cur != want and bool(want)


def _self_test() -> int:
    prompt = "# HC-3331 — Add PUT /events/{id}\n\n| Linear | [HC-3331](https://linear.app/apaleocom/issue/HC-3331/add-put-eventsid) |\n"
    product = "# Add PUT /events/{id} — Product Plan\n"
    assert derive_title("HC-3331", prompt, product, "apaleo") == "HC-3331 Add PUT /events/{id}"
    sl_prompt = "# SL-29 — Add calendar event split endpoint\n"
    assert derive_title("SL-29", sl_prompt, product, "apaleo") == "SL-29 Add calendar event split endpoint"
    arbitrary_prompt = "# Customer journey — Fix empty-state messaging\n"
    assert issue_name(arbitrary_prompt, "") == "Customer journey"
    assert (
        derive_title(issue_name(arbitrary_prompt, ""), arbitrary_prompt, "", "apaleo")
        == "Customer journey Fix empty-state messaging"
    )
    sl96_prompt = "# SL-96 — Fix angular-api-proxy core module discovery\n"
    no_issue_prompt = "# Refresh the deployment notes\n"
    assert issue_name(no_issue_prompt, "") == ""
    assert derive_title("", no_issue_prompt, "", "apaleo") == "Refresh the deployment notes"
    assert derive_title("HC-3331", prompt, product, "agent-skills") == "HC-3331 Add PUT /events/{id}"
    # angular-api-proxy uses the default passthrough, like agent-skills: no repo-specific rewrite.
    assert (
        derive_title("SL-96", sl96_prompt, product, "angular-api-proxy")
        == "SL-96 Fix angular-api-proxy core module discovery"
    )
    assert (
        derive_title("HC-3331", prompt, product, "development")
        == "HC-3331 Cover PUT /events/{id} in E2E"
    )
    assert "Identity catalog" in derive_title("HC-3331", prompt, product, "identity")
    assert linear_url(prompt).endswith("add-put-eventsid")
    rel = related_value("HC-3331", linear_url(prompt))
    assert rel.startswith("[HC-3331](https://linear.app/")
    body = assemble_body("Add PUT.", "- Controller action.", rel, "[link to PR with E2E tests]")
    patched = patch_links(
        body,
        related_value("HC-3331", linear_url(prompt), "apaleo PR: https://github.com/apaleo/apaleo/pull/1"),
        "https://github.com/apaleo/development/pull/2",
    )
    assert "https://github.com/apaleo/development/pull/2" in patched
    assert "apaleo/apaleo/pull/1" in patched
    assert title_needs_replace("HC-3331", "HC-3331", "HC-3331 Add PUT /events/{id}")
    assert title_needs_replace("HC-3331 #6242", "HC-3331", "HC-3331 Cover PUT /events/{id} in E2E")
    assert not title_needs_replace("HC-3331 Add PUT /events/{id}", "HC-3331", "HC-3331 Add PUT /events/{id}")
    bad = "**Related to:** HC-3331\n\n**E2E tests:** Not included in this PR\n"
    fixed = patch_links(bad, rel, "https://github.com/apaleo/development/pull/2")
    assert "Not included" not in fixed
    approved_product = """# SL-29 — Calendar event split — Product Plan

## Observable outcome

Splitting an event keeps the original series before the chosen date and creates an independent tail.

## Scope

### In

- `PUT /calendar/unstable/event-actions/{id}/split`, with a
  full snapshot body.
- Unit, OPA, and E2E coverage.

### Out

- No migration.
"""
    summary, details = product_sections(approved_product, "SL-29 Add calendar event split endpoint")
    assert summary.startswith("Splitting an event")
    assert details.splitlines() == [
        "- `PUT /calendar/unstable/event-actions/{id}/split`, with a full snapshot body.",
        "- Unit, OPA, and E2E coverage.",
    ]
    plan_body = assemble_product_body(approved_product, "SL-29 Add calendar event split endpoint", rel, "N/A")
    assert "Splitting an event" in plan_body
    assert "event-actions/{id}/split" in plan_body
    assert "See commits on this branch" not in plan_body
    stale_body = assemble_body("Implements SL-29.", "- SL-30 stacked commit", rel, "N/A")
    refreshed = refresh_generated_body(
        stale_body + "\n<!-- automated review -->\n",
        approved_product,
        "SL-29 Add calendar event split endpoint",
        rel,
        "N/A",
    )
    assert "SL-30 stacked commit" not in refreshed
    assert "<!-- automated review -->" in refreshed
    process_prompt = (
        '# SL-125 — Prompt and research\n\n'
        'Linear SL-125 "Add per-night rate and surcharge columns to Block and BlockTimeSlice"\n'
    )
    process_product = """# SL-125 — Product

## Outcome

Blocks can store a per-night gross rate.

## Scope

**In:** the entity properties and one additive migration.

**Out:** API models.
"""
    assert issue_name(process_prompt, process_product) == "SL-125"
    assert (
        derive_title("SL-125", process_prompt, process_product, "apaleo")
        == "SL-125 Add per-night rate and surcharge columns to Block and BlockTimeSlice"
    )
    assert "Prompt and research" not in derive_title("SL-125", process_prompt, process_product, "apaleo")
    decisions = "# SL-9 — Decisions and Research\n"
    assert _feature_core(first_h1(decisions), "SL-9") == ""
    migration_plan = (
        "One PR with one commit:\n"
        "`[DB-MIGRATION] SL-125 Add per-night rate and surcharge columns to Block and BlockTimeSlice`.\n"
    )
    assert (
        derive_title("SL-125", process_prompt, process_product, "apaleo", migration_plan)
        == "[DB-MIGRATION] SL-125 Add per-night rate and surcharge columns to Block and BlockTimeSlice"
    )
    assert "Cover" in derive_title("SL-125", process_prompt, process_product, "development", migration_plan)
    other_slice = "1. PR1 (`[DB-MIGRATION] SL-107 Add CalendarEvent search vector`) is merged.\n"
    feature_prompt = "# SL-107 v2 — textSearch on GET occurrences via a search vector\n"
    assert (
        derive_title(issue_name(feature_prompt, ""), feature_prompt, "", "apaleo", other_slice)
        == "SL-107 v2 textSearch on GET occurrences via a search vector"
    )
    outcome_summary, outcome_details = product_sections(process_product, "SL-125 Add columns")
    assert outcome_summary == "Blocks can store a per-night gross rate."
    assert outcome_details == "- the entity properties and one additive migration."
    labeled_scope = """# SL-147 — Product

## Observable outcome

Frequency reads as an enum.

## Scope

In:

- Move the enum.
- Drop the casts.

Out:

- Swagger.
"""
    _, labeled_details = product_sections(labeled_scope, "SL-147 Store frequency")
    assert labeled_details.splitlines() == ["- Move the enum.", "- Drop the casts."]
    prose_scope = """# SL-145 PR2 — Product

## Outcome

Dates are plain.

## Scope

In: calendar domain and occurrence E2E.
Out: the migration PR.
"""
    prose_summary, prose_details = product_sections(prose_scope, "SL-145")
    assert prose_summary == "Dates are plain."
    assert prose_details == "- calendar domain and occurrence E2E."
    ac_only = """# SL-146 — Move suppression markers to the new event when forking — Product plan

## Observable outcome

Markers move with the forked properties.

## Acceptance criteria

- **AC-1** BER has no 5 Oct occurrence after the fork.
- **AC-2** 7 Oct appears once for BER.
"""
    _, ac_details = product_sections(ac_only, "SL-146 Move markers")
    assert ac_details.splitlines() == [
        "- **AC-1** BER has no 5 Oct occurrence after the fork.",
        "- **AC-2** 7 Oct appears once for BER.",
    ]
    apply_product = process_product + "\n## Production apply\n\nStartup is safe. The columns are metadata-only.\n"
    sql_body = assemble_product_body(
        apply_product,
        "SL-125 Add columns",
        rel,
        "N/A — schema-only",
        "",
        'ALTER TABLE "Reservation"."Block" ADD COLUMN IF NOT EXISTS "IncludeSurcharges" boolean NOT NULL DEFAULT FALSE;',
    )
    assert "Startup is safe." in sql_body
    assert "ADD COLUMN IF NOT EXISTS" in sql_body
    assert sql_body.index("**Production apply:**") < sql_body.index("**Manual migration script**")
    assert sql_body.index("**Manual migration script**") < sql_body.index("## Checklist")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="draft-pr title/body helpers")
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("title")
    t.add_argument("--issue", "--ticket", dest="issue", default="")
    t.add_argument("--prompt", default="")
    t.add_argument("--product", default="")
    t.add_argument("--implementation", default="")
    t.add_argument("--repo", default="apaleo")

    lin = sub.add_parser("linear")
    lin.add_argument("--prompt", default="")
    lin.add_argument("--product", default="")

    issue = sub.add_parser("issue")
    issue.add_argument("--prompt", default="")
    issue.add_argument("--product", default="")

    rel = sub.add_parser("related")
    rel.add_argument("--issue", "--ticket", dest="issue", default="")
    rel.add_argument("--linear", default="")
    rel.add_argument("--extra", default="")

    p = sub.add_parser("patch-links")
    p.add_argument("--related", required=True)
    p.add_argument("--e2e", required=True)

    a = sub.add_parser("assemble")
    a.add_argument("--related", required=True)
    a.add_argument("--e2e", required=True)
    a.add_argument("--product", default="")
    a.add_argument("--implementation", default="")
    a.add_argument("--sql", default="")
    a.add_argument("--title", default="")

    r = sub.add_parser("refresh")
    r.add_argument("--product", required=True)
    r.add_argument("--implementation", default="")
    r.add_argument("--sql", default="")
    r.add_argument("--title", required=True)
    r.add_argument("--related", required=True)
    r.add_argument("--e2e", required=True)

    e = sub.add_parser("extract")
    n = sub.add_parser("title-needs-replace")
    n.add_argument("--current", required=True)
    n.add_argument("--issue", "--ticket", dest="issue", default="")
    n.add_argument("--wanted", required=True)

    sub.add_parser("self-test")

    args = ap.parse_args()
    if args.cmd == "self-test":
        return _self_test()
    if args.cmd == "title":
        sys.stdout.write(
            derive_title(
                args.issue,
                _read(args.prompt),
                _read(args.product),
                args.repo,
                _read(args.implementation),
            )
            + "\n"
        )
        return 0
    if args.cmd == "linear":
        sys.stdout.write(linear_url(_read(args.prompt), _read(args.product)) + "\n")
        return 0
    if args.cmd == "issue":
        sys.stdout.write(issue_name(_read(args.prompt), _read(args.product)) + "\n")
        return 0
    if args.cmd == "related":
        sys.stdout.write(related_value(args.issue, args.linear, args.extra) + "\n")
        return 0
    if args.cmd == "patch-links":
        sys.stdout.write(patch_links(sys.stdin.read(), args.related, args.e2e))
        return 0
    if args.cmd == "assemble":
        if args.product:
            sys.stdout.write(
                assemble_product_body(
                    _read(args.product),
                    args.title,
                    args.related,
                    args.e2e,
                    _read(args.implementation),
                    _read(args.sql),
                )
            )
        else:
            summary, details = extract_summary_details(sys.stdin.read())
            sys.stdout.write(assemble_body(summary, details, args.related, args.e2e))
        return 0
    if args.cmd == "refresh":
        sys.stdout.write(
            refresh_generated_body(
                sys.stdin.read(),
                _read(args.product),
                args.title,
                args.related,
                args.e2e,
                _read(args.implementation),
                _read(args.sql),
            )
        )
        return 0
    if args.cmd == "extract":
        summary, details = extract_summary_details(sys.stdin.read())
        sys.stdout.write(f"**Summary**:\n\n{summary}\n\n**Details**:\n\n{details}\n")
        return 0
    if args.cmd == "title-needs-replace":
        sys.stdout.write("yes\n" if title_needs_replace(args.current, args.issue, args.wanted) else "no\n")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
