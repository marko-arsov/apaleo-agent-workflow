#!/usr/bin/env python3
"""Shared edit-time and diff-time convention enforcement."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "pipeline"))

from common import FEATURE_REPOS  # noqa: E402
from pipeline_manifest import ManifestError  # noqa: E402
from rule_registry import load_rules  # noqa: E402
from verification import VerificationError, diff_base  # noqa: E402

REGISTRY = ROOT / ".claude" / "conventions" / "registry.json"
ALLOWLIST = ROOT / ".claude" / "conventions" / "allowlist.json"


class ConventionError(RuntimeError):
    pass


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConventionError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConventionError(f"{path} must contain a JSON object")
    return value


def validate_config(registry: dict, allowlist: dict) -> list[str]:
    errors: list[str] = []
    rules = registry.get("rules")
    exemptions = allowlist.get("exemptions")
    if registry.get("version") != 1 or not isinstance(rules, list):
        errors.append("registry version must be 1 and rules must be a list")
        rules = []
    if allowlist.get("version") != 1 or not isinstance(exemptions, list):
        errors.append("allowlist version must be 1 and exemptions must be a list")
        exemptions = []
    ids: set[str] = set()
    try:
        metadata = {rule_id: value for rule_id, (_path, value) in load_rules(ROOT).items()}
    except (OSError, RuntimeError) as exc:
        errors.append(f"rule metadata invalid: {exc}")
        metadata = {}
    for rule in rules:
        rule_id = str(rule.get("id") or "") if isinstance(rule, dict) else ""
        if not rule_id or rule_id in ids:
            errors.append(f"rule id is empty or duplicated: {rule_id or '<empty>'}")
            continue
        ids.add(rule_id)
        severity = rule.get("severity")
        if severity not in {"block", "advisory"}:
            errors.append(f"{rule_id}.severity must be block or advisory")
        meta = metadata.get(rule_id)
        if not meta:
            errors.append(f"{rule_id} has no metadata file")
        elif (severity == "block" and meta["tier"] != 1) or (
            severity == "advisory" and meta["tier"] != 2
        ):
            errors.append(f"{rule_id} severity does not match metadata tier {meta['tier']}")
        for key in ("file_globs", "allowed_paths", "patterns"):
            values = rule.get(key)
            if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
                errors.append(f"{rule_id}.{key} must be a non-empty string list")
        for pattern in rule.get("patterns") or []:
            try:
                re.compile(pattern, re.I | re.M)
            except re.error as exc:
                errors.append(f"{rule_id} invalid regex: {exc}")
        if not str(rule.get("message") or ""):
            errors.append(f"{rule_id}.message is required")
    for exemption in exemptions:
        if not isinstance(exemption, dict):
            errors.append("each exemption must be an object")
            continue
        if exemption.get("rule") not in ids:
            errors.append(f"exemption references unknown rule: {exemption.get('rule')}")
        if not exemption.get("path") or not exemption.get("reason"):
            errors.append("every exemption needs exact path and reason")
        elif any(char in str(exemption["path"]) for char in "*?[]"):
            errors.append("exemption paths must be exact; globs are not allowed")
    return errors


def normalize_path(value: str) -> str:
    text = value.replace("\\", "/")
    marker = "/worktrees/"
    if marker in text:
        remainder = text.split(marker, 1)[1]
        bits = remainder.split("/", 1)
        return bits[1] if len(bits) == 2 else remainder
    for repo in FEATURE_REPOS:
        needle = f"/{repo}/"
        if needle in text:
            return repo + "/" + text.split(needle, 1)[1]
    root_prefix = ROOT.as_posix().rstrip("/") + "/"
    if text.startswith(root_prefix):
        return text[len(root_prefix) :]
    return text.lstrip("./")


def _matches(path: str, patterns: list[str]) -> bool:
    # fnmatch treats ``**/`` as requiring at least one directory on some
    # Python versions. Convention globs use git-style globstar semantics,
    # where it may also match zero directories.
    def variants(pattern: str) -> set[str]:
        if "/**/" not in pattern:
            return {pattern}
        before, after = pattern.split("/**/", 1)
        tails = variants(after)
        return {
            candidate
            for tail in tails
            for candidate in (before + "/**/" + tail, before + "/" + tail)
        }

    return any(fnmatch.fnmatch(path, variant) for pattern in patterns for variant in variants(pattern))


def _exempt(rule_id: str, path: str, exemptions: list[dict]) -> bool:
    return any(
        exemption.get("rule") == rule_id
        and path == str(exemption.get("path") or "")
        and str(exemption.get("reason") or "").strip()
        for exemption in exemptions
    )


def check(path_value: str, content: str) -> list[dict]:
    registry = load_json(REGISTRY)
    allowlist = load_json(ALLOWLIST)
    problems = validate_config(registry, allowlist)
    if problems:
        raise ConventionError("; ".join(problems))
    path = normalize_path(path_value)
    findings: list[dict] = []
    for rule in registry["rules"]:
        if not _matches(path, rule["file_globs"]):
            continue
        if _matches(path, rule.get("allowed_paths") or []):
            continue
        if any(
            re.search(rf"(?m)^\s*namespace\s+{re.escape(namespace)}(?:[.;])", content)
            for namespace in rule.get("allowed_namespaces") or []
        ):
            continue
        if _exempt(rule["id"], path, allowlist["exemptions"]):
            continue
        matches = [pattern for pattern in rule["patterns"] if re.search(pattern, content, re.I | re.M)]
        if matches:
            findings.append(
                {
                    "rule": rule["id"],
                    "path": path,
                    "severity": rule.get("severity", "block"),
                    "message": rule["message"],
                    "patterns": matches,
                }
            )
    return findings


def _introduced(finding: dict, content: str, baseline: str) -> bool:
    return any(
        len(re.findall(pattern, content, re.I | re.M)) > len(re.findall(pattern, baseline, re.I | re.M))
        for pattern in finding["patterns"]
    )


def hook_findings(path_value: str, content: str, baseline: str = "") -> list[dict]:
    """Findings the edit introduces; ``baseline`` is the text it replaces."""
    path = normalize_path(path_value)
    # Enforcement artifacts must remain repairable even while a promotion is
    # being applied across metadata + registry + Semgrep in separate edits.
    if path.startswith(".claude/conventions/") or path == ".claude/hooks/conventions.py":
        return []
    # A brownfield file keeps what it already had (e.g. a block namespace); only new matches block.
    return [finding for finding in check(path, content) if _introduced(finding, content, baseline)]


def _tool_name(payload: dict) -> str:
    return str(payload.get("tool_name") or payload.get("tool") or payload.get("toolName") or "")


def _tool_input(payload: dict) -> dict:
    values = payload.get("tool_input") or payload.get("input") or payload.get("arguments") or {}
    return values if isinstance(values, dict) else {}


def _edit_path(values: dict) -> str:
    return str(
        values.get("file_path")
        or values.get("path")
        or values.get("target_notebook")
        or ""
    )


def _write_content(values: dict) -> str:
    if "contents" in values:
        return str(values.get("contents") or "")
    return str(values.get("content") or "")


def _current_content(path_value: str, payload: dict) -> str:
    path = Path(path_value)
    if not path.is_absolute():
        path = Path(str(payload.get("cwd") or ".")) / path
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def hook_payload(payload: dict) -> list[tuple[str, str, str]]:
    """(path, written text, text it replaces) for each edit in the tool call."""
    tool = _tool_name(payload)
    values = _tool_input(payload)
    if tool not in {"Write", "Edit", "MultiEdit", "StrReplace", "EditNotebook"}:
        return []
    path = _edit_path(values)
    if tool == "Write":
        # Cursor sends edits to existing files as a Write of the whole result.
        return [(path, _write_content(values), _current_content(path, payload))]
    if tool in {"Edit", "StrReplace", "EditNotebook"}:
        return [(path, str(values.get("new_string") or ""), str(values.get("old_string") or ""))]
    return [
        (
            path,
            str(edit.get("new_string") or edit.get("contents") or edit.get("content") or ""),
            str(edit.get("old_string") or ""),
        )
        for edit in values.get("edits") or []
        if isinstance(edit, dict)
    ]


def hook_stdout(findings: list[dict]) -> tuple[dict, int]:
    """Cursor PreToolUse requires JSON on stdout; non-JSON is fail-closed."""
    blocking = [item for item in findings if item["severity"] == "block"]
    if blocking:
        message = render(findings)
        return (
            {
                "permission": "deny",
                "agent_message": message,
                "user_message": message,
            },
            2,
        )
    body: dict = {"permission": "allow"}
    if findings:
        body["agent_message"] = render(findings)
    return body, 0


def _compare_ref(branch: str, repo: Path) -> str:
    """origin/master, or the fork point when the branch's plan is stacked on another branch."""
    try:
        return diff_base(ROOT, branch, repo)
    except ManifestError:
        return "origin/master"
    except VerificationError as exc:
        raise ConventionError(str(exc)) from exc


