#!/usr/bin/env python3
"""Detached, fresh-context implementation pipeline for the Apaleo workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(SCRIPT_DIR))

from assemble_prompt import DEFAULT_REFS_BY_STAGE, assemble  # noqa: E402
from common import FEATURE_REPOS  # noqa: E402
from models import models_match, parse_stream_json  # noqa: E402
from pipeline_manifest import (  # noqa: E402
    AI_STAGES,
    ManifestError,
    STAGE_ORDER,
    find_plan_dir,
    load_manifest,
    path_allowed,
    plan_branch_dir,
    route_text,
    runtime_manifest,
    task_base_branch,
    selected_stages,
    stage_routes,
)
from pipeline_state import (  # noqa: E402
    bind_plan,
    invalidate_from,
    load as load_state,
    mark_complete,
    mark_failed,
    mark_started,
    normalize_completed_prefix,
    remaining,
    safe_task,
    save as save_state,
    state_path,
    utc_now,
)
from stage_result import (  # noqa: E402
    classify,
    classify_failure,
    health_failure_reason,
    last_terminal_line,
    load_json,
    provider_diagnostic_text,
)
from verification import (  # noqa: E402
    VerificationError,
    assert_no_new_decisions,
    assert_review_gates,
    diff_fingerprint,
    precommit_scan,
    validate_red_proof,
    verify as verify_implementation,
)
from untrusted_input import sanitize, wrap_data  # noqa: E402


RUNS_DIR = ROOT / ".local" / "pipeline-runs"
LOCKS_DIR = ROOT / ".local" / "pipeline-locks"
HEALTH_DIR = ROOT / ".local" / "pipeline-health"
LIVE_DIR = RUNS_DIR
REPOS = FEATURE_REPOS


class PipelineError(RuntimeError):
    pass


class PipelineInputRequired(PipelineError):
    pass


@dataclass
class AttemptResult:
    outcome: str
    reason: str
    failure_class: str
    provider: str
    model: str
    session_id: str
    seconds: int
    changed_paths: list[str]
    output_text: Path
    output_json: Path
    resumable: bool
    requires_user: bool


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def canonical_task(value: str) -> str:
    """Use one state/progress key for every common spelling of an HC task."""
    match = re.search(r"(?i)(?:^|[/_-])h?c[-_ ]?(\d+)(?:$|[/_-])", value.strip())
    return f"HC-{match.group(1)}" if match else value.strip()


def attempt_stem(
    stage: str, route: dict, route_index: int, attempt: int, continuation: int = 0
) -> str:
    model_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", route["model"])
    stem = f"{stage}.route-{route_index}-{route['provider']}-{model_slug}.attempt-{attempt}"
    return f"{stem}.continuation-{continuation}" if continuation else stem


def live_status_path(task: str) -> Path:
    return LIVE_DIR / f"live-{safe_task(task)}.status.json"


def live_last_path(task: str) -> Path:
    return LIVE_DIR / f"live-{safe_task(task)}.last.json"


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        status = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return True
    return not status.startswith("Z")


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


class Reporter:
    def __init__(self, task: str, run_dir: Path, update_every: int) -> None:
        self.task = task
        self.run_dir = run_dir
        self.events_path = run_dir / "events.jsonl"
        self.update_every = update_every
        self.current_stage = "preflight"

    def emit(self, event: str, **values: Any) -> None:
        payload = {
            "when": utc_now(),
            "when_unix": int(time.time()),
            "event": event,
            "task": self.task,
            "pid": os.getpid(),
            "run_dir": str(self.run_dir),
            **values,
        }
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
        status = {
            "task": self.task,
            "pid": os.getpid(),
            "run_dir": str(self.run_dir),
            "stage": values.get("stage", self.current_stage),
            "event": event,
            "message": values.get("message", ""),
            "updated": payload["when"],
            "updated_unix": payload["when_unix"],
        }
        self.current_stage = str(status["stage"] or self.current_stage)
        atomic_json(live_status_path(self.task), status)
        print(format_event(payload), flush=True)


def format_event(event: dict) -> str:
    when = event.get("when", "")
    kind = event.get("event", "event")
    stage = event.get("stage")
    message = event.get("message") or ""
    route = ""
    if event.get("provider"):
        route = f" [{event['provider']}:{event.get('model', '')}]"
    label = f"/{stage}" if stage else "pipeline"
    return f"[{when}] {label}{route} {kind}: {message}".rstrip()


def infer_task() -> str:
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        branch = ""
    if branch and branch not in {"master", "main", "HEAD"}:
        return branch
    raise PipelineError("task or full feature branch is required outside a feature worktree")


def find_cursor() -> str:
    for candidate in (
        shutil.which("agent"),
        shutil.which("cursor-agent"),
        str(Path.home() / ".local/bin/agent"),
        str(Path.home() / ".local/bin/cursor-agent"),
    ):
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return ""


def find_codex() -> str:
    for candidate in (
        shutil.which("codex"),
        str(Path.home() / ".local/bin/codex"),
        "/opt/homebrew/bin/codex",
        "/usr/local/bin/codex",
    ):
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return ""


def find_claude() -> str:
    for candidate in (
        shutil.which("claude"),
        str(Path.home() / ".local/bin/claude"),
        "/opt/homebrew/bin/claude",
        "/usr/local/bin/claude",
    ):
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return ""


def worktrees(branch: str) -> dict[str, Path]:
    base = ROOT / "worktrees" / branch
    return {repo: base / repo for repo in REPOS if (base / repo).is_dir()}


def git(path: Path, *args: str, timeout: int = 60, check: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and result.returncode:
        raise PipelineError(
            f"git {' '.join(args)} failed in {path}: {(result.stderr or result.stdout).strip()}"
        )
    return result


def dirty_paths(repo: Path) -> dict[str, str]:
    raw = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        capture_output=True,
        timeout=30,
    ).stdout
    chunks = raw.split(b"\0")
    paths: list[str] = []
    index = 0
    while index < len(chunks):
        entry = chunks[index]
        index += 1
        if not entry:
            continue
        text = entry.decode("utf-8", errors="replace")
        status = text[:2]
        path = text[3:] if len(text) > 3 else ""
        if path:
            paths.append(path)
        if ("R" in status or "C" in status) and index < len(chunks):
            other = chunks[index].decode("utf-8", errors="replace")
            index += 1
            if other:
                paths.append(other)
    result: dict[str, str] = {}
    for relative in paths:
        absolute = repo / relative
        if absolute.is_file():
            digest = hashlib.sha256(absolute.read_bytes()).hexdigest()
        elif absolute.exists():
            digest = "present"
        else:
            digest = "deleted"
        result[relative] = digest
    return result


def snapshot(branch: str) -> dict:
    repos: dict[str, dict] = {}
    for name, path in worktrees(branch).items():
        repos[name] = {
            "head": git(path, "rev-parse", "HEAD", check=True).stdout.strip(),
            "dirty": dirty_paths(path),
        }
    return repos


def working_paths(branch: str) -> list[str]:
    return sorted(
        f"{name}/{path}"
        for name, repo in worktrees(branch).items()
        for path in dirty_paths(repo)
    )


def repositories_with_base_diff(branch: str) -> dict[str, Path]:
    """Return exactly the worktree repositories that require a PR."""
    changed: dict[str, Path] = {}
    base_ref = f"origin/{task_base_branch(ROOT, branch)}"
    for name, repo in worktrees(branch).items():
        result = git(repo, "diff", "--quiet", f"{base_ref}...HEAD")
        if result.returncode == 1:
            changed[name] = repo
        elif result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise PipelineError(
                f"cannot compare {name} with {base_ref} before draft verification: {detail}"
            )
    return changed


def parked_main_snapshot() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for name in REPOS:
        path = ROOT / name
        if not path.is_dir():
            continue
        result[name] = {
            "branch": git(path, "branch", "--show-current").stdout.strip(),
            "head": git(path, "rev-parse", "HEAD", check=True).stdout.strip(),
            "dirty": dirty_paths(path),
        }
    return result


def ensure_parked_mains_unchanged(before: dict[str, dict]) -> None:
    after = parked_main_snapshot()
    changed = [name for name in sorted(set(before) | set(after)) if before.get(name) != after.get(name)]
    if changed:
        raise PipelineError(
            "parked main checkout changed during the stage: " + ", ".join(changed)
        )


def plan_contract_path(plan_dir: Path, name: str) -> Path:
    versioned = plan_dir / name
    if versioned.is_file():
        return versioned
    return plan_branch_dir(plan_dir) / name


def plan_contract_snapshot(plan_dir: Path) -> dict[str, str]:
    files = (
        plan_contract_path(plan_dir, "prompt.md"),
        plan_dir / "product.md",
        plan_dir / "implementation.md",
        plan_contract_path(plan_dir, "deferred-scope.md"),
        plan_dir / "pipeline.json",
    )
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files
        if path.is_file()
    }


def ensure_plan_contract_unchanged(plan_dir: Path, before: dict[str, str]) -> None:
    """Plan changes are accepted; the next run rebinds state to their new fingerprint."""
    after = plan_contract_snapshot(plan_dir)
    if after != before:
        return


def plan_contract_fingerprint(plan_dir: Path) -> str:
    snapshot = plan_contract_snapshot(plan_dir)
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def workflow_policy_snapshot(stage: str) -> dict[str, str]:
    """Snapshot only policy that the active stage actually receives or runs.

    A detached provider already has its prompt. An unrelated edit to another
    skill, the workflow guide, or a publishing helper must not invalidate that
    provider's completed work. The plan contract and worktree boundaries are
    still checked independently.
    """
    skills = ROOT / ".claude" / "skills"
    paths = [ROOT / "AGENTS.md", skills / stage / "SKILL.md"]
    for ref in DEFAULT_REFS_BY_STAGE.get(stage, []):
        if ref.endswith(".md"):
            paths.append(skills / "references" / ref)
    if stage == "implement":
        paths.append(skills / "test-and-fix" / "SKILL.md")
    if stage in {"commit-and-push", "draft-pr"}:
        paths.extend(path for path in (skills / stage).glob("*.sh"))
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
        if path.is_file()
    }


def ensure_workflow_policy_unchanged(stage: str, before: dict[str, str]) -> list[str]:
    """Return active-policy changes without invalidating an in-flight session.

    The provider prompt and a script's executable path are fixed at launch.
    Applying a policy edit retroactively would make an already-completed stage
    non-reproducible, while treating it as advisory lets the next fresh stage
    use the current policy. Worktree and plan-contract checks remain gates.
    """
    after = workflow_policy_snapshot(stage)
    if after != before:
        changed = sorted(set(before) ^ set(after))
        changed += sorted(path for path in set(before) & set(after) if before[path] != after[path])
        return changed
    return []


def snapshot_delta(before: dict, after: dict) -> list[str]:
    changed: set[str] = set()
    for repo in set(before) | set(after):
        left = before.get(repo, {"dirty": {}, "head": ""})
        right = after.get(repo, {"dirty": {}, "head": ""})
        for path in set(left["dirty"]) | set(right["dirty"]):
            if left["dirty"].get(path) != right["dirty"].get(path):
                changed.add(f"{repo}/{path}")
        if left.get("head") != right.get("head"):
            changed.add(f"{repo}/.git/HEAD")
    return sorted(changed)


def stage_paths_allowed(stage: str, paths: list[str], manifest: dict) -> bool:
    if not paths:
        return True
    allowed = manifest.get("allowed_paths") or []
    tests = manifest.get("test_paths") or []
    for path in paths:
        if path.endswith("/.git/HEAD"):
            return False
        if stage == "implement-tests":
            if not path_allowed(path, tests):
                return False
        elif stage == "implement":
            if not path_allowed(path, allowed) and not path_allowed(path, tests):
                return False
        elif stage == "review":
            if not path_allowed(path, allowed) and not path_allowed(path, tests):
                return False
    return True


def acquire_lock(task: str, force: bool) -> Path:
    lock = LOCKS_DIR / f"{safe_task(task)}.lock"
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError:
        pid_file = lock / "pid"
        try:
            holder = int(pid_file.read_text().strip())
        except (OSError, ValueError):
            holder = 0
        if pid_alive(holder) and not force:
            raise PipelineError(f"another run is active for {task} (pid {holder})")
        if pid_alive(holder) and force:
            raise PipelineError(
                f"refusing to take over a live run (pid {holder}); stop it explicitly first"
            )
        if pid_file.exists():
            pid_file.unlink()
        lock.rmdir()
        lock.mkdir()
    (lock / "pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    return lock


def release_lock(lock: Path | None) -> None:
    if not lock or not lock.is_dir():
        return
    pid_file = lock / "pid"
    try:
        if pid_file.is_file() and int(pid_file.read_text().strip()) == os.getpid():
            pid_file.unlink()
            lock.rmdir()
    except (OSError, ValueError):
        pass


def health_cache_path(route: dict) -> Path:
    key = re.sub(r"[^A-Za-z0-9._-]+", "_", route_text(route))
    return HEALTH_DIR / f"{key}.json"


def provider_wide_failure(provider: str, reason: str) -> bool:
    """Whether a failure must suppress every route from one provider.

    Cursor's hosted-model allowance is model-scoped: after a Claude/GPT limit,
    the explicitly approved Cursor Grok fallback must remain eligible. Authentication
    and account-state failures still apply to every Cursor route.
    """
    if provider == "cursor":
        return bool(
            re.search(
                r"invalid api key|authentication failed|failed to authenticate|"
                r"oauth session expired|unauthenticated|account.*(?:disabled|suspended)",
                reason,
                re.I,
            )
        )
    return bool(
        re.search(
            r"spend limit|usage[- ]credits?|insufficient (?:quota|credits?)|billing|"
            r"invalid api key|authentication failed|failed to authenticate|"
            r"oauth session expired|unauthenticated|account.*(?:disabled|suspended)",
            reason,
            re.I,
        )
    )


def include_retry_after(reason: str, haystack: str) -> str:
    """Preserve a provider's retry hint after concise failure classification."""
    match = re.search(r"retry[- ]after\D{0,20}(\d+)", haystack, re.I)
    if not match or re.search(r"retry[- ]after", reason, re.I):
        return reason
    return f"{reason}; retry-after={match.group(1)}".strip("; ")


