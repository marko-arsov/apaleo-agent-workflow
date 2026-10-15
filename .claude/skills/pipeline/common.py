#!/usr/bin/env python3
"""Shared path helpers for pipeline scripts. No timestamps, no branch names."""

from __future__ import annotations

from pathlib import Path

_MARKERS = ("AGENTS.md", ".claude/skills")
FEATURE_REPOS = ("apaleo", "development", "identity", "agent-skills", "angular-api-proxy")


def find_root(start: Path | None = None) -> Path:
    """Resolve $ROOT. Worktree folders are never treated as $ROOT."""
    cur = (start or Path.cwd()).resolve()
    s = str(cur)
    if "/worktrees/" in s:
        cur = Path(s.split("/worktrees/")[0])
    for p in [cur, *cur.parents]:
        if (p / "AGENTS.md").is_file() and (p / "apaleo").is_dir() and (p / "development").is_dir():
            if "/worktrees/" in str(p):
                continue
            return p
    raise SystemExit("ERROR: could not resolve Apaleo $ROOT (AGENTS.md + apaleo/ + development/)")


def skills_dir(root: Path | None = None) -> Path:
    return (root or find_root()) / ".claude" / "skills"


def pipeline_dir(root: Path | None = None) -> Path:
    return skills_dir(root) / "pipeline"