def changed_content(branch: str) -> list[tuple[str, str]]:
    base = ROOT / "worktrees" / branch
    changed: list[tuple[str, str]] = []
    for repo_name in FEATURE_REPOS:
        repo = base / repo_name
        if not repo.is_dir():
            continue
        diff = subprocess.run(
            ["git", "diff", "--unified=1", _compare_ref(branch, repo), "--", "*.cs", "*.rego"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if diff.returncode:
            raise ConventionError(f"cannot read {repo_name} diff: {diff.stderr.strip()}")
        current = ""
        additions: list[str] = []
        for line in diff.stdout.splitlines():
            if line.startswith("+++ b/"):
                if current and additions:
                    changed.append((f"{repo_name}/{current}", "\n".join(additions)))
                current = line[6:]
                additions = []
            elif line.startswith("+") and not line.startswith("+++"):
                additions.append(line[1:])
        if current and additions:
            changed.append((f"{repo_name}/{current}", "\n".join(additions)))
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "*.cs", "*.rego"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        for rel in untracked.stdout.splitlines():
            path = repo / rel
            changed.append((f"{repo_name}/{rel}", path.read_text(encoding="utf-8", errors="replace")))
    return changed


def render(findings: list[dict]) -> str:
    return "\n".join(
        f"{'BLOCKED' if item['severity'] == 'block' else 'WARNING'} "
        f"[{item['rule']}] {item['path']}: {item['message']}"
        for item in findings
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    sub.add_parser("hook")
    file_cmd = sub.add_parser("check-file")
    file_cmd.add_argument("path")
    file_cmd.add_argument("--content-file", default="")
    diff_cmd = sub.add_parser("check-diff")
    diff_cmd.add_argument("branch")
    args = parser.parse_args()
    try:
        if args.command == "validate":
            errors = validate_config(load_json(REGISTRY), load_json(ALLOWLIST))
            if errors:
                raise ConventionError("; ".join(errors))
            print("OK convention registry and allowlist")
            return 0
        if args.command == "hook":
            payload = json.load(sys.stdin)
            findings = [
                finding
                for path, content, baseline in hook_payload(payload)
                for finding in hook_findings(path, content, baseline)
            ]
            body, code = hook_stdout(findings)
            print(json.dumps(body))
            if code:
                print(render(findings), file=sys.stderr)
            return code
        elif args.command == "check-file":
            content = (
                Path(args.content_file).read_text(encoding="utf-8", errors="replace")
                if args.content_file
                else Path(args.path).read_text(encoding="utf-8", errors="replace")
            )
            findings = check(args.path, content)
        else:
            findings = [finding for path, content in changed_content(args.branch) for finding in check(path, content)]
        if findings:
            blocking = [item for item in findings if item["severity"] == "block"]
            print(render(findings), file=sys.stderr if blocking else sys.stdout)
            return 2 if blocking else 0
        print("OK no convention violations")
        return 0
    except (ConventionError, OSError, json.JSONDecodeError) as exc:
        message = f"CONVENTION_CHECK_ERROR: {exc}"
        if args.command == "hook":
            print(
                json.dumps(
                    {
                        "permission": "deny",
                        "agent_message": message,
                        "user_message": message,
                    }
                )
            )
        print(message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
