#!/usr/bin/env python3
"""Assemble a cache-friendly prompt with a byte-stable plan prefix.

For one plan revision, everything before ``# Stage-specific tail`` is identical
across stages and runs. Provider-controlled tool definitions sit before this
user prompt and are outside the runner's control.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import find_root, skills_dir

DEFAULT_REFS_BY_STAGE = {
    "implement-tests": ["existing-patterns.md", "e2e-stack.md", "identity.md"],
    "implement": [
        "existing-patterns.md",
        "worktrees.md",
        "e2e-stack.md",
        "e2e-missing-identity-scopes.md",
        "clean-code",
    ],
    "review": ["existing-patterns.md", "deferred-scope.md"],
    "specify": ["existing-patterns.md", "worktrees.md", "identity.md"],
    "address-pr-comments": ["deferred-scope.md"],
}


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""


def review_convention_context(root: Path) -> str:
    """Return the authoritative rule inventory for a fresh review session.

    The review agent still selects path-scoped rules from the changed paths, but
    must receive the registry and metadata that `/add-rule` maintains.  Keeping
    this in the stage tail preserves the cross-stage cached prefix while making
    a newly registered rule visible to the very next review.
    """
    sources = [
        root / ".claude" / "conventions" / "registry.json",
        root / ".claude" / "conventions" / "allowlist.json",
        *sorted((root / ".claude" / "conventions" / "rules").glob("*.yml")),
        *sorted((root / ".claude" / "rules").glob("*.md")),
    ]
    parts: list[str] = []
    for source in sources:
        body = _read(source)
        if body:
            parts.append(
                f"## {source.relative_to(root).as_posix()}\n\n{body.strip()}"
            )
    if not parts:
        return ""
    return (
        "# Mandatory review convention inventory\n\n"
        "This is the authoritative `/add-rule` inventory. Apply each scoped rule only to "
        "its matching changed paths. Tier 1 violations must be repaired; Tier 2 matches must "
        "be investigated and evidenced; Tier 3 statements require a semantic review.\n\n"
        + "\n\n---\n\n".join(parts)
    )


def stable_prefix(root: Path, plan_dir: Path | None) -> str:
    parts = ["# Apaleo pipeline cached prefix v2"]
    agents = _read(root / "AGENTS.md")
    if agents:
        parts.append("# AGENTS.md\n\n" + agents.strip())
    if plan_dir:
        for name in ("product.md", "implementation.md", "deferred-scope.md", "pipeline.json"):
            body = _read(plan_dir / name)
            if body:
                parts.append(f"# Plan revision: {name}\n\n" + body.strip())
    return "\n\n---\n\n".join(parts)


def assemble(
    stage: str,
    run_context: str,
    *,
    extra_refs: list[str] | None = None,
    root: Path | None = None,
    plan_dir: Path | None = None,
) -> str:
    root = root or find_root()
    skills = skills_dir(root)
    parts: list[str] = [stable_prefix(root, plan_dir), "# Stage-specific tail"]

    skill = _read(skills / stage / "SKILL.md")
    if skill:
        parts.append(f"# Skill /{stage}\n\n" + skill.strip())

    if stage == "review":
        conventions = review_convention_context(root)
        if conventions:
            parts.append(conventions)

    refs = list(DEFAULT_REFS_BY_STAGE.get(stage, []))
    if extra_refs:
        refs.extend(extra_refs)
    seen: set[str] = set()
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        path = skills / "references" / ref
        if not path.is_file() and not ref.endswith(".md"):
            # plugin name — skip; implement loads clean-code itself
            continue
        body = _read(path)
        if body:
            parts.append(f"# Reference {ref}\n\n" + body.strip())

    parts.append("# Stage task and run context\n\n" + run_context.strip())
    return "\n\n---\n\n".join(parts) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble cache-friendly pipeline prompt")
    ap.add_argument("--stage", required=True)
    ap.add_argument("--context-file", default="")
    ap.add_argument("--plan-dir", default="")
    ap.add_argument("--ref", action="append", default=[])
    args = ap.parse_args()
    ctx = Path(args.context_file).read_text(encoding="utf-8") if args.context_file else sys.stdin.read()
    sys.stdout.write(
        assemble(
            args.stage,
            ctx,
            extra_refs=args.ref,
            plan_dir=Path(args.plan_dir) if args.plan_dir else None,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