def recoverable_block_reason(stage: str, reason: str) -> bool:
    """Reject user-input escalation for known reversible execution work."""
    text = reason.lower()
    infrastructure = bool(
        re.search(
            r"docker|registry|image pull|compose|connection reset|network timeout|"
            r"stack lock|local api (?:container|image)|container (?:swap|replacement|restart)",
            text,
        )
    )
    code_generation = bool(re.search(r"swagger|proxy (?:generation|regeneration)|regenerate.*proxy", text))
    mechanical_test = stage in {"implement", "review"} and bool(
        re.search(
            r"test (?:fixture|helper|setup)|fixture|helper.*(?:null|default|coalesc)|"
            r"(?:missing|wrong|renamed) (?:member|property)|does not contain a definition|"
            r"compile.*test|test.*compile",
            text,
        )
    )
    return infrastructure or code_generation or mechanical_test


def concrete_user_action(reason: str) -> bool:
    """Identify an explicit action the detached worker cannot perform itself."""
    return bool(
        re.search(
            r"(?:please|you must|user must|requires? you to) (?:manually )?"
            r"(?:install|sign in|log in|authenticate|unlock|approve in system settings|restart the host|"
            r"start docker manually)|manual installation|required credentials?",
            reason,
            re.I,
        )
    )


def probe_route(route: dict, no_probe: bool) -> tuple[bool, str, str]:
    provider = route["provider"]
    model = route["model"]
    if os.environ.get("PIPELINE_FAKE_HEALTH") == "1":
        return True, "healthy", "fake health enabled"
    binary = {
        "codex": find_codex,
        "cursor": find_cursor,
        "claude": find_claude,
    }[provider]()
    if not binary:
        return False, "permanent_provider", f"{provider} CLI not found"
    if no_probe:
        return True, "healthy", f"{provider} CLI present; active probe disabled"
    cache = health_cache_path(route)
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        if data.get("ok") and time.time() - float(data.get("checked_unix") or 0) < 600:
            return True, "healthy", "cached probe (<10m)"
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    HEALTH_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pipeline-health-") as tmp:
        out = Path(tmp) / "out.jsonl"
        last = Path(tmp) / "last.txt"
        if provider == "cursor":
            cmd = [
                binary,
                "-p",
                "--output-format",
                "stream-json",
                "--mode",
                "ask",
                "--trust",
                "--workspace",
                str(ROOT),
                "--model",
                model,
                "Reply exactly READY. Do not use tools.",
            ]
        elif provider == "codex":
            cmd = [
                binary,
                "exec",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "-C",
                str(ROOT),
                "--model",
                model,
                *(["-c", f'model_reasoning_effort="{route["reasoning"]}"'] if route.get("reasoning") else []),
                "--json",
                "-o",
                str(last),
                "Reply exactly READY. Do not use tools.",
            ]
        else:
            cmd = [
                binary,
                "-p",
                "--output-format",
                "json",
                "--model",
                model,
                *(["--effort", route["reasoning"]] if route.get("reasoning") else []),
                "--no-session-persistence",
                "Reply exactly READY. Do not use tools.",
            ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            raw = (result.stdout or "") + "\n" + (result.stderr or "")
            if last.is_file():
                raw += "\n" + last.read_text(encoding="utf-8", errors="replace")
            out.write_text(raw, encoding="utf-8")
        except subprocess.TimeoutExpired as exc:
            raw = f"health probe timeout: {exc}"
            result = subprocess.CompletedProcess(cmd, 124, "", raw)
        failure_class, matched = classify_failure(raw)
        ok = result.returncode == 0 and "READY" in raw.upper()
        if ok and provider == "cursor":
            parsed = parse_stream_json(out)
            actual = str(parsed.get("model_actual") or "")
            if not models_match(model, actual):
                ok = False
                failure_class = "permanent_provider"
                matched = f"model mismatch: expected {model}, got {actual or 'empty'}"
        if not ok and failure_class == "semantic":
            failure_class = "transient_provider" if result.returncode in {124, 137, 143} else "permanent_provider"
        reason = "READY" if ok else health_failure_reason(raw, matched, result.returncode)
        if not ok:
            reason = include_retry_after(reason, raw)
        atomic_json(
            cache,
            {"ok": ok, "class": failure_class, "reason": reason, "checked_unix": int(time.time())},
        )
        return ok, "healthy" if ok else failure_class, reason


def preflight(
    task: str,
    branch: str,
    plan_dir: Path,
    manifest: dict,
    stages: list[str],
    no_probe: bool,
    max_provider_retries: int,
    docker_start_timeout: int,
    reporter: Reporter,
) -> tuple[dict[str, tuple[bool, str, str]], set[str]]:
    problems: list[str] = []
    notes: list[str] = []
    repos = worktrees(branch)
    if not repos:
        problems.append(f"no feature worktree found: {ROOT / 'worktrees' / branch}")
    for main in REPOS:
        path = ROOT / main
        if not path.is_dir():
            continue
        current = git(path, "branch", "--show-current").stdout.strip()
        if current != "master":
            problems.append(f"parked main {main} is on {current or '<detached>'}, expected master")
        dirty = dirty_paths(path)
        if dirty:
            notes.append(
                f"parked main {main} has pinned pre-existing dirt: {', '.join(sorted(dirty))}"
            )
        if git(path, "rev-parse", "--verify", "origin/master").returncode == 0:
            ahead = git(path, "rev-list", "--count", "origin/master..HEAD").stdout.strip()
            if ahead and int(ahead) > 0:
                problems.append(f"parked main {main} is ahead of origin/master by {ahead} commit(s)")
    for name, path in repos.items():
        current = git(path, "branch", "--show-current").stdout.strip()
        if current != branch:
            problems.append(f"{name} worktree is on {current or '<detached>'}, expected {branch}")
    current_dirty = working_paths(branch)
    if current_dirty and not stages:
        problems.append(
            "all selected stages are recorded complete but the worktree is dirty; "
            "rerun from the appropriate stage or use --no-resume"
        )
    if current_dirty and stages:
        first = stages[0]
        allowed = manifest.get("allowed_paths") or []
        tests = manifest.get("test_paths") or []
        for path in current_dirty:
            in_product = path_allowed(path, allowed) and not path_allowed(path, tests)
            in_tests = path_allowed(path, tests)
            acceptable = in_tests if first == "implement-tests" else (in_product or in_tests)
            if first == "draft-pr":
                acceptable = False
            if not acceptable:
                problems.append(
                    f"dirty path is not a valid recovery input for first stage {first}: {path}"
                )
    for required in (
        plan_contract_path(plan_dir, "prompt.md"),
        plan_dir / "product.md",
        plan_dir / "implementation.md",
        plan_contract_path(plan_dir, "deferred-scope.md"),
        plan_dir / "pipeline.json",
    ):
        if not required.is_file():
            problems.append(f"required plan artifact missing: {required}")
    planned_repos = {
        path.split("/", 1)[0]
        for path in [*(manifest.get("allowed_paths") or []), *(manifest.get("test_paths") or [])]
    }
    for repo in sorted(planned_repos):
        if repo not in repos:
            problems.append(f"manifest names {repo} paths but its feature worktree is missing")
    if "commit-and-push" in stages:
        script = ROOT / ".claude/skills/commit-and-push/commit-and-push.sh"
        if not script.is_file():
            problems.append(f"commit script missing: {script}")
    if "draft-pr" in stages:
        script = ROOT / ".claude/skills/draft-pr/draft-pr.sh"
        if not script.is_file():
            problems.append(f"draft PR script missing: {script}")
        gh = shutil.which("gh")
        if not gh:
            problems.append("gh CLI not found")
        else:
            auth = subprocess.run([gh, "auth", "status"], capture_output=True, text=True, timeout=30)
            if auth.returncode:
                problems.append("gh authentication is not healthy")
    if manifest.get("e2e_required") and "implement" in stages:
        docker = shutil.which("docker")
        if not docker:
            problems.append(
                "Docker is required for selected E2E validation but is not installed; "
                "user intervention is required"
            )
        else:
            def docker_ready() -> bool:
                try:
                    return subprocess.run(
                        [docker, "info"], capture_output=True, timeout=30
                    ).returncode == 0
                except subprocess.TimeoutExpired:
                    return False

            if not docker_ready():
                reporter.emit(
                    "docker_recovery_started",
                    stage="preflight",
                    message=f"Docker is unavailable; starting/waiting up to {docker_start_timeout}s",
                )
                opener = shutil.which("open")
                if opener and sys.platform == "darwin":
                    subprocess.run(
                        [opener, "-a", "Docker"], capture_output=True, timeout=30
                    )
                deadline = time.time() + docker_start_timeout
                next_update = 0.0
                while time.time() < deadline and not docker_ready():
                    if time.time() >= next_update:
                        remaining_seconds = max(0, int(deadline - time.time()))
                        reporter.emit(
                            "docker_recovery_waiting",
                            stage="preflight",
                            message=f"waiting for Docker; {remaining_seconds}s remain",
                        )
                        next_update = time.time() + 30
                    time.sleep(5)
                if docker_ready():
                    reporter.emit(
                        "docker_recovered",
                        stage="preflight",
                        message="Docker is healthy; continuing automatically",
                    )
                else:
                    problems.append(
                        "Docker could not be started automatically; user intervention is required"
                    )
    try:
        free = shutil.disk_usage(ROOT).free
        if free < 5 * 1024**3:
            notes.append(f"low disk space: {free // 1024**2} MiB free")
    except OSError:
        notes.append("disk space could not be checked")

    health: dict[str, tuple[bool, str, str]] = {}
    provider_circuits: set[str] = set()
    for stage in stages:
        if stage not in AI_STAGES:
            continue
        healthy_route = False
        for route in stage_routes(manifest, stage):
            key = route_text(route)
            if route["provider"] in provider_circuits:
                health[key] = (False, "permanent_provider", "provider circuit already open")
                continue
            result = probe_route(route, no_probe)
            for health_attempt in range(1, max_provider_retries + 1):
                if result[0] or result[1] not in {"transient_provider", "provider_stall"}:
                    break
                delay = 10
                retry_after = re.search(r"retry-after\D+(\d+)", result[2], re.I)
                if retry_after:
                    delay = min(120, max(1, int(retry_after.group(1))))
                reporter.emit(
                    "route_health_retry",
                    stage=stage,
                    provider=route["provider"],
                    model=route["model"],
                    message=f"fresh health probe {health_attempt + 1} in {delay}s",
                )
                time.sleep(delay)
                result = probe_route(route, no_probe)
            health[key] = result
            ok, failure_class, reason = result
            reporter.emit(
                "route_health",
                stage=stage,
                provider=route["provider"],
                model=route["model"],
                message=("healthy" if ok else f"{failure_class}: {reason[:180]}"),
            )
            healthy_route = healthy_route or ok
            if not ok and failure_class == "permanent_provider" and provider_wide_failure(
                route["provider"], reason
            ):
                provider_circuits.add(route["provider"])
        if not healthy_route:
            problems.append(f"{stage}: no approved route passed preflight")
    report = ["# Implement pipeline preflight", "", f"- Task: `{task}`", f"- Branch: `{branch}`"]
    report += [f"- Plan: `{plan_dir}`", f"- Stages: `{', '.join(stages)}`", ""]
    report += ["## Routes", ""]
    for key, (ok, klass, reason) in health.items():
        report.append(f"- `{key}`: {'OK' if ok else 'FAIL'} — {klass}: {reason}")
    if notes:
        for note in notes:
            reporter.emit("preflight_note", stage="preflight", message=note)
        report += ["", "## Notes", "", *[f"- {note}" for note in notes]]
    if problems:
        report += ["", "## Fatal", "", *[f"- {problem}" for problem in problems]]
    (reporter.run_dir / "preflight.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    if problems:
        reporter.current_stage = "preflight"
        reason = "; ".join(problems)
        if "user intervention is required" in reason:
            raise PipelineInputRequired(reason)
        raise PipelineError(reason)
    return health, provider_circuits


def sync_master(branch: str, reporter: Reporter) -> None:
    repos = worktrees(branch)
    if any(dirty_paths(path) for path in repos.values()):
        reporter.emit("sync_skipped", stage="preflight", message="worktree already has changes")
        return
    # A stacked plan follows the branch it was cut from; master reaches it through that branch.
    base = task_base_branch(ROOT, branch)
    for name, path in repos.items():
        git(path, "fetch", "--prune", "origin", base, timeout=180, check=True)
        behind = git(path, "rev-list", "--count", f"HEAD..origin/{base}", check=True).stdout.strip()
        if behind and int(behind) > 0:
            merge = git(path, "merge", "--no-edit", f"origin/{base}", timeout=300)
            if merge.returncode:
                git(path, "merge", "--abort")
                raise PipelineError(f"sync conflict with origin/{base} in {name}; merge aborted")
            reporter.emit("synced", stage="preflight", message=f"merged origin/{base} into {name}")


def stage_context(
    stage: str,
    task: str,
    branch: str,
    plan_dir: Path,
    recovery_packets: list[Path] | None = None,
    manifest: dict | None = None,
) -> str:
    manifest = manifest or {}
    contract = (manifest.get("context_contracts") or {}).get(stage) or {}
    contract_text = (
        f"Context contract — reads: {', '.join(contract.get('reads') or [])}; "
        f"denied: {', '.join(contract.get('denied') or [])}; "
        f"writes: {', '.join(contract.get('writes') or [])}."
    )
    special = {
        "implement-tests": (
            "Implement the complete plan-specified test suite before product code. Modify only the "
            "manifest's test_paths. Prefer E2E coverage; add unit/policy tests where the plan requires. "
            "Do not read product source paths under change or prior implementation attempts. Run the "
            "narrowest useful red-phase checks and prove assertion-level failure; compilation/type failure "
            "is invalid. Never change product code, generated product clients, or weaken an assertion. "
            "Write red-proof.md and a new tests-implementation-<n>.md report in the mutable artifact directory. "
            "In red-proof.md, cite every changed test file as a $ROOT-relative path in backticks "
            "(`apaleo/test/...`, `development/src/tests/...`); repo-relative `test/...` under an "
            "`apaleo:` heading is not enough for the post-stage gate."
        ),
        "implement": (
            "Implement the plan, then progressively load and execute /test-and-fix inside this same provider "
            "session. Do not read prompt.md/the specify transcript or prior provider rationale. Treat red tests "
            "as the contract during construction. In the verification/fix subphase, a test may change only for "
            "a plan-settled fixture/setup defect; never weaken, skip, delete, quarantine, or loosen assertions. "
            "Run every manifest test command through the deterministic verification helper until it parses green: "
            f"python3 {ROOT / '.claude/skills/pipeline/verification.py'} {task!r} --root {str(ROOT)!r} --force. "
            "Perform required Swagger/proxy generation and local E2E autonomously with the stack lock and "
            "mandatory restoration. Do not self-review or write a review artifact."
        ),
        "review": (
            "Review from scratch with no implementation-session context. Inspect only the actual diff, confirmed "
            "plan, test evidence, and applicable rules. The supplied convention inventory is the authoritative "
            "/add-rule output: apply its path scopes, inspect every Tier 2 match, and semantically check every "
            "applicable Tier 3 statement. Review in this order: specification violations, test gaps, "
            "correctness, then rules/conventions and repository-wide semantic reuse/DRY. Do not make a new "
            "product or architecture decision, but apply unambiguous plan-authorized correctness fixes "
            "and same-behavior convention/DRY improvements within manifest paths. A detected Tier 1 violation "
            "is not advisory: repair it before completing the stage. After each repair, run the "
            "narrowest affected named check and record its evidence; stop after three repair/verify cycles and "
            "record only unresolved plan/behavior findings as advisory. Run the deterministic diff-scoped "
            f"convention scan before completion: python3 {ROOT / '.claude/skills/pipeline/verification.py'} "
            f"{branch!r} --root {str(ROOT)!r} --precommit. "
            "Write a new review-<n>.md artifact with AC evidence and both audit declarations when possible. "
            "Every finding needs file:line and a concrete failure scenario; write none for clean sections. "
            "Plan/behavior findings, incomplete evidence, and environment failures are advisory; a Tier 1 scanner failure is enforced. "
            "Do not read progress.md, "
            "tests-implementation reports, recovery packets, provider output, or prior-agent rationale. "
            "Do not switch stacks/images or rerun E2E during review."
        ),
    }[stage]
    handoff = (
        "For review, shared context is limited to the confirmed plan, current worktree and tests, "
        "and git diff."
        if stage == "review"
        else "Shared context is limited to the filesystem: the confirmed plan, current worktree, "
        "stage reports, and git diff."
    )
    recovery = ""
    if recovery_packets and stage != "review":
        recovery = "\nRecovery packets from failed fresh attempts:\n" + "\n".join(
            f"- `{path}`" for path in recovery_packets
        )
        recovery += "\nAudit the current filesystem before continuing; do not assume partial work is correct.\n"
    legacy = ""
    if stage == "implement" and manifest.get("implementation_verification", {}).get(
        "legacy_test_and_fix_selected"
    ):
        legacy = (
            "\nThis immutable v1 plan selected test-and-fix. Execute that complete procedure here and "
            "write a new test-report-<n>.md for compatibility; do not launch another provider session.\n"
        )
    return f"""
Run the selected `/{stage}` stage for `{task}`.

This stage starts in a brand-new provider session. Do not infer or request context from another
stage or agent session. {handoff} The orchestrator may resume this exact session only after this
stage itself genuinely requires user input.

- Root: `{ROOT}`
- Branch: `{branch}`
- Plan directory: `{plan_dir}`
- Mutable artifact directory: `{plan_branch_dir(plan_dir)}`
- Worktree: `{ROOT / 'worktrees' / branch}`

{special}

{contract_text}

No stage report may introduce a product or architectural decision. If the confirmed plan does not
settle a necessary choice, record `PLAN_DEFECT` in a complete plan revision; the next run rebinds
automatically instead of requiring a specific version directory.
{legacy}
{recovery}
Implementation and publish safety gates fail closed; review is advisory. Exhaust safe in-scope work, retries, local recovery, and reversible
operations before stopping. Do not ask permission for a local operation that the plan requires and
the workflow makes reversible. Do not emit PIPELINE_STAGE_SKIPPED. End with exactly one terminal line:

PIPELINE_STAGE_OK: {stage}

Only when progress is impossible without a decision or external action solely the user can provide,
end with `PIPELINE_INPUT_REQUIRED` followed by the minimum numbered questions. The orchestrator will
preserve and resume this exact provider session after the answer. Do not use `PIPELINE_BLOCKED` for
transient infrastructure, local container/image replacement, mechanical test defects, or work owned
by a later selected stage. Do not commit or push.
""".strip()


def provider_command(
    route: dict,
    prompt: str,
    out_text: Path,
) -> list[str]:
    if route["provider"] == "cursor":
        binary = find_cursor()
        if not binary:
            raise PipelineError("Cursor agent CLI not found")
        return [
            binary,
            "-p",
            "--output-format",
            "stream-json",
            "--stream-partial-output",
            "--workspace",
            str(ROOT),
            "--model",
            route["model"],
            "--yolo",
            "--trust",
            prompt,
        ]
    if route["provider"] == "codex":
        binary = find_codex()
        if not binary:
            raise PipelineError("Codex CLI not found")
        return [
            binary,
            "exec",
            "--skip-git-repo-check",
            "-C",
            str(ROOT),
            "--model",
            route["model"],
            *(["-c", f'model_reasoning_effort="{route["reasoning"]}"'] if route.get("reasoning") else []),
            "--dangerously-bypass-approvals-and-sandbox",
            "--json",
            "-o",
            str(out_text),
            prompt,
        ]
    binary = find_claude()
    if not binary:
        raise PipelineError("Claude CLI not found")
    return [
        binary,
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--model",
        route["model"],
        *(["--effort", route["reasoning"]] if route.get("reasoning") else []),
        "--dangerously-skip-permissions",
        prompt,
    ]


def provider_resume_command(
    route: dict,
    session_id: str,
    prompt: str,
    out_text: Path,
) -> list[str]:
    """Continue one paused stage in its exact provider session."""
    if not session_id:
        raise PipelineError("paused stage has no resumable provider session id")
    if route["provider"] == "cursor":
        binary = find_cursor()
        if not binary:
            raise PipelineError("Cursor agent CLI not found")
        return [
            binary,
            "-p",
            "--resume",
            session_id,
            "--output-format",
            "stream-json",
            "--stream-partial-output",
            "--workspace",
            str(ROOT),
            "--model",
            route["model"],
            "--yolo",
            "--trust",
            prompt,
        ]
    if route["provider"] == "codex":
        binary = find_codex()
        if not binary:
            raise PipelineError("Codex CLI not found")
        return [
            binary,
            "exec",
            "resume",
            "--skip-git-repo-check",
            "--model",
            route["model"],
            *(["-c", f'model_reasoning_effort="{route["reasoning"]}"'] if route.get("reasoning") else []),
            "--dangerously-bypass-approvals-and-sandbox",
            "--json",
            "-o",
            str(out_text),
            session_id,
            prompt,
        ]
    binary = find_claude()
    if not binary:
        raise PipelineError("Claude CLI not found")
    return [
        binary,
        "-p",
        "--resume",
        session_id,
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--model",
        route["model"],
        *(["--effort", route["reasoning"]] if route.get("reasoning") else []),
        "--dangerously-skip-permissions",
        prompt,
    ]


def terminate_process_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.time() + 15
    while process.poll() is None and time.time() < deadline:
        time.sleep(0.25)
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass


def run_monitored(
    cmd: list[str],
    out_json: Path,
    err_file: Path,
    *,
    stage: str,
    route: dict,
    reporter: Reporter,
    update_every: int,
    inactive_warning: int,
    inactive_timeout: int,
    total_timeout: int,
    tool_call_grace: int,
) -> tuple[int, str]:
    started = time.time()
    last_activity = started
    last_heartbeat = started
    warned = False
    with out_json.open("wb") as stdout, err_file.open("wb") as stderr:
        process = subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        while process.poll() is None:
            time.sleep(2)
            latest = max(
                out_json.stat().st_mtime if out_json.exists() else started,
                err_file.stat().st_mtime if err_file.exists() else started,
            )
            if latest > last_activity:
                last_activity = latest
                warned = False
            now = time.time()
            inactive = int(now - last_activity)
            elapsed = int(now - started)
            if inactive >= inactive_warning and not warned:
                reporter.emit(
                    "inactivity_warning",
                    stage=stage,
                    provider=route["provider"],
                    model=route["model"],
                    message=f"no provider output for {inactive}s",
                )
                warned = True
            if now - last_heartbeat >= update_every:
                reporter.emit(
                    "heartbeat",
                    stage=stage,
                    provider=route["provider"],
                    model=route["model"],
                    message=f"running {elapsed}s; last activity {inactive}s ago",
                )
                last_heartbeat = now
            if inactive >= inactive_timeout:
                terminate_process_group(process)
                return process.wait(), f"inactivity watchdog after {inactive}s"
            if elapsed >= total_timeout:
                terminate_process_group(process)
                return process.wait(), f"stage timeout after {elapsed}s"
            overdue = overdue_provider_tool_call(out_json, now, tool_call_grace)
            if overdue:
                terminate_process_group(process)
                return process.wait(), overdue
    return process.returncode or 0, ""


def overdue_provider_tool_call(out_json: Path, now: float, grace_seconds: int) -> str:
    """Return a failure for a provider shell tool exceeding its own timeout.

    Cursor may continue emitting transport or progress noise while its nested
    shell command is hung. File mtime alone then prevents the ordinary
    inactivity watchdog from firing. A declared tool timeout is a stronger
    contract: allow a modest grace period, then recover the provider session.
    """
    if not out_json.is_file():
        return ""
    pending: dict[str, tuple[float, int, str]] = {}
    for line in out_json.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "tool_call":
            continue
        call_id = str(event.get("call_id") or event.get("toolCallId") or "")
        if not call_id:
            continue
        if event.get("subtype") == "completed":
            pending.pop(call_id, None)
            continue
        if event.get("subtype") != "started":
            continue
        tool = event.get("tool_call")
        if not isinstance(tool, dict):
            continue
        timeout_ms = 0
        name = "provider tool"
        for tool_name, details in tool.items():
            if not isinstance(details, dict):
                continue
            name = str(tool_name)
            args = details.get("args")
            if isinstance(args, dict):
                try:
                    timeout_ms = int(args.get("timeout") or 0)
                except (TypeError, ValueError):
                    timeout_ms = 0
            if timeout_ms > 0:
                break
        if timeout_ms <= 0:
            continue
        started_ms = event.get("startedAtMs") or event.get("timestamp_ms")
        try:
            started = float(started_ms) / 1000
        except (TypeError, ValueError):
            continue
        pending[call_id] = (started, timeout_ms, name)
    for started, timeout_ms, name in pending.values():
        elapsed = now - started
        limit = (timeout_ms / 1000) + grace_seconds
        if elapsed >= limit:
            return (
                f"provider tool watchdog: {name} exceeded its declared {timeout_ms}ms "
                f"timeout by {int(elapsed - (timeout_ms / 1000))}s"
            )
    return ""


def run_attempt(
    stage: str,
    route: dict,
    route_index: int,
    attempt: int,
    task: str,
    branch: str,
    plan_dir: Path,
    manifest: dict,
    run_dir: Path,
    reporter: Reporter,
    args: argparse.Namespace,
    stage_baseline: dict,
    recovery_packets: list[Path],
    *,
    resume_session_id: str = "",
    continuation: int = 0,
    continuation_prompt: str = "",
) -> AttemptResult:
    invocation_id = str(uuid.uuid4())
    session_id = resume_session_id
    stem = attempt_stem(stage, route, route_index, attempt, continuation)
    out_json = run_dir / f"{stem}.jsonl"
    out_text = run_dir / f"{stem}.txt"
    err_file = run_dir / f"{stem}.stderr"
    if resume_session_id:
        prompt = continuation_prompt.strip()
    else:
        prompt = assemble(
            stage,
            stage_context(stage, task, branch, plan_dir, recovery_packets, manifest),
            root=ROOT,
            plan_dir=plan_dir,
        )
    (run_dir / f"{stem}.prompt.md").write_text(prompt, encoding="utf-8")
    cmd = (
        provider_resume_command(route, resume_session_id, prompt, out_text)
        if resume_session_id
        else provider_command(route, prompt, out_text)
    )
    reporter.emit(
        "stage_resumed" if resume_session_id else "stage_started",
        stage=stage,
        provider=route["provider"],
        model=route["model"],
        session_id=session_id or invocation_id,
        attempt=attempt,
        continuation=continuation,
        message=("same provider session continued" if resume_session_id else "fresh session started"),
    )
    started = time.time()
    rc, watchdog = run_monitored(
        cmd,
        out_json,
        err_file,
        stage=stage,
        route=route,
        reporter=reporter,
        update_every=args.update_every,
        inactive_warning=args.inactive_warning,
        inactive_timeout=args.inactive_timeout,
        total_timeout=args.stage_timeout,
        tool_call_grace=args.tool_call_grace,
    )
    seconds = int(time.time() - started)
    parsed = parse_stream_json(out_json)
    actual_session = str(parsed.get("session_id") or "")
    if actual_session:
        session_id = actual_session
    if route["provider"] in {"cursor", "claude"}:
        result_text = str(parsed.get("result_text") or "")
        if result_text:
            out_text.write_text(result_text + "\n", encoding="utf-8")
        actual_model = str(parsed.get("model_actual") or "")
        if rc == 0 and not models_match(route["model"], actual_model):
            rc = 42
            watchdog = f"model mismatch: expected {route['model']}, got {actual_model or 'empty'}"
    raw_json = out_json.read_text(encoding="utf-8", errors="replace") if out_json.exists() else ""
    text = out_text.read_text(encoding="utf-8", errors="replace") if out_text.exists() else ""
    err = err_file.read_text(encoding="utf-8", errors="replace") if err_file.exists() else ""
    data = load_json(raw_json)
    contract_text = text + "\n" + str(data.get("result") or "")
    outcome, reason = classify(data, contract_text, err)
    requires_user = last_terminal_line(contract_text, "PIPELINE_INPUT_REQUIRED") is not None
    diagnostic = provider_diagnostic_text(data, err, watchdog)
    failure_class, matched = classify_failure(diagnostic)
    if watchdog:
        reason = watchdog
        if watchdog.startswith("model mismatch:"):
            outcome = "error"
            failure_class = "permanent_provider"
        else:
            outcome = "transient"
            failure_class = "provider_stall" if "inactivity" in watchdog else "transient_provider"
    elif rc != 0 and outcome == "ok":
        outcome = "error"
        reason = f"provider exited {rc} despite OK marker"
    if failure_class in {"transient_provider", "provider_stall"}:
        reason = include_retry_after(reason, diagnostic)
    if outcome in {"ok", "blocked", "skipped", "continue"}:
        failure_class = "stage_contract"
    elif outcome == "error" and failure_class == "semantic":
        reason = reason or matched or f"provider exited {rc}"
    after = snapshot(branch)
    changed = snapshot_delta(stage_baseline, after)
    resumable = bool(session_id)
    return AttemptResult(
        outcome=outcome,
        reason=reason or matched,
        failure_class=failure_class,
        provider=route["provider"],
        model=route["model"],
        session_id=session_id or invocation_id,
        seconds=seconds,
        changed_paths=changed,
        output_text=out_text,
        output_json=out_json,
        resumable=resumable,
        requires_user=requires_user,
    )


def artifact_snapshot(plan_dir: Path) -> set[str]:
    directory = plan_branch_dir(plan_dir)
    return {path.name for path in directory.glob("*.md") if path.is_file()}


def new_artifact(plan_dir: Path, pattern: str, before: set[str]) -> bool:
    return any(
        path.name not in before for path in plan_branch_dir(plan_dir).glob(pattern)
    )


def new_artifact_paths(plan_dir: Path, pattern: str, before: set[str]) -> list[Path]:
    return [
        path
        for path in plan_branch_dir(plan_dir).glob(pattern)
        if path.is_file() and path.name not in before
    ]


def existing_artifact_paths(plan_dir: Path, pattern: str) -> list[Path]:
    return sorted(path for path in plan_branch_dir(plan_dir).glob(pattern) if path.is_file())


def recover_implement_tests_from_artifacts(
    branch: str, plan_dir: Path, manifest: dict, state: dict
) -> str:
    """Recover a verified test handoff after an interruption outside the stage.

    This deliberately reruns the normal deterministic postcondition, but uses
    the current test-only worktree rather than an in-memory baseline that is
    unavailable after the worker has exited.
    """
    if state.get("failed_stage") != "implement-tests":
        return ""
    dirty = working_paths(branch)
    tests = manifest.get("test_paths") or []
    allowed = manifest.get("allowed_paths") or []
    test_changes = [path for path in dirty if path_allowed(path, tests)]
    product_changes = [
        path for path in dirty if path_allowed(path, allowed) and not path_allowed(path, tests)
    ]
    out_of_plan = [
        path for path in dirty if not path_allowed(path, tests) and not path_allowed(path, allowed)
    ]
    reports = existing_artifact_paths(plan_dir, "tests-implementation-*.md")
    if not test_changes or product_changes or out_of_plan or not reports:
        return ""
    try:
        validate_red_proof(plan_dir, manifest, changed_test_paths=test_changes)
        assert_no_new_decisions([reports[-1]], require_declaration=True)
        assert_no_new_decisions(
            [plan_branch_dir(plan_dir) / "red-proof.md", plan_branch_dir(plan_dir) / "progress.md"]
        )
    except VerificationError:
        return ""
    return (
        f"recovered from {reports[-1].name}: {len(test_changes)} planned test path(s) present; "
        "red proof verified"
    )


def recover_test_handoff_for_implementation(
    branch: str, plan_dir: Path, manifest: dict
) -> str:
    """Validate a prior test handoff when verified product changes now coexist."""
    test_changes = [
        path for path in working_paths(branch) if path_allowed(path, manifest.get("test_paths") or [])
    ]
    reports = existing_artifact_paths(plan_dir, "tests-implementation-*.md")
    if not test_changes or not reports:
        return ""
    try:
        validate_red_proof(plan_dir, manifest, changed_test_paths=test_changes)
        assert_no_new_decisions([reports[-1]], require_declaration=True)
        assert_no_new_decisions(
            [plan_branch_dir(plan_dir) / "red-proof.md", plan_branch_dir(plan_dir) / "progress.md"]
        )
    except VerificationError:
        return ""
    return (
        f"recovered from {reports[-1].name}: {len(test_changes)} planned test path(s) and red proof remain valid"
    )


def recover_implementation_from_artifacts(
    branch: str, plan_dir: Path, manifest: dict, state: dict
) -> str:
    """Recover an implement stage only from current, passed verification evidence.

    This is intentionally cache-only: a resume must be fast and must not
    silently launch a broad verification run. A changed diff fingerprint
    leaves the stage pending for a fresh provider attempt instead.
    """
    if state.get("failed_stage") != "implement":
        return ""
    dirty = working_paths(branch)
    allowed = manifest.get("allowed_paths") or []
    tests = manifest.get("test_paths") or []
    product_changes = [
        path for path in dirty if path_allowed(path, allowed) and not path_allowed(path, tests)
    ]
    out_of_plan = [
        path for path in dirty
        if not path_allowed(path, allowed) and not path_allowed(path, tests)
    ]
    if not product_changes or out_of_plan:
        return ""
    artifact = plan_branch_dir(plan_dir) / "verification.json"
    if not artifact.is_file():
        return ""
    try:
        evidence = json.loads(artifact.read_text(encoding="utf-8"))
        if (
            evidence.get("status") != "passed"
            or evidence.get("diff_fingerprint") != diff_fingerprint(ROOT, branch)
            or [
                {key: item.get(key) for key in ("id", "repo", "argv")}
                for item in evidence.get("commands") or []
            ]
            != [
                {key: item.get(key) for key in ("id", "repo", "argv")}
                for item in manifest.get("test_commands") or []
            ]
            or [
                {key: item.get(key) for key in ("id", "test", "test_path", "command", "evidence_pattern")}
                for item in evidence.get("acceptance") or []
            ]
            != [
                {key: item.get(key) for key in ("id", "test", "test_path", "command", "evidence_pattern")}
                for item in manifest.get("acceptance_criteria") or []
            ]
        ):
            return ""
        reports = existing_artifact_paths(plan_dir, "test-report-*.md")
        if manifest.get("implementation_verification", {}).get("legacy_test_and_fix_selected"):
            if not reports:
                return ""
        if reports:
            assert_no_new_decisions([reports[-1]], require_declaration=True)
        assert_no_new_decisions([plan_branch_dir(plan_dir) / "progress.md"])
        # Keep this coupled to the verifier's cache contract. It performs no
        # commands when the fingerprint above is still current.
        verify_implementation(ROOT, branch, plan_dir, manifest)
    except (VerificationError, OSError, json.JSONDecodeError):
        return ""
    return (
        f"recovered from current verification.json: {len(product_changes)} planned product path(s) "
        f"and {len(evidence.get('commands') or [])} verification command(s) already passed"
    )


def verify_stage(
    stage: str,
    branch: str,
    plan_dir: Path,
    manifest: dict,
    baseline: dict,
    artifacts_before: set[str] | None = None,
) -> str:
    after = snapshot(branch)
    changed = snapshot_delta(baseline, after)
    artifacts_before = artifacts_before or set()
    dirty = working_paths(branch)
    allowed = manifest.get("allowed_paths") or []
    tests = manifest.get("test_paths") or []
    out_of_plan = [
        path for path in dirty
        if not path_allowed(path, allowed) and not path_allowed(path, tests)
    ]
    if out_of_plan:
        raise PipelineError(f"stage left dirty paths outside the plan: {', '.join(out_of_plan)}")
    if stage == "implement-tests":
        test_changes = [path for path in dirty if path_allowed(path, tests)]
        product_changes = [path for path in dirty if path_allowed(path, allowed) and not path_allowed(path, tests)]
        if not test_changes:
            raise PipelineError("implement-tests claimed success but no planned test files are changed")
        if product_changes:
            raise PipelineError(
                f"implement-tests left product changes in its test-only phase: {', '.join(product_changes)}"
            )
        if not stage_paths_allowed(stage, changed, manifest):
            raise PipelineError(f"implement-tests changed paths outside test_paths: {', '.join(changed)}")
        reports = new_artifact_paths(plan_dir, "tests-implementation-*.md", artifacts_before)
        if not reports:
            raise PipelineError("implement-tests report missing (tests-implementation-<n>.md)")
        try:
            validate_red_proof(plan_dir, manifest, changed_test_paths=test_changes)
            assert_no_new_decisions(reports, require_declaration=True)
            assert_no_new_decisions(
                [plan_branch_dir(plan_dir) / "red-proof.md", plan_branch_dir(plan_dir) / "progress.md"]
            )
        except VerificationError as exc:
            raise PipelineError(str(exc)) from exc
        return f"{len(test_changes)} planned test path(s) present; red proof verified"
    if stage == "implement":
        product_changes = [
            path for path in dirty
            if path_allowed(path, allowed) and not path_allowed(path, tests)
        ]
        if not product_changes:
            raise PipelineError("implement claimed success but no planned product files are changed")
        if not stage_paths_allowed(stage, changed, manifest):
            raise PipelineError(f"implement changed out-of-plan paths: {', '.join(changed)}")
        reports = new_artifact_paths(plan_dir, "test-report-*.md", artifacts_before)
        if manifest.get("implementation_verification", {}).get("legacy_test_and_fix_selected"):
            if not reports:
                raise PipelineError(
                    "legacy plan selected test-and-fix; implement must execute it internally and write test-report-<n>.md"
                )
        try:
            if reports:
                assert_no_new_decisions(reports, require_declaration=True)
            assert_no_new_decisions([plan_branch_dir(plan_dir) / "progress.md"])
            evidence = verify_implementation(ROOT, branch, plan_dir, manifest)
        except VerificationError as exc:
            raise PipelineError(str(exc)) from exc
        return (
            f"{len(product_changes)} planned product path(s) present; "
            f"{len(evidence.get('commands') or [])} command(s) and traceability verified"
        )
    if stage == "review":
        reports = new_artifact_paths(plan_dir, "review-*.md", artifacts_before)
        if not stage_paths_allowed(stage, changed, manifest):
            raise PipelineError(f"review changed out-of-plan paths: {', '.join(changed)}")
        try:
            precommit_scan(ROOT, branch)
        except VerificationError as exc:
            raise PipelineError(
                f"review left the diff failing the deterministic secret/convention scan: {exc}"
            ) from exc
        advisories: list[str] = []
        if not reports:
            advisories.append("review did not write a new review report")
        else:
            try:
                assert_no_new_decisions(reports, require_declaration=True)
                assert_review_gates(reports)
            except VerificationError as exc:
                advisories.append(str(exc))
        if changed:
            advisories.append(
                "review changed the diff; narrow post-fix verification and the deterministic post-review scan passed"
            )
        detail = "; ".join(advisories) if advisories else "review report, audits, and deterministic post-review scan recorded"
        return f"review completed with advisory status: {detail}"
    if stage == "commit-and-push":
        for name, repo in worktrees(branch).items():
            if dirty_paths(repo):
                raise PipelineError(f"{name} remains dirty after commit-and-push")
            git(repo, "fetch", "origin", branch, timeout=180, check=True)
            local = git(repo, "rev-parse", "HEAD", check=True).stdout.strip()
            remote = git(repo, "rev-parse", f"origin/{branch}", check=True).stdout.strip()
            if local != remote:
                raise PipelineError(f"{name} HEAD does not match origin/{branch}")
        return "all worktree repositories clean and pushed"
    if stage == "draft-pr":
        if not (plan_branch_dir(plan_dir) / "pr.md").is_file():
            raise PipelineError("draft-pr did not write pr.md")
        expected = repositories_with_base_diff(branch)
        if not expected:
            raise PipelineError(
                f"no repository differs from origin/{task_base_branch(ROOT, branch)}; no draft PR is required"
            )
        for name, repo in expected.items():
            result = subprocess.run(
                ["gh", "pr", "view", "--json", "state,isDraft,url"],
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode:
                detail = (result.stderr or result.stdout).strip()
                raise PipelineError(f"{name} draft PR could not be verified: {detail}")
            data = json.loads(result.stdout or "{}")
            if data.get("state") != "OPEN" or not data.get("isDraft"):
                raise PipelineError(f"{name} PR is not open and draft")
        return f"{len(expected)} open draft PR(s) verified"
    raise PipelineError(f"no verifier for stage {stage}")


def recovery_packet(
    run_dir: Path, stage: str, result: AttemptResult, route_index: int, attempt: int
) -> Path:
    path = run_dir / f"{stage}.recovery-route-{route_index}-attempt-{attempt}.json"
    sanitized = sanitize(result.reason)
    atomic_json(
        path,
        {
            "stage": stage,
            "failed_route": f"{result.provider}:{result.model}",
            "failure_class": result.failure_class,
            "reason": wrap_data(sanitized.text, "failed provider recovery reason"),
            "untrusted_input_flags": list(sanitized.flags),
            "changed_paths": result.changed_paths,
            "instruction": "Fresh fallback session must audit current filesystem state before continuing.",
        },
    )
    return path


def continuation_prompt(stage: str, reason: str, answer: str = "") -> str:
    if answer:
        authority = f"""
The user answered the pending question:

{answer.strip()}

Treat only that explicit answer as additional authority. Continue the same `/{stage}` stage from
the current filesystem state. Do not restart the stage or repeat resolved work.
""".strip()
    else:
        authority = f"""
Your previous `/{stage}` stop was premature:

{reason.strip()}

Continue autonomously in this same provider session. Reinspect the current filesystem, preserve
valid partial work, and take the smallest safe plan-consistent action. Reversible local operations,
lock-protected local container/image switching with restoration, bounded retries for transient
network/Docker failures, and mechanical test-fixture corrections already settled by the plan or
neighboring contracts do not require user permission. If another selected stage owns a correction,
record it and keep this stage moving instead of asking.
""".strip()
    return f"""
{authority}

Stop only when progress is impossible without a decision or external action only the user can
provide. In that case, end with `PIPELINE_INPUT_REQUIRED` followed by the minimum numbered
questions. Otherwise finish the stage and end with exactly:

PIPELINE_STAGE_OK: {stage}

Do not commit or push.
""".strip()


def persist_pending_input(
    state: dict,
    *,
    stage: str,
    route: dict,
    route_index: int,
    attempt: int,
    continuation: int,
    session_id: str,
    question: str,
    run_dir: Path,
) -> None:
    state["pending_input"] = {
        "stage": stage,
        "route": route,
        "route_index": route_index,
        "attempt": attempt,
        "continuation": continuation,
        "session_id": session_id,
        "question": question,
        "run_dir": str(run_dir),
        "pausedAt": utc_now(),
    }
    state["current_stage"] = stage
    state["failed_stage"] = None
    state["failed_reason"] = None
    state.pop("failed_at", None)


def run_ai_stage(
    stage: str,
    task: str,
    branch: str,
    plan_dir: Path,
    manifest: dict,
    health: dict[str, tuple[bool, str, str]],
    provider_circuits: set[str],
    run_dir: Path,
    reporter: Reporter,
    state: dict,
    args: argparse.Namespace,
) -> str:
    baseline = snapshot(branch)
    parked_before = parked_main_snapshot()
    contract_before = plan_contract_snapshot(plan_dir)
    policy_before = workflow_policy_snapshot(stage)
    routes = stage_routes(manifest, stage)
    recovery_packets: list[Path] = []
    last_reason = "no route attempted"
    reported_policy_changes: set[str] = set()

    def report_policy_update() -> None:
        changed = ensure_workflow_policy_unchanged(stage, policy_before)
        fresh = [path for path in changed if path not in reported_policy_changes]
        if not fresh:
            return
        reported_policy_changes.update(fresh)
        reporter.emit(
            "policy_change_advisory",
            stage=stage,
            message=(
                "active-stage policy changed after this provider session started; "
                "the completed session remains valid and the update applies to the next fresh stage: "
                + ", ".join(fresh)
            ),
        )

    def record_result(result: AttemptResult, *, resumed: bool, continuation: int) -> None:
        sessions = state.setdefault("stage_sessions", {}).setdefault(stage, [])
        if not sessions:
            raise PipelineError(f"missing session audit record for {stage}")
        record = sessions[-1]
        record["session_id"] = result.session_id
        record["provider_outcome"] = result.outcome
        record["status"] = "provider_ok" if result.outcome == "ok" else "attempt_failed"
        record["failure_class"] = result.failure_class
        record["reason"] = result.reason
        record["seconds"] = int(record.get("seconds") or 0) + result.seconds
        record["changed_paths"] = result.changed_paths
        record["lastTurnAt"] = utc_now()
        if resumed:
            record.setdefault("continuations", []).append(
                {
                    "number": continuation,
                    "outcome": result.outcome,
                    "reason": result.reason,
                    "seconds": result.seconds,
                    "run_dir": str(run_dir),
                    "completedAt": utc_now(),
                }
            )

    def evaluate(
        result: AttemptResult,
        *,
        route: dict,
        route_index: int,
        attempt: int,
        continuation: int,
        artifacts_before: set[str],
    ) -> str | None:
        nonlocal last_reason
        last_reason = f"{result.failure_class}: {result.reason or result.outcome}"
        if stage == "review" and result.outcome != "ok":
            if result.changed_paths and not stage_paths_allowed(stage, result.changed_paths, manifest):
                raise PipelineError(
                    f"review provider stopped after out-of-plan edits: {', '.join(result.changed_paths)}"
                )
            try:
                precommit_scan(ROOT, branch)
            except VerificationError as exc:
                raise PipelineError(
                    f"review provider stopped after leaving the diff failing the deterministic "
                    f"secret/convention scan: {exc}"
                ) from exc
            state.pop("pending_input", None)
            evidence = (
                f"review completed with advisory status: {last_reason}; "
                "deterministic post-review scan passed"
            )
            reporter.emit(
                "review_advisory",
                stage=stage,
                provider=route["provider"],
                model=route["model"],
                session_id=result.session_id,
                message=evidence,
            )
            return evidence
        if result.outcome == "ok":
            evidence = verify_stage(
                stage,
                branch,
                plan_dir,
                manifest,
                baseline,
                artifacts_before,
            )
            state.pop("pending_input", None)
            reporter.emit(
                "stage_completed",
                stage=stage,
                provider=route["provider"],
                model=route["model"],
                session_id=result.session_id,
                message=evidence,
            )
            return evidence
        if result.changed_paths and not stage_paths_allowed(stage, result.changed_paths, manifest):
            raise PipelineError(
                f"provider stopped after out-of-plan edits: {', '.join(result.changed_paths)}"
            )
        if result.outcome == "blocked":
            if not result.resumable:
                raise PipelineError(
                    f"{last_reason}; provider did not expose a resumable session id"
                )
            recoverable_escalation = recoverable_block_reason(stage, result.reason)
            requested_user = result.requires_user
            if result.requires_user and recoverable_escalation:
                result.requires_user = False
                reporter.emit(
                    "recoverable_input_rejected",
                    stage=stage,
                    provider=route["provider"],
                    model=route["model"],
                    message=f"continuing without user input: {result.reason[:180]}",
                )
            elif result.requires_user:
                persist_pending_input(
                    state,
                    stage=stage,
                    route=route,
                    route_index=route_index,
                    attempt=attempt,
                    continuation=continuation,
                    session_id=result.session_id,
                    question=result.reason,
                    run_dir=run_dir,
                )
                save_state(ROOT, task, state, plan_branch_dir(plan_dir))
                raise PipelineInputRequired(result.reason)
            if continuation >= args.max_stage_continuations:
                if recoverable_escalation:
                    if requested_user and concrete_user_action(result.reason):
                        persist_pending_input(
                            state,
                            stage=stage,
                            route=route,
                            route_index=route_index,
                            attempt=attempt,
                            continuation=continuation,
                            session_id=result.session_id,
                            question=result.reason,
                            run_dir=run_dir,
                        )
                        save_state(ROOT, task, state, plan_branch_dir(plan_dir))
                        raise PipelineInputRequired(result.reason)
                    result.outcome = "error"
                    result.failure_class = "semantic"
                    result.reason = (
                        "provider repeatedly refused recoverable execution work after "
                        f"{continuation} same-session continuations: {result.reason}"
                    )
                    last_reason = f"semantic: {result.reason}"
                    return None
                question = (
                    "The stage remained blocked after autonomous same-session continuations. "
                    f"Give direction for: {result.reason}"
                )
                persist_pending_input(
                    state,
                    stage=stage,
                    route=route,
                    route_index=route_index,
                    attempt=attempt,
                    continuation=continuation,
                    session_id=result.session_id,
                    question=question,
                    run_dir=run_dir,
                )
                save_state(ROOT, task, state, plan_branch_dir(plan_dir))
                raise PipelineInputRequired(question)
            return None
        if result.outcome == "skipped":
            raise PipelineError(last_reason)
        return None

    pending = state.get("pending_input") or {}
    if pending and pending.get("stage") == stage:
        if not args.answer:
            raise PipelineInputRequired(str(pending.get("question") or "user input required"))
        route = dict(pending.get("route") or {})
        if route_text(route) not in {route_text(item) for item in routes}:
            raise PipelineError(
                "the paused provider route is not selected by this run; resume with the original "
                "routing or start a deliberate fresh rerun"
            )
        route_index = int(pending.get("route_index") or 1)
        attempt = int(pending.get("attempt") or 1)
        continuation = int(pending.get("continuation") or 0) + 1
        session_id = str(pending.get("session_id") or "")
        artifacts_before = artifact_snapshot(plan_dir)
        result = run_attempt(
            stage,
            route,
            route_index,
            attempt,
            task,
            branch,
            plan_dir,
            manifest,
            run_dir,
            reporter,
            args,
            baseline,
            recovery_packets,
            resume_session_id=session_id,
            continuation=continuation,
            continuation_prompt=continuation_prompt(stage, str(pending.get("question") or ""), args.answer),
        )
        ensure_parked_mains_unchanged(parked_before)
        ensure_plan_contract_unchanged(plan_dir, contract_before)
        report_policy_update()
        record_result(result, resumed=True, continuation=continuation)
        save_state(ROOT, task, state, plan_branch_dir(plan_dir))
        evidence = evaluate(
            result,
            route=route,
            route_index=route_index,
            attempt=attempt,
            continuation=continuation,
            artifacts_before=artifacts_before,
        )
        if evidence:
            return evidence
        session_id = result.session_id
        while result.outcome == "blocked" and not result.requires_user:
            continuation += 1
            delay = min(300, 20 * (2 ** min(continuation - 1, 4)))
            reporter.emit(
                "autonomy_continuation",
                stage=stage,
                provider=route["provider"],
                model=route["model"],
                message=f"same-session continuation {continuation} in {delay}s: {result.reason[:180]}",
            )
            time.sleep(delay)
            result = run_attempt(
                stage,
                route,
                route_index,
                attempt,
                task,
                branch,
                plan_dir,
                manifest,
                run_dir,
                reporter,
                args,
                baseline,
                recovery_packets,
                resume_session_id=session_id,
                continuation=continuation,
                continuation_prompt=continuation_prompt(stage, result.reason),
            )
            ensure_parked_mains_unchanged(parked_before)
            ensure_plan_contract_unchanged(plan_dir, contract_before)
            report_policy_update()
            record_result(result, resumed=True, continuation=continuation)
            save_state(ROOT, task, state, plan_branch_dir(plan_dir))
            evidence = evaluate(
                result,
                route=route,
                route_index=route_index,
                attempt=attempt,
                continuation=continuation,
                artifacts_before=artifacts_before,
            )
            if evidence:
                return evidence

    for route_index, route in enumerate(routes, start=1):
        key = route_text(route)
        if route["provider"] in provider_circuits:
            reporter.emit(
                "route_skipped",
                stage=stage,
                provider=route["provider"],
                model=route["model"],
                message="provider circuit is open",
            )
            continue
        if not health.get(key, (False, "", ""))[0]:
            reporter.emit(
                "route_skipped",
                stage=stage,
                provider=route["provider"],
                model=route["model"],
                message=f"preflight unhealthy: {health.get(key, ('', '', 'unknown'))[2]}",
            )
            continue
        max_attempts = 1 + args.max_provider_retries
        for attempt in range(1, max_attempts + 1):
            attempt_artifacts_before = artifact_snapshot(plan_dir)
            invocation_id = str(uuid.uuid4())
            mark_started(
                state,
                stage,
                provider=route["provider"],
                model=route["model"],
                session_id=invocation_id,
                run_dir=str(run_dir),
            )
            save_state(ROOT, task, state, plan_branch_dir(plan_dir))
            result = run_attempt(
                stage,
                route,
                route_index,
                attempt,
                task,
                branch,
                plan_dir,
                manifest,
                run_dir,
                reporter,
                args,
                baseline,
                recovery_packets,
            )
            ensure_parked_mains_unchanged(parked_before)
            ensure_plan_contract_unchanged(plan_dir, contract_before)
            report_policy_update()
            record_result(result, resumed=False, continuation=0)
            save_state(ROOT, task, state, plan_branch_dir(plan_dir))
            evidence = evaluate(
                result,
                route=route,
                route_index=route_index,
                attempt=attempt,
                continuation=0,
                artifacts_before=attempt_artifacts_before,
            )
            if evidence:
                return evidence
            if result.outcome == "blocked" and result.resumable:
                continuation = 1
                session_id = result.session_id
                while True:
                    delay = min(300, 20 * (2 ** min(continuation - 1, 4)))
                    reporter.emit(
                        "autonomy_continuation",
                        stage=stage,
                        provider=route["provider"],
                        model=route["model"],
                        message=f"same-session continuation {continuation} in {delay}s: {result.reason[:180]}",
                    )
                    time.sleep(delay)
                    result = run_attempt(
                        stage,
                        route,
                        route_index,
                        attempt,
                        task,
                        branch,
                        plan_dir,
                        manifest,
                        run_dir,
                        reporter,
                        args,
                        baseline,
                        recovery_packets,
                        resume_session_id=session_id,
                        continuation=continuation,
                        continuation_prompt=continuation_prompt(stage, result.reason),
                    )
                    ensure_parked_mains_unchanged(parked_before)
                    ensure_plan_contract_unchanged(plan_dir, contract_before)
                    report_policy_update()
                    record_result(result, resumed=True, continuation=continuation)
                    save_state(ROOT, task, state, plan_branch_dir(plan_dir))
                    evidence = evaluate(
                        result,
                        route=route,
                        route_index=route_index,
                        attempt=attempt,
                        continuation=continuation,
                        artifacts_before=attempt_artifacts_before,
                    )
                    if evidence:
                        return evidence
                    if result.outcome != "blocked":
                        break
                    session_id = result.session_id
            if result.changed_paths:
                if not stage_paths_allowed(stage, result.changed_paths, manifest):
                    raise PipelineError(
                        f"provider failed after out-of-plan edits: {', '.join(result.changed_paths)}"
                    )
                packet = recovery_packet(run_dir, stage, result, route_index, attempt)
                recovery_packets.append(packet)
                reporter.emit(
                    "recovery_packet",
                    stage=stage,
                    provider=route["provider"],
                    model=route["model"],
                    message=f"partial in-plan edits preserved; {packet.name}",
                )
            if result.failure_class == "permanent_provider":
                if provider_wide_failure(route["provider"], result.reason):
                    provider_circuits.add(route["provider"])
                break
            if attempt < max_attempts:
                delay = 20
                retry_after = re.search(r"retry-after\D+(\d+)", result.reason, re.I)
                if retry_after:
                    delay = min(120, max(1, int(retry_after.group(1))))
                reporter.emit(
                    "provider_retry",
                    stage=stage,
                    provider=route["provider"],
                    model=route["model"],
                    message=f"fresh-session retry in {delay}s: {last_reason[:180]}",
                )
                time.sleep(delay)
        if route_index < len(routes):
            reporter.emit(
                "fallback",
                stage=stage,
                provider=routes[route_index]["provider"],
                model=routes[route_index]["model"],
                message=f"switching from failed approved route; {last_reason[:180]}",
            )
    if stage == "review":
        evidence = f"review completed with advisory status: all approved routes failed: {last_reason}"
        reporter.emit("review_advisory", stage=stage, message=evidence)
        return evidence
    raise PipelineError(f"all approved routes failed for {stage}: {last_reason}")


def run_script_stage(stage: str, branch: str, run_dir: Path, reporter: Reporter) -> str:
    parked_before = parked_main_snapshot()
    policy_before = workflow_policy_snapshot(stage)
    if stage == "commit-and-push":
        workaround = ROOT / ".claude/skills/references/e2e-local-scope-workaround.sh"
        if workaround.is_file():
            subprocess.run([str(workaround), "restore", "--root", str(ROOT)], timeout=60)
        script = ROOT / ".claude/skills/commit-and-push/commit-and-push.sh"
    elif stage == "draft-pr":
        script = ROOT / ".claude/skills/draft-pr/draft-pr.sh"
    else:
        raise PipelineError(f"unknown script stage: {stage}")
    reporter.emit("stage_started", stage=stage, provider="script", model="n/a", message="script started")
    result = subprocess.run(
        [str(script), branch],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    (run_dir / f"{stage}.txt").write_text(
        (result.stdout or "") + ("\nSTDERR:\n" + result.stderr if result.stderr else ""),
        encoding="utf-8",
    )
    if result.returncode:
        raise PipelineError(f"{stage} script exited {result.returncode}: {(result.stderr or result.stdout)[-400:]}")
    ensure_parked_mains_unchanged(parked_before)
    changed_policy = ensure_workflow_policy_unchanged(stage, policy_before)
    if changed_policy:
        reporter.emit(
            "policy_change_advisory",
            stage=stage,
            message=(
                "active-stage policy changed after this script started; the completed script remains valid "
                "and the update applies to the next fresh stage: " + ", ".join(changed_policy)
            ),
        )
    evidence = verify_stage(stage, branch, find_plan_dir(ROOT, branch), {}, {})
    reporter.emit("stage_completed", stage=stage, provider="script", model="n/a", message=evidence)
    return evidence


def recap(
    run_dir: Path,
    task: str,
    branch: str,
    manifest: dict,
    outcomes: list[tuple[str, str]],
    status: str,
    reason: str = "",
    resumable_session: bool = False,
) -> Path:
    lines = [
        "# Implementation pipeline recap",
        "",
        f"- **Task:** {task}",
        f"- **Branch:** `{branch}`",
        f"- **Status:** {status}",
        f"- **Run:** `{run_dir}`",
        f"- **Finished:** {utc_now()}",
        "",
        "## Selected stages and routes",
        "",
        "| Stage | Route |",
        "|---|---|",
    ]
    for stage in selected_stages(manifest):
        routes = " → ".join(route_text(route) for route in stage_routes(manifest, stage)) if stage in AI_STAGES else "script"
        lines.append(f"| `{stage}` | `{routes}` |")
    lines += ["", "## Outcomes", ""]
    lines += [f"- `/{stage}` — {evidence}" for stage, evidence in outcomes]
    if not outcomes:
        lines.append("- none")
    if reason:
        lines += ["", "## Stop reason", "", reason]
    lines += ["", "## Next", ""]
    if status == "SUCCESS":
        lines.append("The selected implementation pipeline is complete.")
    elif status == "WAITING_FOR_INPUT":
        if resumable_session:
            lines.append(
                f"Answer the question above, then continue the same provider session with "
                f"`{ROOT}/.claude/skills/pipeline/implement-pipeline.sh {task} --answer '<answer>'`."
            )
        else:
            lines.append(
                f"Complete the requested local intervention, then rerun "
                f"`{ROOT}/.claude/skills/pipeline/implement-pipeline.sh {task}`."
            )
    else:
        lines.append(
            f"Resolve the stop reason, then rerun `{ROOT}/.claude/skills/pipeline/implement-pipeline.sh {task}`; completed stages resume automatically."
        )
    path = run_dir / "recap.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def notify(title: str, message: str) -> None:
    if not shutil.which("osascript"):
        return
    safe_title = title.replace('"', "")
    safe_message = message.replace('"', "")
    subprocess.run(
        ["osascript", "-e", f'display notification "{safe_message}" with title "{safe_title}"'],
        capture_output=True,
        timeout=10,
    )


def display_status(task: str) -> int:
    live = live_status_path(task)
    last = live_last_path(task)
    state = load_state(ROOT, task)
    print(f"task={task}")
    if live.is_file():
        data = json.loads(live.read_text(encoding="utf-8"))
        running = pid_alive(int(data.get("pid") or 0))
        print(f"state={'RUNNING' if running else 'IDLE'}")
        if running:
            for key in ("pid", "stage", "event", "message", "updated", "run_dir"):
                print(f"{key}={data.get(key, '')}")
        else:
            for key in ("stage", "event", "message", "updated", "run_dir"):
                print(f"last_{key}={data.get(key, '')}")
    else:
        print("state=IDLE")
    selected = state.get("selected_stages") or []
    completed = state.get("completed") or []
    next_stage = next((stage for stage in selected if stage not in completed), "")
    print(f"selected={','.join(selected)}")
    print(f"completed={','.join(completed)}")
    print(f"next_stage={next_stage}")
    if state.get("failed_stage"):
        print(f"failed_stage={state['failed_stage']}")
        print(f"failed_reason={state.get('failed_reason') or ''}")
    pending = state.get("pending_input") or {}
    if pending:
        print(f"waiting_stage={pending.get('stage', '')}")
        print(f"waiting_provider={pending.get('route', {}).get('provider', '')}")
        print(f"waiting_model={pending.get('route', {}).get('model', '')}")
        print(f"waiting_question={pending.get('question', '')}")
    if last.is_file():
        data = json.loads(last.read_text(encoding="utf-8"))
        print(f"last_status={data.get('status', '')}")
        print(f"last_recap={data.get('recap', '')}")
    return 0


def watch(task: str, target_pid: int = 0, since: int = 0, last_after_ns: int = 0) -> int:
    cursor = 0
    run_dir: Path | None = None
    last_print = time.time()
    while True:
        status_file = live_status_path(task)
        if status_file.is_file():
            try:
                status = json.loads(status_file.read_text(encoding="utf-8"))
                updated = int(status.get("updated_unix") or 0)
                if updated >= since:
                    candidate_pid = int(status.get("pid") or 0)
                    if target_pid or pid_alive(candidate_pid):
                        run_dir = Path(status["run_dir"])
                        if not target_pid:
                            target_pid = candidate_pid
                    elif since == 0:
                        print("No active run found.")
                        return display_status(task)
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                pass
        if run_dir and (run_dir / "events.jsonl").is_file():
            lines = (run_dir / "events.jsonl").read_text(encoding="utf-8", errors="replace").splitlines()
            for line in lines[cursor:]:
                try:
                    print(format_event(json.loads(line)), flush=True)
                except json.JSONDecodeError:
                    continue
                last_print = time.time()
            cursor = len(lines)
        if target_pid and not pid_alive(target_pid):
            break
        if not target_pid and time.time() - since > 15:
            print("No active run found.")
            return display_status(task)
        if time.time() - last_print >= 90:
            print(f"[{utc_now()}] /{task} watcher: worker alive; waiting for next event", flush=True)
            last_print = time.time()
        time.sleep(2)
    last = live_last_path(task)
    if last.is_file() and last.stat().st_mtime_ns > last_after_ns:
        data = json.loads(last.read_text(encoding="utf-8"))
        recap_path = Path(data.get("recap") or "")
        if recap_path.is_file():
            print(recap_path.read_text(encoding="utf-8"), end="")
        return int(data.get("exit_code") or 0)
    if target_pid:
        print("Worker exited without a fresh final recap; inspect the detached log.", flush=True)
    return 2


def detach(args: argparse.Namespace) -> int:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    child_args = [item for item in sys.argv[1:] if item != "--foreground"]
    raw_task = getattr(args, "raw_task", args.task)
    if raw_task in child_args:
        child_args.remove(raw_task)
    if args.task not in child_args:
        child_args.insert(0, args.task)
    child_args.append("--foreground")
    wrapper_log = RUNS_DIR / f"live-{safe_task(args.task)}.log"
    started = int(time.time())
    last = live_last_path(args.task)
    last_before_ns = last.stat().st_mtime_ns if last.is_file() else 0
    with wrapper_log.open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), *child_args],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    print(f"PIPELINE_DETACHED pid={process.pid} log={wrapper_log}")
    print(f"Status: {ROOT}/.claude/skills/pipeline/implement-pipeline.sh {args.task} --status")
    print(f"Watch:  {ROOT}/.claude/skills/pipeline/implement-pipeline.sh {args.task} --watch")
    if args.no_wait:
        return 0
    return watch(args.task, process.pid, started, last_before_ns)


def build_runtime(args: argparse.Namespace) -> tuple[Path, dict, str]:
    plan_dir = find_plan_dir(ROOT, args.task)
    base = load_manifest(plan_dir / "pipeline.json")
    runtime = runtime_manifest(
        base,
        stages_override=args.stages,
        route_assignments=args.route,
        fallback_assignments=args.fallback,
    )
    branch = plan_branch_dir(plan_dir).relative_to(ROOT / "ai-plans").as_posix()
    runtime["task"] = args.task
    runtime["branch"] = branch
    runtime["plan_dir"] = str(plan_dir)
    return plan_dir, runtime, branch


def reset_unverified_legacy_implementation(state: dict, manifest: dict) -> list[str]:
    """Do not let an old pre-folding implement completion bypass its retired test/fix gate."""
    legacy_selected = manifest.get("implementation_verification", {}).get(
        "legacy_test_and_fix_selected"
    )
    if (
        legacy_selected
        and "implement" in (state.get("completed") or [])
        and not state.get("implementation_verification_complete")
    ):
        return invalidate_from(state, STAGE_ORDER, "implement")
    return []


def run(args: argparse.Namespace) -> int:
    plan_dir, manifest, branch = build_runtime(args)
    selected = selected_stages(manifest)
    state = load_state(ROOT, args.task)
    previously_completed = set(state.get("completed") or [])
    recovered_implementation_evidence = ""
    recovered_test_handoff_evidence = ""
    recovered_test_evidence_before_bind = ""
    if not args.no_resume and not args.from_stage:
        # Plan rebinding clears failed_stage. Capture a verified test handoff first
        # so a green-by-design implement-tests result survives that reset.
        recovered_test_evidence_before_bind = recover_implement_tests_from_artifacts(
            branch, plan_dir, manifest, state
        )
    if not args.no_resume and not args.from_stage:
        # `bind_plan` deliberately drops stale state. Capture only a completed
        # implement failure that independently verifies against the current
        # manifest and diff before that reset occurs.
        recovered_implementation_evidence = recover_implementation_from_artifacts(
            branch, plan_dir, manifest, state
        )
        if recovered_implementation_evidence and "implement-tests" in previously_completed:
            recovered_test_handoff_evidence = recover_test_handoff_for_implementation(
                branch, plan_dir, manifest
            )
        if recovered_implementation_evidence and not recovered_test_handoff_evidence:
            recovered_implementation_evidence = ""
    binding = bind_plan(state, plan_contract_fingerprint(plan_dir), str(plan_dir))
    state["selected_stages"] = selected
    legacy_verification_reset = reset_unverified_legacy_implementation(state, manifest)
    recovered_test_evidence = ""
    if not args.no_resume and not args.from_stage:
        recovered_test_evidence = recover_implement_tests_from_artifacts(
            branch, plan_dir, manifest, state
        ) or recovered_test_evidence_before_bind
        if recovered_test_evidence:
            mark_complete(state, "implement-tests", recovered_test_evidence)
            save_state(ROOT, args.task, state, plan_branch_dir(plan_dir))
        if not recovered_implementation_evidence:
            recovered_implementation_evidence = recover_implementation_from_artifacts(
                branch, plan_dir, manifest, state
            )
        if recovered_implementation_evidence:
            if "implement-tests" not in (state.get("completed") or []):
                mark_complete(state, "implement-tests", recovered_test_handoff_evidence)
            mark_complete(state, "implement", recovered_implementation_evidence)
            save_state(ROOT, args.task, state, plan_branch_dir(plan_dir))
    normalized = normalize_completed_prefix(state, selected)
    stages = remaining(
        selected,
        state.get("completed") or [],
        no_resume=args.no_resume,
        from_stage=args.from_stage,
        to_stage=args.to_stage,
    )
    pending = state.get("pending_input") or {}
    if args.answer and not pending:
        raise PipelineError("--answer was supplied but no stage is waiting for user input")
    if pending and pending.get("stage") not in stages:
        raise PipelineError(
            f"paused stage {pending.get('stage')} is not in the remaining run; resume without "
            "range/stage overrides or reset progress deliberately"
        )
    if pending:
        pending_stage = str(pending.get("stage") or "")
        pending_route = dict(pending.get("route") or {})
        approved_routes = {
            route_text(route) for route in stage_routes(manifest, pending_stage)
        }
        if route_text(pending_route) not in approved_routes:
            raise PipelineError(
                "the paused provider route is not selected by this run; resume with the original "
                "routing or reset progress deliberately"
            )
    if args.dry_run:
        print(f"Task: {args.task}\nBranch: {branch}\nPlan: {plan_dir}")
        print("Stages:")
        for stage in stages:
            routes = " -> ".join(route_text(route) for route in stage_routes(manifest, stage)) if stage in AI_STAGES else "script"
            print(f"  {stage}: {routes}")
        return 0
    stamp = now_stamp()
    run_dir = RUNS_DIR / f"{stamp}_{safe_task(args.task)}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "routing.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    reporter = Reporter(args.task, run_dir, args.update_every)
    lock: Path | None = acquire_lock(args.task, args.force_lock)
    outcomes: list[tuple[str, str]] = []
    try:
        live_last_path(args.task).unlink(missing_ok=True)
        reporter.emit(
            "run_started",
            stage="preflight",
            message=f"selected: {', '.join(stages) or 'nothing remaining'}",
        )
        if pending and not args.answer:
            reporter.current_stage = str(pending.get("stage") or "pipeline")
            raise PipelineInputRequired(str(pending.get("question") or "user input required"))
        health, circuits = preflight(
            args.task,
            branch,
            plan_dir,
            manifest,
            stages,
            args.no_health_probe,
            args.max_provider_retries,
            args.docker_start_timeout,
            reporter,
        )
        reporter.emit("preflight_completed", stage="preflight", message="all selected stages are runnable")
        if recovered_test_evidence:
            reporter.emit(
                "stage_recovered",
                stage="implement-tests",
                message=recovered_test_evidence,
            )
        if binding == "version_changed":
            reporter.emit(
                "plan_version_changed",
                stage="preflight",
                message="plan revision detected; prior execution state archived and the latest complete plan is active",
            )
        if state.get("failed_stage") == "preflight":
            state["failed_stage"] = None
            state["failed_reason"] = None
            state.pop("failed_at", None)
            state.setdefault("evidence", {}).pop("preflight", None)
            save_state(ROOT, args.task, state, plan_branch_dir(plan_dir))
        if args.preflight_only:
            state["last_run_dir"] = str(run_dir)
            save_state(ROOT, args.task, state, plan_branch_dir(plan_dir))
            recap_path = recap(run_dir, args.task, branch, manifest, outcomes, "PREFLIGHT_OK")
            atomic_json(
                live_last_path(args.task),
                {"status": "PREFLIGHT_OK", "exit_code": 0, "recap": str(recap_path), "when": utc_now()},
            )
            return 0
        if not stages:
            save_state(ROOT, args.task, state, plan_branch_dir(plan_dir))
            recap_path = recap(run_dir, args.task, branch, manifest, outcomes, "SUCCESS")
            atomic_json(
                live_last_path(args.task),
                {"status": "SUCCESS", "exit_code": 0, "recap": str(recap_path), "when": utc_now()},
            )
            reporter.emit("run_completed", stage="done", message="nothing remaining")
            return 0
        if normalized:
            reporter.emit(
                "progress_normalized",
                stage="preflight",
                message="invalid non-prefix completion removed: " + ", ".join(normalized),
            )
        if legacy_verification_reset:
            reporter.emit(
                "legacy_verification_reset",
                stage="preflight",
                message="retired test-and-fix evidence was incomplete; rerunning implement verification",
            )
        invalidated = invalidate_from(state, STAGE_ORDER, stages[0])
        if invalidated:
            reporter.emit(
                "progress_invalidated",
                stage="preflight",
                message="rerun invalidated: " + ", ".join(invalidated),
            )
        save_state(ROOT, args.task, state, plan_branch_dir(plan_dir))
        run_parked_baseline = parked_main_snapshot()
        run_plan_baseline = plan_contract_snapshot(plan_dir)
        if not args.no_sync_master and any(stage in stages for stage in ("implement-tests", "implement")):
            sync_master(branch, reporter)
        for stage in stages:
            ensure_parked_mains_unchanged(run_parked_baseline)
            ensure_plan_contract_unchanged(plan_dir, run_plan_baseline)
            if stage == "commit-and-push":
                try:
                    publish_evidence = precommit_scan(ROOT, branch)
                except VerificationError as exc:
                    raise PipelineError(f"pre-publish safety scan failed: {exc}") from exc
                reporter.emit(
                    "publish_gate_verified",
                    stage=stage,
                    message=(
                        "current diff safety scan passed; implementation test evidence is not rerun during publish"
                    ),
                )
            if stage in AI_STAGES:
                evidence = run_ai_stage(
                    stage,
                    args.task,
                    branch,
                    plan_dir,
                    manifest,
                    health,
                    circuits,
                    run_dir,
                    reporter,
                    state,
                    args,
                )
            else:
                mark_started(
                    state,
                    stage,
                    provider="script",
                    model="n/a",
                    session_id=f"script-{uuid.uuid4()}",
                    run_dir=str(run_dir),
                )
                save_state(ROOT, args.task, state, plan_branch_dir(plan_dir))
                evidence = run_script_stage(stage, branch, run_dir, reporter)
            ensure_parked_mains_unchanged(run_parked_baseline)
            ensure_plan_contract_unchanged(plan_dir, run_plan_baseline)
            mark_complete(state, stage, evidence)
            if stage == "implement":
                state["implementation_verification_complete"] = True
            state["last_run_dir"] = str(run_dir)
            save_state(ROOT, args.task, state, plan_branch_dir(plan_dir))
            outcomes.append((stage, evidence))
        recap_path = recap(run_dir, args.task, branch, manifest, outcomes, "SUCCESS")
        atomic_json(
            live_last_path(args.task),
            {"status": "SUCCESS", "exit_code": 0, "recap": str(recap_path), "when": utc_now()},
        )
        reporter.emit("run_completed", stage="done", message="all selected stages verified")
        if args.notify:
            notify("Apaleo implementation pipeline", f"{args.task} completed")
        return 0
    except PipelineInputRequired as exc:
        pending_input = state.get("pending_input") or {}
        waiting_stage = str(pending_input.get("stage") or reporter.current_stage)
        question = str(exc)
        state["last_run_dir"] = str(run_dir)
        save_state(ROOT, args.task, state, plan_branch_dir(plan_dir))
        recap_path = recap(
            run_dir,
            args.task,
            branch,
            manifest,
            outcomes,
            "WAITING_FOR_INPUT",
            question,
            resumable_session=bool(pending_input.get("session_id")),
        )
        atomic_json(
            live_last_path(args.task),
            {
                "status": "WAITING_FOR_INPUT",
                "exit_code": 3,
                "recap": str(recap_path),
                "question": question,
                "stage": waiting_stage,
                "when": utc_now(),
            },
        )
        reporter.emit("input_required", stage=waiting_stage, message=question)
        if args.notify:
            notify("Apaleo pipeline needs input", f"{args.task}: {question[:120]}")
        return 3
    except (
        PipelineError,
        ManifestError,
        ValueError,
        OSError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ) as exc:
        failed = reporter.current_stage
        reason = str(exc)
        mark_failed(state, failed, reason)
        state["last_run_dir"] = str(run_dir)
        save_state(ROOT, args.task, state, plan_branch_dir(plan_dir))
        recap_path = recap(run_dir, args.task, branch, manifest, outcomes, "NEEDS_REVIEW", reason)
        atomic_json(
            live_last_path(args.task),
            {"status": "NEEDS_REVIEW", "exit_code": 2, "recap": str(recap_path), "when": utc_now()},
        )
        reporter.emit("run_failed", stage=failed, message=reason)
        if args.notify:
            notify("Apaleo pipeline needs review", f"{args.task}: {reason[:120]}")
        return 2
    finally:
        workaround = ROOT / ".claude/skills/references/e2e-local-scope-workaround.sh"
        if workaround.is_file():
            try:
                subprocess.run(
                    [str(workaround), "restore", "--root", str(ROOT)],
                    capture_output=True,
                    timeout=60,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
        release_lock(lock)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Run the plan-confirmed implementation stages in separate fresh sessions."
    )
    result.add_argument("task", nargs="?", default="")
    result.add_argument("--stages", default="", help="comma-separated runtime stage override")
    result.add_argument("--route", action="append", default=[], help="stage=provider:model[:reasoning]")
    result.add_argument(
        "--fallback",
        action="append",
        default=[],
        help="approved stage=provider:model[:reasoning], or stage=none to clear",
    )
    result.add_argument("--from", dest="from_stage", default="")
    result.add_argument("--to", dest="to_stage", default="")
    result.add_argument("--no-resume", action="store_true")
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--preflight-only", action="store_true")
    result.add_argument("--no-health-probe", action="store_true")
    result.add_argument("--no-sync-master", action="store_true")
    result.add_argument("--max-provider-retries", type=int, default=1)
    result.add_argument(
        "--docker-start-timeout",
        type=int,
        default=600,
        help="seconds to start/wait for Docker before requiring user intervention",
    )
    result.add_argument(
        "--max-stage-continuations",
        type=int,
        default=3,
        help="same-session autonomy continuations before fresh recovery or genuine escalation",
    )
    result.add_argument(
        "--answer",
        default="",
        help="answer a pending question and resume that exact provider session",
    )
    result.add_argument("--inactive-warning", type=int, default=300)
    result.add_argument("--inactive-timeout", type=int, default=600)
    result.add_argument("--stage-timeout", type=int, default=5400)
    result.add_argument(
        "--tool-call-grace",
        type=int,
        default=120,
        help="seconds allowed after a provider tool's declared timeout before recovery",
    )
    result.add_argument("--update-every", type=int, default=90)
    result.add_argument("--status", action="store_true")
    result.add_argument("--watch", action="store_true")
    result.add_argument("--no-wait", action="store_true")
    result.add_argument("--foreground", action="store_true", help=argparse.SUPPRESS)
    result.add_argument("--force-lock", action="store_true")
    result.add_argument("--notify", action="store_true")
    result.add_argument("--reset-progress", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    if not args.task:
        try:
            args.task = infer_task()
        except PipelineError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 64
    args.raw_task = args.task
    args.task = canonical_task(args.task)
    if not 0 <= args.max_provider_retries <= 3:
        print("ERROR: --max-provider-retries must be between 0 and 3", file=sys.stderr)
        return 64
    if not 1 <= args.max_stage_continuations <= 10:
        print("ERROR: --max-stage-continuations must be between 1 and 10", file=sys.stderr)
        return 64
    if not 60 <= args.docker_start_timeout <= 3600:
        print("ERROR: --docker-start-timeout must be between 60 and 3600 seconds", file=sys.stderr)
        return 64
    if not 30 <= args.update_every <= 600:
        print("ERROR: --update-every must be between 30 and 600 seconds", file=sys.stderr)
        return 64
    if not 30 <= args.inactive_warning < args.inactive_timeout:
        print("ERROR: inactivity warning must be >=30s and below inactivity timeout", file=sys.stderr)
        return 64
    if not args.inactive_timeout <= args.stage_timeout <= 21600:
        print("ERROR: stage timeout must be >= inactivity timeout and at most 21600s", file=sys.stderr)
        return 64
    if not 15 <= args.tool_call_grace <= 900:
        print("ERROR: tool-call grace must be between 15 and 900 seconds", file=sys.stderr)
        return 64
    if args.status:
        return display_status(args.task)
    if args.watch:
        return watch(args.task, since=0)
    if args.reset_progress:
        paths = [state_path(ROOT, args.task)]
        try:
            paths.append(plan_branch_dir(find_plan_dir(ROOT, args.task)) / "pipeline-progress.json")
        except ManifestError:
            pass
        removed = []
        for path in dict.fromkeys(paths):
            if path.exists():
                path.unlink()
                removed.append(path)
        if removed:
            for path in removed:
                print(f"reset {path}")
        else:
            print("no state file")
        return 0
    short = args.dry_run or args.preflight_only
    if not args.foreground and not short and not (sys.stdin.isatty() and sys.stdout.isatty()):
        return detach(args)
    try:
        return run(args)
    except (PipelineError, ManifestError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
