#!/usr/bin/env python3
"""Report AGENTS.md lines with no evidence of affecting recent runs."""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import date
from pathlib import Path


PIPELINE = Path(__file__).resolve().parents[1] / "pipeline"
sys.path.insert(0, str(PIPELINE))

from rule_registry import candidates as rule_candidates  # noqa: E402


STOP = {
    "about", "after", "again", "also", "always", "before", "branch", "claude", "does", "every",
    "file", "files", "from", "into", "never", "only", "path", "prefer", "repo", "root", "same",
    "skill", "that", "their", "this", "under", "when", "where", "with", "worktree",
}


def keywords(line: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_.-]{3,}", line)
        if token.lower() not in STOP
    }


def recent_corpus(root: Path, days: int) -> str:
    cutoff = time.time() - days * 86400
    parts: list[str] = []
    runs = root / ".local" / "pipeline-runs"
    if not runs.is_dir():
        return ""
    for path in runs.rglob("*"):
        if not path.is_file() or path.stat().st_mtime < cutoff:
            continue
        if path.name.endswith(".prompt.md") or path.suffix not in {".txt", ".md", ".json", ".jsonl"}:
            continue
        try:
            parts.append(path.read_text(encoding="utf-8", errors="replace")[:200_000].lower())
        except OSError:
            continue
    return "\n".join(parts)


def candidates(root: Path, days: int) -> list[tuple[int, str, str]]:
    agents = root / "AGENTS.md"
    corpus = recent_corpus(root, days)
    findings: list[tuple[int, str, str]] = []
    for number, line in enumerate(agents.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "```", "|", "- **Explicit prohibitions")):
            continue
        words = keywords(stripped)
        if len(words) < 2:
            continue
        hits = sorted(word for word in words if word in corpus)
        if len(hits) < min(2, len(words)):
            reason = "no recent output evidence" if not hits else f"only weak keyword evidence: {', '.join(hits)}"
            findings.append((number, stripped, reason))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output) if args.output else root / ".local" / "context-pruning" / "latest.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = candidates(root, args.days)
    lines = [
        "# Context-pruning candidates",
        "",
        f"Evidence window: {args.days} days. This report proposes candidates; it never edits instructions.",
        "",
        "A missing signal is not proof that a rule is useless. Preserve safety invariants and validate each deletion manually.",
        "",
        "| Line | Candidate | Reason |",
        "|---:|---|---|",
    ]
    for number, line, reason in rows:
        lines.append(f"| {number} | {line.replace('|', '&#124;')} | {reason} |")
    if not rows:
        lines.append("| — | No candidates | Recent evidence is insufficient or every actionable line had signals. |")
    rules = rule_candidates(root, as_of=args.as_of, months=6)
    lines += [
        "",
        "## Rule deletion candidates",
        "",
        "Tier-independent rules with zero recorded violations after six months. Propose deletion; never apply it.",
        "",
        "| Rule | Tier | Added |",
        "|---|---:|---|",
    ]
    lines += [f"| `{rule['id']}` | {rule['tier']} | {rule['added']} |" for rule in rules["deletion"]]
    if not rules["deletion"]:
        lines.append("| — | — | No candidates |")
    lines += [
        "",
        "## Rule escalation candidates",
        "",
        "Tier-3 rules with at least two violations must become mechanically enforceable; more prose is refused.",
        "",
        "| Rule | Violations | Last violation |",
        "|---|---:|---|",
    ]
    lines += [
        f"| `{rule['id']}` | {rule['violations']} | {rule['last_violation']} |"
        for rule in rules["escalation"]
    ]
    if not rules["escalation"]:
        lines.append("| — | — | No candidates |")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
