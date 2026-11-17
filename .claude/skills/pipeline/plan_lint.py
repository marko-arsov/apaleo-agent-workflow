#!/usr/bin/env python3
"""Lint a /specify plan before it is presented for approval.

Errors (exit 1):
- a `repo/path:line` citation that does not exist on origin;
- a missing required section;
- an unresolved placeholder (TBD, TODO, FIXME, ???);
- a manifest acceptance id with no matching example in product.md;
- a C# acceptance test name that is not a literal identifier.

Warnings: a plan longer than its size budget, a missing recommended section, a citation that
cannot be checked, or an acceptance test name that the Tests section never mentions.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from common import FEATURE_REPOS, find_root

CITATION = re.compile(
    r"(?<![\w/.$-])(?:\$ROOT/)?(?P<path>(?:[\w.-]+/)+[\w.-]+\.[A-Za-z]{1,8}):(?P<start>\d+)(?:-(?P<end>\d+))?"
)
BARE_CITATION = re.compile(r"(?<![\w/.-])[\w-]+\.(?:cs|ts|json|rego|sql|yml|yaml|csproj):\d+")
PLACEHOLDER = re.compile(r"\b(?:TBD|TODO|FIXME)\b|\?\?\?")
CSHARP_TEST_NAME = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")
RENDERED_SECTION = re.compile(r"^## Execution Pipeline\b.*?(?=^## |\Z)", re.M | re.S)

PRODUCT_REQUIRED = {
    "observable outcome": ("observable outcome", "outcome"),
    "examples": ("examples",),
    "scope": ("scope",),
}
IMPLEMENTATION_REQUIRED = ("lane", "decisions", "steps", "tests")
IMPLEMENTATION_RECOMMENDED = ("traps", "read first", "assumptions")
BUDGETS = ((150, 120), (600, 250))
LARGE_BUDGET = 400
WORKFLOW_DIRS = (".claude", ".cursor", "ai-plans")


@dataclass
class Resolution:
    repo: str = ""
    path: str = ""
    line_count: int = 0
    abbreviated: bool = False
    ambiguous: bool = False
    missing: bool = False


@dataclass
class LintResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    citations_checked: int = 0


def headings(text: str) -> set[str]:
    found = set()
    for match in re.finditer(r"^##\s+(.+?)\s*$", text, re.M):
        title = re.sub(r"\(.*?\)", "", match.group(1)).strip().lower()
        found.add(title)
    return found


def plan_budget(expected_lines: int) -> int:
    for limit, budget in BUDGETS:
        if expected_lines <= limit:
            return budget
    return LARGE_BUDGET


class OriginFiles:
    """Line counts of files on origin, read once per repository and path."""

    def __init__(self, root: Path, repos: list[str], base: str) -> None:
        self.root = root
        self.repos = repos
        self.base = base
        self._cache: dict[tuple[str, str], int | None] = {}
        self._refs: dict[str, str | None] = {}
        self._trees: dict[str, list[str]] = {}

    def _ref(self, repo: str) -> str | None:
        if repo not in self._refs:
            self._refs[repo] = None
            for candidate in (f"origin/{self.base}", "origin/master"):
                probe = subprocess.run(
                    ["git", "-C", str(self.root / repo), "rev-parse", "--verify", "--quiet", candidate],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if probe.returncode == 0:
                    self._refs[repo] = candidate
                    break
        return self._refs[repo]

    def line_count(self, repo: str, path: str) -> int | None:
        key = (repo, path)
        if key not in self._cache:
            ref = self._ref(repo)
            self._cache[key] = None
            if ref:
                shown = subprocess.run(
                    ["git", "-C", str(self.root / repo), "show", f"{ref}:{path}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if shown.returncode == 0:
                    self._cache[key] = len(shown.stdout.splitlines())
        return self._cache[key]

    def available(self, repo: str) -> bool:
        return self._ref(repo) is not None

    def _tree(self, repo: str) -> list[str]:
        if repo not in self._trees:
            ref = self._ref(repo)
            listed = (
                subprocess.run(
                    ["git", "-C", str(self.root / repo), "ls-tree", "-r", "--name-only", ref],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if ref
                else None
            )
            self._trees[repo] = listed.stdout.splitlines() if listed and listed.returncode == 0 else []
        return self._trees[repo]

    def resolve(self, path: str) -> Resolution:
        """Find a cited path on origin: exact repo path first, then a unique suffix match."""
        first, _, rest = path.partition("/")
        if first in WORKFLOW_DIRS:
            local = self.root / path
            if local.is_file():
                return Resolution("workflow", path, len(local.read_text(encoding="utf-8").splitlines()))
            return Resolution(missing=True)
        if first in self.repos and rest:
            count = self.line_count(first, rest)
            if count is not None:
                return Resolution(first, rest, count)
            path = rest
        for repo in self.repos:
            count = self.line_count(repo, path)
            if count is not None:
                return Resolution(repo, path, count)
        suffix = "/" + path
        matches = [(repo, item) for repo in self.repos for item in self._tree(repo) if item.endswith(suffix)]
        if len(matches) == 1:
            repo, item = matches[0]
            count = self.line_count(repo, item)
            return Resolution(repo, item, count or 0, abbreviated=True)
        if len(matches) > 1:
            return Resolution(ambiguous=True)
        return Resolution(missing=True)


def check_citations(text: str, files: OriginFiles, source: str, result: LintResult) -> None:
    for match in CITATION.finditer(text):
        path, start = match.group("path"), int(match.group("start"))
        end = int(match.group("end") or start)
        cited = f"`{path}:{match.group('start')}" + (f"-{match.group('end')}`" if match.group("end") else "`")
        first = path.partition("/")[0]
        if "..." in path.split("/"):
            result.warnings.append(f"{source}: cannot check elided path {cited}; cite the full path")
            continue
        if first in files.repos and not files.available(first):
            result.warnings.append(f"{source}: cannot check {cited} — no origin for {first}")
            continue
        found = files.resolve(path)
        result.citations_checked += 1
        if found.missing:
            result.errors.append(f"{source}: cited file not on origin: {cited}")
            continue
        if found.ambiguous:
            result.warnings.append(f"{source}: {cited} matches several files; cite the full repo path")
            continue
        if found.abbreviated:
            result.warnings.append(f"{source}: {cited} is abbreviated; cite `{found.repo}/{found.path}`")
        if max(start, end) > found.line_count:
            result.errors.append(
                f"{source}: {cited} is past the end of {found.repo}/{found.path} ({found.line_count} lines)"
            )
    bare = BARE_CITATION.findall(text)
    if bare:
        result.warnings.append(
            f"{source}: {len(bare)} citation(s) without a directory cannot be checked "
            f"(e.g. `{bare[0]}`); cite repo/path:line"
        )


def lint(plan_dir: Path, root: Path) -> LintResult:
    result = LintResult()
    product_path = plan_dir / "product.md"
    implementation_path = plan_dir / "implementation.md"
    for required in (product_path, implementation_path):
        if not required.is_file():
            result.errors.append(f"missing {required.name}")
    if result.errors:
        return result
    product = product_path.read_text(encoding="utf-8")
    implementation = implementation_path.read_text(encoding="utf-8")
    manifest_path = plan_dir / "pipeline.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}

    product_headings = headings(product)
    for label, accepted in PRODUCT_REQUIRED.items():
        if not product_headings.intersection(accepted):
            result.errors.append(f"product.md: missing `## {label.capitalize()}` section")
    if not re.search(r"^###\s+In\b|^\*\*In:\*\*|^In:", product, re.M):
        result.errors.append("product.md: `## Scope` needs a `### In` list (draft-pr reads it)")
    implementation_headings = headings(implementation)
    for title in IMPLEMENTATION_REQUIRED:
        if title not in implementation_headings:
            result.errors.append(f"implementation.md: missing `## {title.capitalize()}` section")
    for title in IMPLEMENTATION_RECOMMENDED:
        if title not in implementation_headings:
            result.warnings.append(f"implementation.md: no `## {title.capitalize()}` section (write `none` if empty)")

    for name, text in (("product.md", product), ("implementation.md", implementation)):
        placeholder = PLACEHOLDER.search(text)
        if placeholder:
            result.errors.append(f"{name}: unresolved placeholder `{placeholder.group(0)}`")

    for criterion in manifest.get("acceptance_criteria") or []:
        criterion_id = str(criterion.get("id") or "")
        test = str(criterion.get("test") or "")
        test_path = str(criterion.get("test_path") or "")
        if criterion_id and not re.search(rf"(?<![\w-]){re.escape(criterion_id)}(?!\w)", product):
            result.errors.append(f"product.md: no example for {criterion_id}")
        if test_path.endswith(".cs") and test and not CSHARP_TEST_NAME.match(test):
            result.errors.append(
                f"{criterion_id}: C# test `{test}` must be the literal method name, not a description"
            )
        if test and test not in implementation:
            result.warnings.append(f"{criterion_id}: test name `{test}` does not appear in implementation.md")

    repos = [*FEATURE_REPOS, "package-essential-api", *(manifest.get("extra_repos") or [])]
    files = OriginFiles(root, [repo for repo in dict.fromkeys(repos)], manifest.get("base_branch") or "master")
    check_citations(product, files, "product.md", result)
    check_citations(implementation, files, "implementation.md", result)

    plan_lines = len(product.splitlines()) + len(RENDERED_SECTION.sub("", implementation).splitlines())
    expected = int((manifest.get("diff_budget") or {}).get("expected_lines") or 0)
    budget = plan_budget(expected)
    if plan_lines > budget:
        result.warnings.append(
            f"plan is {plan_lines} lines; the budget for ~{expected} changed lines is {budget}. "
            "Cut what the implementer would not miss."
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint a /specify plan directory")
    parser.add_argument("plan_dir", type=Path, help="ai-plans/<branch> or one of its vN/ directories")
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.root or find_root(args.plan_dir.resolve())
    plan_dir = args.plan_dir
    versions = sorted(
        (path for path in plan_dir.glob("v*") if re.fullmatch(r"v\d+", path.name) and (path / "product.md").is_file()),
        key=lambda path: int(path.name[1:]),
    )
    if versions:
        plan_dir = versions[-1]
    result = lint(plan_dir, root)
    for error in result.errors:
        print(f"error: {error}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    status = "failed" if result.errors else "passed"
    print(
        f"Plan lint {status}: {plan_dir} — {result.citations_checked} citation(s) checked, "
        f"{len(result.errors)} error(s), {len(result.warnings)} warning(s)"
    )
    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
