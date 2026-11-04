#!/usr/bin/env python3
"""Classify test edits made after the implement-tests checkpoint.

Obvious skips, deleted tests, and assertion edits are restored from that
commit. Import and comment edits stay. Other test edits stay and are named.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

_SKIP = re.compile(
    r"\b(?:it|test|describe)\.(?:skip|only|todo)\b"
    r"|\b(?:xit|xdescribe|xcontext|fit|fdescribe)\s*\("
    r"|\bpending\s*\("
)
_ASSERT = re.compile(
    r"\bexpect\s*\("
    r"|\bassert(?:\.\w+)?\s*[\(\.]"
    r"|\.Should[A-Za-z]*\s*\("
    r"|\bto(?:Be|Equal|Throw|Have|Contain|Match|StrictEqual)\s*\(",
    re.IGNORECASE,
)
_TEST_OPEN = re.compile(r"\b(?:it|test|describe)\s*\(")
_IMPORT = re.compile(
    r"^\s*(?:import\s|export\s|from\s|using\s|#include\s"
    r"|const\s+\w+\s*=\s*require\s*\(|\w+\s*=\s*require\s*\()"
)
_SECRET_PATH = re.compile(r"(^|/)\.env($|\.)|(^|/)id_rsa$|(^|/)credentials(\.json)?$")
_ISSUE = re.compile(r"(?:^|/)((?:hc|sl|pa|ps)-?\d+)", re.IGNORECASE)


class TestJudgeError(RuntimeError):
    pass


def issue_label(branch: str) -> str:
    match = _ISSUE.search(branch or "")
    if not match:
        return ""
    prefix, number = re.match(r"([A-Za-z]+)(\d+)", match.group(1).replace("-", "")).groups()
    return f"{prefix.upper()}-{number}"


def checkpoint_message(branch: str, stage: str) -> str:
    label = issue_label(branch)
    return f"{label} checkpoint {stage}".strip()


def classify_diff(diff: str) -> tuple[str, str]:
    """Return (clean|safe|cheat|kept, reason)."""
    if not diff or not diff.strip():
        return "clean", ""
    if "Binary files" in diff and "differ" in diff:
        return "kept", "binary test file"
    removed_assert = added_assert = False
    removed_test = added_test = False
    skip = False
    other = False
    saw_change = False
    for line in diff.splitlines():
        if line.startswith(("diff ", "index ", "@@", "+++", "---", "\\")):
            continue
        if not line or line[0] not in "+-":
            continue
        body = line[1:]
        if not body.strip():
            continue
        saw_change = True
        stripped = body.strip()
        commented = stripped.startswith(("//", "*", "/*", "#"))
        if _SKIP.search(body) and not commented:
            skip = True
        if _ASSERT.search(body):
            if line[0] == "-":
                removed_assert = True
            else:
                added_assert = True
        if _TEST_OPEN.search(body):
            if line[0] == "-":
                removed_test = True
            else:
                added_test = True
        if not _IMPORT.match(body) and not commented:
            other = True
    if not saw_change:
        return "clean", ""
    if skip:
        return "cheat", "skip or only"
    if removed_assert and not added_assert:
        return "cheat", "assertion removed"
    if removed_assert and added_assert:
        return "cheat", "assertion changed"
    if removed_test and not added_test:
        return "cheat", "test case removed"
    if not other:
        return "safe", "imports or comments only"
    return "kept", "setup or helper edit"


def diff_excerpt(diff: str, limit: int = 12) -> str:
    lines: list[str] = []
    for line in diff.splitlines():
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            lines.append(line)
            if len(lines) >= limit:
                break
    return "\n".join(lines)


def affected_commands(manifest: dict, restored_paths: list[str]) -> list[dict]:
    wanted = {
        str(criterion.get("command") or "")
        for criterion in manifest.get("acceptance_criteria") or []
        if criterion.get("test_path") in restored_paths
    }
    wanted.discard("")
    commands: list[dict] = []
    seen: set[str] = set()
    for command in manifest.get("test_commands") or []:
        command_id = str(command.get("id") or "")
        if command_id in wanted and command_id not in seen:
            seen.add(command_id)
            commands.append(command)
    return commands


def render_report(
    restored: list[dict],
    kept: list[dict],
    unrestored: list[dict],
    commands: list[dict],
) -> str:
    failing = [item for item in commands if not item.get("passed")]
    if failing:
        title = "## Restored tests failing locally"
        lead = (
            "Test edits that skipped, deleted, or changed an assertion were restored "
            "from the implement-tests commit. Product commits were left in place. "
            "The restored tests did not pass locally, so this is not a passed verification."
        )
    elif restored:
        title = "## Restored tests"
        lead = (
            "Test edits that skipped, deleted, or changed an assertion were restored "
            "from the implement-tests commit. The affected command passed locally."
        )
    else:
        title = "## Test edits kept"
        lead = (
            "Later stages edited tests. Those edits were not an obvious skip, deletion, "
            "or assertion change, so they were kept."
        )
    lines = [title, "", lead, ""]
    if restored:
        lines.append("Restored:")
        for item in restored:
            lines.append(f"- `{item['path']}` — {item['reason']}")
            excerpt = (item.get("excerpt") or "").strip()
            if excerpt:
                lines.extend(["", "```diff", excerpt, "```", ""])
        if not any((item.get("excerpt") or "").strip() for item in restored):
            lines.append("")
    if unrestored:
        lines.append("Not restored:")
        for item in unrestored:
            lines.append(f"- `{item['path']}` — {item['reason']}")
        lines.append("")
    if kept:
        lines.append("Kept:")
        for item in kept:
            lines.append(f"- `{item['path']}` — {item['reason']}")
        lines.append("")
    if commands:
        lines.append("Commands:")
        for item in commands:
            mark = "passed" if item.get("passed") else "failed"
            argv = " ".join(item.get("argv") or [])
            lines.append(f"- `{argv}` — {mark}")
        lines.append("")
    elif restored:
        lines.append("No acceptance command was mapped to the restored files.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _git(repo: Path, *args: str, env: dict | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env or os.environ.copy(),
    )


def commit_worktree(repo: Path, message: str, env: dict | None = None) -> str | None:
    """Commit the worktree. Return the new SHA, or None when there is nothing to commit."""
    status = _git(repo, "status", "--porcelain", env=env)
    if status.returncode:
        raise TestJudgeError(status.stderr.strip() or "git status failed")
    secret = [
        line[3:]
        for line in status.stdout.splitlines()
        if len(line) > 3 and _SECRET_PATH.search(line[3:])
    ]
    if secret:
        raise TestJudgeError("secret-looking paths in status: " + ", ".join(secret))
    if not status.stdout.strip():
        return None
    added = _git(repo, "add", "-A", env=env)
    if added.returncode:
        raise TestJudgeError(added.stderr.strip() or "git add failed")
    cached = _git(repo, "diff", "--cached", "--quiet", env=env)
    if cached.returncode == 0:
        return None
    if cached.returncode != 1:
        raise TestJudgeError(cached.stderr.strip() or "git diff --cached failed")
    committed = _git(repo, "commit", "-m", message, env=env)
    if committed.returncode:
        detail = (committed.stderr or committed.stdout).strip()
        raise TestJudgeError(detail or "git commit failed")
    head = _git(repo, "rev-parse", "HEAD", env=env)
    if head.returncode or not head.stdout.strip():
        raise TestJudgeError(head.stderr.strip() or "git rev-parse failed")
    return head.stdout.strip()


def file_diff(repo: Path, baseline: str, path: str) -> str:
    result = _git(repo, "diff", baseline, "HEAD", "--", path)
    if result.returncode:
        raise TestJudgeError(result.stderr.strip() or f"git diff failed for {path}")
    return result.stdout


def changed_paths(repo: Path, baseline: str) -> list[str]:
    result = _git(repo, "diff", "--name-only", baseline, "HEAD")
    if result.returncode:
        raise TestJudgeError(result.stderr.strip() or "git diff --name-only failed")
    return [line for line in result.stdout.splitlines() if line.strip()]


def restore_test_file(repo: Path, baseline: str, path: str) -> bool:
    """Restore one file from the baseline commit. Return False when that commit has no such file."""
    exists = _git(repo, "cat-file", "-e", f"{baseline}:{path}")
    if exists.returncode:
        return False
    checkout = _git(repo, "checkout", baseline, "--", path)
    if checkout.returncode:
        raise TestJudgeError(checkout.stderr.strip() or f"git checkout failed for {path}")
    status = _git(repo, "status", "--porcelain", "--", path)
    return bool(status.stdout.strip())
