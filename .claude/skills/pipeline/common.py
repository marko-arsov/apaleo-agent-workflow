#!/usr/bin/env python3
"""Shared path helpers for pipeline scripts. No timestamps, no branch names."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_MARKERS = ("AGENTS.md", ".claude/skills")
FEATURE_REPOS = ("apaleo", "development", "identity", "agent-skills", "angular-api-proxy")
# Directory names that must never be treated as an extra product repository.
RESERVED_REPO_NAMES = frozenset({
    "worktrees",
    "ai-plans",
    ".claude",
    ".cursor",
    ".repos",
    ".local",
    "host",
    "company-workflow-docs",
})
_EXTRA_REPO_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")


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


def valid_extra_repo_name(name: str) -> bool:
    """True for an apaleo org repository that is not one of the parked five."""
    return bool(_EXTRA_REPO_NAME.fullmatch(name)) and name not in FEATURE_REPOS and name not in RESERVED_REPO_NAMES


def is_git_checkout(path: Path) -> bool:
    git = path / ".git"
    return git.is_dir() or git.is_file()


def _add_extra(names: list[str], seen: set[str], name: str) -> None:
    name = name.strip()
    if not name or name in seen or not valid_extra_repo_name(name):
        return
    seen.add(name)
    names.append(name)


def _read_extra_file(path: Path, names: list[str], seen: set[str]) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        _add_extra(names, seen, line)


def _read_extra_plan(path: Path, names: list[str], seen: set[str]) -> None:
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    extras = data.get("extra_repos") if isinstance(data, dict) else None
    if not isinstance(extras, list):
        return
    for item in extras:
        if isinstance(item, str):
            _add_extra(names, seen, item)


def extra_repo_names(root: Path, branch: str) -> list[str]:
    """Extra repositories recorded for one branch, whether or not the checkout exists."""
    names: list[str] = []
    seen: set[str] = set()
    _read_extra_file(root / "worktrees" / branch / ".extra-repos", names, seen)
    _read_extra_plan(root / "ai-plans" / branch / "pipeline.json", names, seen)
    return names


def discover_extra_repo_names(root: Path) -> list[str]:
    """Extra repositories recorded on any local branch. Does not scan the org or product trees."""
    names: list[str] = []
    seen: set[str] = set()
    patterns = (
        "worktrees/*/.extra-repos",
        "worktrees/*/*/.extra-repos",
        "ai-plans/*/pipeline.json",
        "ai-plans/*/*/pipeline.json",
        "ai-plans/*/*/v2/pipeline.json",
        "ai-plans/*/*/v3/pipeline.json",
    )
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.name == ".extra-repos":
                _read_extra_file(path, names, seen)
            else:
                _read_extra_plan(path, names, seen)
    return names


def attached_repo_names(root: Path, branch: str) -> list[str]:
    """Feature checkouts commit, push, and verify may touch.

    The parked five are included when their worktree directory exists. Any other
    directory is included only when this branch recorded it and the checkout exists.
    """
    base = root / "worktrees" / branch
    names = [name for name in FEATURE_REPOS if (base / name).is_dir()]
    for name in extra_repo_names(root, branch):
        if name not in names and (base / name).is_dir():
            names.append(name)
    return names


def parked_checkout_names(root: Path, branch: str) -> list[str]:
    """Parked checkouts a branch may use as a worktree source."""
    names = [name for name in FEATURE_REPOS if (root / name).is_dir()]
    for name in extra_repo_names(root, branch):
        if name not in names and is_git_checkout(root / name):
            names.append(name)
    return names


def repos_from_manifest(manifest: dict) -> tuple[str, ...]:
    names = list(FEATURE_REPOS)
    extras = manifest.get("extra_repos") or []
    if isinstance(extras, list):
        for item in extras:
            if isinstance(item, str) and valid_extra_repo_name(item) and item not in names:
                names.append(item)
    return tuple(names)


def record_extra_repo(root: Path, branch: str, name: str) -> None:
    if not valid_extra_repo_name(name):
        raise ValueError(f"invalid extra repository name: {name}")
    marker = root / "worktrees" / branch / ".extra-repos"
    marker.parent.mkdir(parents=True, exist_ok=True)
    existing: list[str] = []
    if marker.is_file():
        existing = [line.strip() for line in marker.read_text(encoding="utf-8").splitlines() if line.strip()]
    if name not in existing:
        existing.append(name)
        marker.write_text("".join(f"{item}\n" for item in existing), encoding="utf-8")
    plan = root / "ai-plans" / branch / "pipeline.json"
    if not plan.is_file():
        return
    data = json.loads(plan.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid plan: {plan}")
    extras = data.get("extra_repos")
    if not isinstance(extras, list):
        extras = []
    if name in extras:
        return
    extras.append(name)
    data["extra_repos"] = extras
    plan.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Attached-repository helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_branch(command: argparse.ArgumentParser) -> None:
        command.add_argument("--root", type=Path, required=True)
        command.add_argument("--branch", required=True)

    add_branch(sub.add_parser("attached-repos"))
    add_branch(sub.add_parser("extra-repos"))
    discovered = sub.add_parser("discover-extras")
    discovered.add_argument("--root", type=Path, required=True)
    named = sub.add_parser("valid-extra-name")
    named.add_argument("--name", required=True)
    record = sub.add_parser("record-extra")
    add_branch(record)
    record.add_argument("--name", required=True)

    args = parser.parse_args(argv)
    root = getattr(args, "root", None)
    if root is not None:
        root = root.resolve()
    if args.command == "attached-repos":
        print("\n".join(attached_repo_names(root, args.branch)))
    elif args.command == "extra-repos":
        print("\n".join(extra_repo_names(root, args.branch)))
    elif args.command == "discover-extras":
        print("\n".join(discover_extra_repo_names(root)))
    elif args.command == "valid-extra-name":
        return 0 if valid_extra_repo_name(args.name) else 1
    elif args.command == "record-extra":
        try:
            record_extra_repo(root, args.branch, args.name)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
