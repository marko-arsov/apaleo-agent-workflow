#!/usr/bin/env python3
"""Deterministic implementation verification and end-of-run evidence gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from common import FEATURE_REPOS, attached_repo_names, find_root, repos_from_manifest
from pipeline_manifest import (
    find_plan_dir,
    load_manifest,
    path_allowed,
    plan_branch_dir,
    task_base_branch,
)


SECRET_PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github-token": re.compile(r"\bgh[oprsu]_[A-Za-z0-9_]{30,}\b"),
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "generic-secret": re.compile(
        r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token)\b\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"
    ),
}
COMPILE_FAILURE = re.compile(
    r"\b(?:error\s+CS\d{4}|compilation failed|build failed|syntaxerror|"
    r"does not contain a definition|cannot find (?:name|symbol)|typecheck failed)\b",
    re.I,
)
ASSERTION_FAILURE = re.compile(
    r"(?:\bAssert\w*Exception\b|\bXunit\.Sdk\b|\bExpected\s*:|\bActual\s*:|"
    r"\bexpected .{0,80}(?:received|actual|to be)\b|\bassertion failed\b|"
    r"\bstatus.{0,50}expected\b|\bFAIL\b)",
    re.I | re.S,
)
NEW_DECISION = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?:new\s+)?(?:product|architectural|architecture)\s+decisions?\s*:?(?!\s*(?:none|no\b))|"
    r"^\s*PIPELINE_DECISION\s*:|^\s*NEW_(?:PRODUCT|ARCHITECTURAL)_DECISION\s*:"
)
DECISION_DECLARATION = re.compile(
    r"(?im)^\s*New product/architectural decisions:\s*(?P<value>[^\r\n]+)\s*$"
)
REVIEW_GATES = {
    "Convention compliance": re.compile(
        r"(?im)^\s*Convention compliance:\s*(?:passed|fixed|findings)\s*[-–—]\s*(?P<evidence>\S.{4,})\s*$"
    ),
    "Reuse/DRY audit": re.compile(
        r"(?im)^\s*Reuse/DRY audit:\s*(?:passed|fixed|findings)\s*[-–—]\s*(?P<evidence>\S.{4,})\s*$"
    ),
}
REVIEW_GATE_EVIDENCE = {
    "Convention compliance": re.compile(
        r"(?:AGENTS\.md|CLAUDE\.md|\.claude/rules|registry|detector|scan)", re.I
    ),
    "Reuse/DRY audit": re.compile(r"(?:\brg\b|graphify|repository|search(?:ed|es)?)", re.I),
}


class VerificationError(RuntimeError):
    pass


def _run(argv: list[str], cwd: Path, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)


def worktrees(root: Path, branch: str) -> dict[str, Path]:
    base = root / "worktrees" / branch
    return {name: base / name for name in attached_repo_names(root, branch)}


def diff_base(root: Path, branch: str, repo: Path) -> str:
    """Merge-base of HEAD and origin/<base>.

    The working tree is compared with that commit. Uncommitted edits are included.
    Files the base deleted after this branch forked are not treated as additions.
    """
    base = task_base_branch(root, branch)
    result = _run(["git", "merge-base", f"origin/{base}", "HEAD"], repo)
    if result.returncode:
        raise VerificationError(
            f"cannot find the fork point with origin/{base} in {repo}: {result.stderr.strip()}; "
            "fetch it, or drop base_branch from pipeline.json once it is merged"
        )
    return result.stdout.strip()


# Core Jest suites master moved into the service repos. Payment and the two
# leftover development folders are still real development work.
_MIGRATED_E2E_PREFIXES = ("src/tests/", "src/proxy/")
_DEVELOPMENT_E2E_KEEP = ("src/tests/payment/", "src/tests/ci/", "src/tests/rendering/")


def _changed_paths(repo: Path, base: str) -> list[str]:
    result = _run(["git", "diff", "--name-only", base], repo)
    if result.returncode:
        raise VerificationError(f"cannot list changes in {repo}: {result.stderr.strip()}")
    paths = [line for line in result.stdout.splitlines() if line]
    paths.extend(path.relative_to(repo).as_posix() for path in _untracked(repo))
    return paths


def _exists_on_ref(repo: Path, ref: str, path: str) -> bool:
    return _run(["git", "cat-file", "-e", f"{ref}:{path}"], repo).returncode == 0


def leftover_core_e2e_message(root: Path, branch: str) -> str | None:
    """Development checkout whose own changes are only core E2E master already removed."""
    repo = root / "worktrees" / branch / "development"
    if not (repo / ".git").exists():
        return None
    base = diff_base(root, branch, repo)
    paths = _changed_paths(repo, base)
    if not paths:
        return None
    leftover: list[str] = []
    for path in paths:
        if path.startswith(_DEVELOPMENT_E2E_KEEP) or not path.startswith(_MIGRATED_E2E_PREFIXES):
            return None
        if _exists_on_ref(repo, "origin/master", path):
            return None
        leftover.append(path)
    shown = ", ".join(leftover[:8])
    extra = "" if len(leftover) <= 8 else f" (+{len(leftover) - 8} more)"
    worktree = repo
    main = root / "development"
    return (
        "development only still carries core E2E that origin/master already removed "
        f"({shown}{extra}). Do not commit or sync it. "
        f"Remove that checkout with `git -C {main} worktree remove --force {worktree}`, "
        "close its pull request, then rerun for the service repo."
    )


def _untracked(repo: Path) -> list[Path]:
    result = _run(["git", "ls-files", "--others", "--exclude-standard", "-z"], repo)
    if result.returncode:
        raise VerificationError(f"cannot list untracked files in {repo}: {result.stderr.strip()}")
    return [repo / item for item in result.stdout.split("\0") if item]


def diff_fingerprint(root: Path, branch: str) -> str:
    digest = hashlib.sha256()
    for name, repo in sorted(worktrees(root, branch).items()):
        digest.update(name.encode())
        for argv in (["git", "diff", "--binary", diff_base(root, branch, repo)],):
            result = _run(argv, repo)
            if result.returncode:
                raise VerificationError(f"cannot fingerprint {name}: {result.stderr.strip()}")
            digest.update(result.stdout.encode("utf-8", errors="replace"))
        for path in sorted(_untracked(repo)):
            digest.update(path.relative_to(repo).as_posix().encode())
            try:
                digest.update(path.read_bytes())
            except OSError as exc:
                raise VerificationError(f"cannot fingerprint {path}: {exc}") from exc
    return digest.hexdigest()


def diff_stats(root: Path, branch: str) -> dict:
    files: set[str] = set()
    added = deleted = 0
    for name, repo in worktrees(root, branch).items():
        result = _run(["git", "diff", "--numstat", diff_base(root, branch, repo)], repo)
        if result.returncode:
            raise VerificationError(f"cannot calculate diff budget for {name}: {result.stderr.strip()}")
        for line in result.stdout.splitlines():
            bits = line.split("\t", 2)
            if len(bits) != 3:
                continue
            left, right, path = bits
            files.add(f"{name}/{path}")
            added += int(left) if left.isdigit() else 0
            deleted += int(right) if right.isdigit() else 0
        for path in _untracked(repo):
            rel = f"{name}/{path.relative_to(repo).as_posix()}"
            files.add(rel)
            try:
                added += len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                pass
    return {"files": len(files), "lines": added + deleted, "added": added, "deleted": deleted, "paths": sorted(files)}


def _added_diff(root: Path, branch: str) -> str:
    blocks: list[str] = []
    for name, repo in worktrees(root, branch).items():
        result = _run(["git", "diff", "--unified=0", diff_base(root, branch, repo)], repo)
        if result.returncode:
            raise VerificationError(f"cannot scan diff for {name}: {result.stderr.strip()}")
        blocks.append(f"# repo={name}\n{result.stdout}")
        for path in _untracked(repo):
            try:
                body = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            blocks.append(
                f"# repo={name} untracked={path.relative_to(repo).as_posix()}\n"
                + "\n".join(f"+{line}" for line in body.splitlines())
            )
    return "\n".join(blocks)


def scan_secrets(root: Path, branch: str, evidence_dir: Path) -> dict:
    diff = _added_diff(root, branch)
    added = "\n".join(
        line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
    findings = [name for name, pattern in SECRET_PATTERNS.items() if pattern.search(added)]
    result = {"status": "passed" if not findings else "failed", "findings": findings, "gitleaks": "unavailable"}
    gitleaks = shutil.which("gitleaks")
    if gitleaks:
        scan_dir = evidence_dir / "gitleaks-input"
        scan_dir.mkdir(parents=True, exist_ok=True)
        (scan_dir / "changes.diff").write_text(diff, encoding="utf-8")
        report = evidence_dir / "gitleaks.json"
        help_result = _run([gitleaks, "help"], root)
        if re.search(r"(?m)^\s*dir\s+", (help_result.stdout or "") + (help_result.stderr or "")):
            command = [gitleaks, "dir", str(scan_dir)]
        else:
            command = [gitleaks, "detect", "--no-git", "--source", str(scan_dir)]
        command += [
            "--redact",
            "--no-banner",
            "--report-format",
            "json",
            "--report-path",
            str(report),
        ]
        process = _run(command, root, timeout=180)
        result["gitleaks"] = "passed" if process.returncode == 0 else "failed"
        if process.returncode not in {0, 1}:
            raise VerificationError(f"gitleaks could not run: {(process.stderr or process.stdout).strip()[-400:]}")
        if process.returncode == 1:
            findings.append("gitleaks")
            result["status"] = "failed"
    return result


def scan_conventions(root: Path, branch: str, evidence_dir: Path) -> dict:
    checker = root / ".claude" / "hooks" / "conventions.py"
    process = _run([sys.executable, str(checker), "check-diff", branch], root, timeout=180)
    (evidence_dir / "conventions.txt").write_text(
        (process.stdout or "") + (process.stderr or ""), encoding="utf-8"
    )
    if process.returncode:
        return {
            "status": "failed",
            "detector": (process.stderr or process.stdout).strip()[-800:],
            "semgrep": "not-run",
        }
    result = {
        "status": "passed",
        "detector": "passed",
        "warnings": [line for line in process.stdout.splitlines() if line.startswith("WARNING ")],
        "semgrep": "unavailable",
        "semgrep_findings": 0,
    }
    semgrep = shutil.which("semgrep")
    worktree = root / "worktrees" / branch
    apaleo = worktree / "apaleo"
    targets = [
        path
        for path in diff_stats(root, branch)["paths"]
        if path.startswith("apaleo/")
        and path.endswith(".cs")
        and (worktree / path).is_file()
    ]
    if semgrep and apaleo.is_dir() and targets:
        report = evidence_dir / "semgrep.json"
        command = [
            semgrep,
            "--config",
            str(root / ".claude" / "conventions" / "semgrep"),
            "--json",
            "--quiet",
            "--output",
            str(report),
        ]
        allowlist_path = root / ".claude" / "conventions" / "allowlist.json"
        try:
            allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            allowlist = {}
        for exemption in allowlist.get("exemptions") or []:
            if exemption.get("path"):
                command += ["--exclude", str(exemption["path"])]
        command.extend(targets)
        semgrep_run = _run(command, worktree, timeout=300)
        try:
            semgrep_report = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else {}
        except json.JSONDecodeError:
            semgrep_report = {}
        semgrep_findings = semgrep_report.get("results") or []
        result["semgrep_findings"] = len(semgrep_findings)
        result["warnings"].extend(
            "WARNING [{rule}] {path}:{line}: {message}".format(
                rule=item.get("check_id") or "semgrep",
                path=item.get("path") or "<unknown>",
                line=(item.get("start") or {}).get("line") or "?",
                message=((item.get("extra") or {}).get("message") or "Semgrep finding").strip(),
            )
            for item in semgrep_findings
        )
        # Findings are advisory here. Tier-1 blocking is owned by the shared
        # detector; Semgrep execution/configuration errors still fail closed.
        result["semgrep"] = "passed" if semgrep_run.returncode == 0 else "failed"
        if semgrep_run.returncode not in {0, 1}:
            result["status"] = "failed"
    elif semgrep:
        result["semgrep"] = "not-applicable"
    return result


def precommit_scan(root: Path, branch: str) -> dict:
    """Run only fast, diff-scoped safety checks; never execute project tests."""
    leftover = leftover_core_e2e_message(root, branch)
    if leftover:
        raise VerificationError(leftover)
    fingerprint = diff_fingerprint(root, branch)
    evidence_dir = (
        root
        / ".local"
        / "pipeline-verification"
        / re.sub(r"[^A-Za-z0-9._-]+", "_", branch)
        / fingerprint[:16]
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "schema": 1,
        "diff_fingerprint": fingerprint,
        "secret_scan": scan_secrets(root, branch, evidence_dir),
        "convention_scan": scan_conventions(root, branch, evidence_dir),
    }
    result["status"] = (
        "passed"
        if result["secret_scan"]["status"] == "passed"
        and result["convention_scan"]["status"] == "passed"
        else "failed"
    )
    (evidence_dir / "precommit.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    if result["status"] != "passed":
        raise VerificationError("pre-commit secret/convention scan failed")
    return result


def parse_test_output(command: dict, output: str, returncode: int) -> tuple[bool, str]:
    if returncode != 0:
        return False, f"exit={returncode}"
    parser = command["parser"]
    if parser == "dotnet":
        failed = re.search(r"Failed:\s*(\d+)", output, re.I)
        if failed and int(failed.group(1)):
            return False, f"dotnet reported {failed.group(1)} failed"
        passed = re.search(r"Passed:\s*(\d+)", output, re.I)
        total = re.search(r"(?:Total tests|Total):\s*(\d+)", output, re.I)
        if passed and int(passed.group(1)) > 0:
            return True, "dotnet success summary parsed"
        if re.search(r"\bTest Run Successful\.", output, re.I) and total and int(total.group(1)) > 0:
            return True, "dotnet successful non-empty run parsed"
        return False, "dotnet success summary not found"
    if parser == "jest":
        if re.search(r"Test Suites:\s*\d+\s+failed", output, re.I):
            return False, "Jest failure summary parsed"
        passed = re.search(r"Tests:.*?([1-9]\d*)\s+passed\b", output, re.I)
        if passed:
            return True, "Jest success summary parsed"
        return False, "Jest success summary not found"
    if parser == "playwright":
        if re.search(r"\b[1-9]\d*\s+failed\b", output, re.I):
            return False, "Playwright failure summary parsed"
        if re.search(r"\b[1-9]\d*\s+passed\b", output, re.I):
            return True, "Playwright success summary parsed"
        return False, "Playwright success summary not found"
    pattern = str(command.get("success_pattern") or "")
    if pattern and re.search(pattern, output, re.I | re.M):
        return True, "configured success pattern parsed"
    return False, "configured success pattern not found"


def red_proof_cites_path(text: str, path: str, repos: tuple[str, ...] = FEATURE_REPOS) -> bool:
    """True when red-proof.md mentions a changed test file.

    Agents often list files as ``apaleo/test/...`` (workspace-relative) or as
    ``test/...`` under an ``apaleo:`` heading (repo-relative). Either form is
    evidence that the file was accounted for; a basename-only mention is not.
    """
    normalized = path.replace("\\", "/").lstrip("./")
    if normalized and normalized in text:
        return True
    repo, _, remainder = normalized.partition("/")
    return bool(repo in repos and remainder and remainder in text)


def dirty_workspace_paths(root: Path, branch: str) -> list[str]:
    found: list[str] = []
    for name, repo in sorted(worktrees(root, branch).items()):
        result = _run(["git", "status", "--porcelain=v1", "--untracked-files=all"], repo)
        if result.returncode:
            raise VerificationError(
                f"cannot list dirty files in {name}: {result.stderr.strip() or result.stdout.strip()}"
            )
        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue
            rest = line[3:]
            if " -> " in rest:
                rest = rest.split(" -> ", 1)[1]
            rest = rest.strip().strip('"')
            if rest:
                found.append(f"{name}/{rest}")
    return found


def dirty_test_paths(root: Path, branch: str, manifest: dict) -> list[str]:
    tests = manifest.get("test_paths") or []
    return [path for path in dirty_workspace_paths(root, branch) if path_allowed(path, tests)]


def validate_red_proof(
    plan_dir: Path,
    manifest: dict,
    *,
    changed_test_paths: list[str] | None = None,
) -> dict:
    proof = plan_branch_dir(plan_dir) / "red-proof.md"
    if not proof.is_file():
        raise VerificationError("implement-tests must write red-proof.md")
    text = proof.read_text(encoding="utf-8", errors="replace")
    if COMPILE_FAILURE.search(text):
        raise VerificationError("red-proof.md contains a compile/type failure, not assertion-level red proof")
    red_criteria = [
        criterion
        for criterion in manifest.get("acceptance_criteria") or []
        if criterion.get("red_required")
    ]
    if not red_criteria:
        if not re.search(r"(?im)^\s*[-*]?\s*failure\s+level\s*:\s*none\b", text):
            raise VerificationError(
                "red-proof.md must declare 'Failure level: none' when no criterion requires assertion-level red"
            )
    else:
        if not re.search(r"(?im)^\s*[-*]?\s*failure\s+level\s*:\s*assertion\s*$", text):
            raise VerificationError("red-proof.md must declare 'Failure level: assertion'")
        if not ASSERTION_FAILURE.search(text):
            raise VerificationError("red-proof.md does not contain assertion-level failure output")
    missing: list[str] = []
    for criterion in red_criteria:
        for value in (criterion.get("test"), criterion.get("command")):
            if value and str(value) not in text:
                missing.append(f"{criterion.get('id')}:{value}")
    if missing:
        raise VerificationError("red-proof.md is missing mapped test/command evidence: " + ", ".join(missing))
    missing_paths = [
        path for path in changed_test_paths or []
        if not red_proof_cites_path(text, path, repos_from_manifest(manifest))
    ]
    if missing_paths:
        raise VerificationError(
            "red-proof.md is missing changed test file evidence: " + ", ".join(missing_paths)
        )
    return {"path": str(proof), "criteria": len(red_criteria)}


def assert_no_new_decisions(paths: list[Path], *, require_declaration: bool = False) -> None:
    violations: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        declaration = DECISION_DECLARATION.search(text)
        declaration_invalid = bool(
            declaration
            and declaration.group("value").strip().lower() not in {"none", "no", "none."}
        )
        if NEW_DECISION.search(text) or declaration_invalid or (require_declaration and not declaration):
            violations.append(str(path))
    if violations:
        raise VerificationError(
            "stage report has a new product/architectural decision or lacks the required 'none' declaration; record a plan defect instead: "
            + ", ".join(violations)
        )


def assert_review_gates(paths: list[Path]) -> None:
    missing: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in REVIEW_GATES.items():
            match = pattern.search(text)
            if not match or not REVIEW_GATE_EVIDENCE[label].search(match.group("evidence")):
                missing.append(f"{path}:{label}")
    if missing:
        raise VerificationError(
            "review report lacks successful convention or repository-wide reuse/DRY audit evidence: "
            + ", ".join(missing)
        )


def _budget_result(manifest: dict, stats: dict) -> dict:
    budget = manifest.get("diff_budget") or {}
    result = {"status": "passed", "actual": stats, "budget": budget, "overshoot": []}
    if manifest.get("legacy_source_version"):
        result["status"] = "legacy-unbudgeted"
        return result
    if stats["files"] > budget["max_files"]:
        result["overshoot"].append(f"files {stats['files']} > maximum {budget['max_files']}")
    if stats["lines"] > budget["max_lines"]:
        result["overshoot"].append(f"lines {stats['lines']} > maximum {budget['max_lines']}")
    if result["overshoot"]:
        result["status"] = "advisory-overshoot"
    elif stats["files"] > budget["expected_files"] or stats["lines"] > budget["expected_lines"]:
        result["status"] = "expected-overshoot"
    return result


def _render_markdown(evidence: dict) -> str:
    lines = [
        "# Implementation verification",
        "",
        f"- Diff fingerprint: `{evidence['diff_fingerprint']}`",
        f"- Status: **{evidence['status']}**",
        f"- Secret scan: **{evidence['secret_scan']['status']}**",
        f"- Convention scan: **{evidence['convention_scan']['status']}**",
        f"- Diff budget: **{evidence['diff_budget']['status']}**",
        "",
        "## Commands",
        "",
    ]
    if not evidence["commands"]:
        lines.append("- Legacy plan: command evidence remains in its original test report.")
    for item in evidence["commands"]:
        lines += [
            f"### {item['id']}",
            f"- Command: `{' '.join(item['argv'])}`",
            f"- Result: **{'passed' if item['passed'] else 'failed'}** — {item['parsed']}",
            f"- Output: `{item['output']}`",
            "",
        ]
    lines += ["## Acceptance traceability", ""]
    if not evidence["acceptance"]:
        lines.append("- Legacy plan: no machine-readable AC mapping was available.")
    for item in evidence["acceptance"]:
        lines.append(
            f"- `{item['id']}` → `{item['test']}` in `{item['test_path']}` via `{item['command']}`: **{'passed' if item['passed'] else 'failed'}**"
        )
    lines += ["", "## Advisory convention findings", ""]
    warnings = evidence["convention_scan"].get("warnings") or []
    lines += [f"- {warning}" for warning in warnings] if warnings else ["- None."]
    return "\n".join(lines).rstrip() + "\n"


def verify(
    root: Path,
    branch: str,
    plan_dir: Path,
    manifest: dict,
    *,
    force: bool = False,
) -> dict:
    fingerprint = diff_fingerprint(root, branch)
    artifact = plan_branch_dir(plan_dir) / "verification.json"
    if artifact.is_file() and not force:
        try:
            cached = json.loads(artifact.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cached = {}
        if cached.get("diff_fingerprint") == fingerprint and cached.get("status") == "passed":
            return cached

    evidence_dir = root / ".local" / "pipeline-verification" / re.sub(r"[^A-Za-z0-9._-]+", "_", branch) / fingerprint[:16]
    evidence_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    by_id: dict[str, dict] = {}
    for command in manifest.get("test_commands") or []:
        repo = root / "worktrees" / branch / command["repo"]
        if not repo.is_dir():
            raise VerificationError(f"verification repo is missing: {repo}")
        command_id = command["id"]
        timeout = int(command.get("timeout_seconds") or 1800)
        environment = os.environ.copy()
        environment.update({str(key): str(value) for key, value in (command.get("env") or {}).items()})
        process = subprocess.run(
            command["argv"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=environment,
        )
        output = (process.stdout or "") + ("\nSTDERR:\n" + process.stderr if process.stderr else "")
        output_path = evidence_dir / f"{re.sub(r'[^A-Za-z0-9._-]+', '_', command_id)}.log"
        output_path.write_text(output, encoding="utf-8")
        passed, parsed = parse_test_output(command, output, process.returncode)
        item = {
            "id": command_id,
            "repo": command["repo"],
            "argv": command["argv"],
            "returncode": process.returncode,
            "passed": passed,
            "parsed": parsed,
            "output": str(output_path),
            "output_text": output,
        }
        results.append(item)
        by_id[command_id] = item

    acceptance: list[dict] = []
    for criterion in manifest.get("acceptance_criteria") or []:
        command = by_id.get(criterion["command"])
        path = root / "worktrees" / branch / criterion["test_path"]
        exists = path.is_file()
        source_has_test = exists and criterion["test"] in path.read_text(encoding="utf-8", errors="replace")
        evidence_matches = bool(
            command
            and re.search(
                criterion["evidence_pattern"],
                command["output_text"],
                re.I | re.M,
            )
        )
        acceptance.append(
            {
                **criterion,
                "exists": exists,
                "source_has_test": source_has_test,
                "evidence_matches": evidence_matches,
                "passed": bool(command and command["passed"] and exists and source_has_test and evidence_matches),
            }
        )

    mutation_result = {"enabled": False, "passed": True}
    mutation = manifest.get("mutation_testing") or {"enabled": False}
    if mutation.get("enabled"):
        repo = root / "worktrees" / branch / str(mutation.get("repo") or "apaleo")
        process = subprocess.run(
            mutation["argv"], cwd=repo, capture_output=True, text=True, timeout=3600, check=False
        )
        output_path = evidence_dir / "mutation.log"
        output_path.write_text((process.stdout or "") + (process.stderr or ""), encoding="utf-8")
        mutation_result = {"enabled": True, "passed": process.returncode == 0, "output": str(output_path)}

    budget = _budget_result(manifest, diff_stats(root, branch))
    secrets = scan_secrets(root, branch, evidence_dir)
    conventions = scan_conventions(root, branch, evidence_dir)
    legacy = bool(manifest.get("legacy_source_version"))
    passed = (
        all(item["passed"] for item in results)
        and all(item["passed"] for item in acceptance)
        and secrets["status"] == "passed"
        and conventions["status"] == "passed"
        and mutation_result["passed"]
    )
    if legacy and not results and not acceptance:
        # Old immutable plans continue through their original in-session validation contract.
        passed = (
            secrets["status"] == "passed"
            and conventions["status"] == "passed"
        )
    evidence = {
        "schema": 1,
        "diff_fingerprint": fingerprint,
        "status": "passed" if passed else "failed",
        "commands": [{key: value for key, value in item.items() if key != "output_text"} for item in results],
        "acceptance": acceptance,
        "diff_budget": budget,
        "secret_scan": secrets,
        "convention_scan": conventions,
        "mutation_testing": mutation_result,
    }
    artifact.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    (plan_branch_dir(plan_dir) / "verification.md").write_text(_render_markdown(evidence), encoding="utf-8")
    if not passed:
        failures = [item["id"] for item in results if not item["passed"]]
        failures += [item["id"] for item in acceptance if not item["passed"]]
        failures += secrets["findings"]
        if conventions["status"] != "passed":
            failures.append("convention-scan")
        if not mutation_result["passed"]:
            failures.append("mutation-testing")
        raise VerificationError("implementation verification failed: " + ", ".join(failures))
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task")
    parser.add_argument("--root", default="")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--red-proof", action="store_true")
    parser.add_argument("--precommit", action="store_true")
    parser.add_argument("--leftover-development", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else find_root()
    try:
        if args.leftover_development:
            message = leftover_core_e2e_message(root, args.task)
            if message:
                print(message)
                return 2
            return 0
        if args.precommit:
            result = precommit_scan(root, args.task)
        else:
            plan_dir = find_plan_dir(root, args.task)
            manifest = load_manifest(plan_dir / "pipeline.json")
            branch = plan_branch_dir(plan_dir).relative_to(root / "ai-plans").as_posix()
            if args.red_proof:
                dirty_tests = dirty_test_paths(root, branch, manifest) if worktrees(root, branch) else []
                result = validate_red_proof(
                    plan_dir, manifest, changed_test_paths=dirty_tests or None
                )
            else:
                result = verify(
                    root, branch, plan_dir, manifest, force=args.force
                )
        print(json.dumps(result, indent=2))
        return 0
    except (VerificationError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
