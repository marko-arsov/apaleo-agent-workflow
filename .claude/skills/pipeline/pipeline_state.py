#!/usr/bin/env python3
"""Small, stage-list-based state store for `/implement-pipeline`."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_task(task: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", task).strip("_") or "unknown"


def state_path(root: Path, task: str) -> Path:
    return root / ".local" / "pipeline-state" / safe_task(task) / "progress.json"


def load(root: Path, task: str) -> dict:
    path = state_path(root, task)
    if not path.is_file():
        return {
            "schema": 3,
            "task": task,
            "completed": [],
            "attempts": {},
            "stage_sessions": {},
            "selected_stages": [],
            "failed_stage": None,
            "failed_reason": None,
            "pending_input": None,
            "implementation_verification_complete": False,
        }
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    # Compatibility for retired stages. test-and-fix is now an internal
    # implement subphase; its old completion record is not a separate gate.
    raw_completed = state.get("completed") or []
    legacy_test_and_fix_completed = "test-and-fix" in raw_completed
    completed = [
        "draft-pr" if stage == "create-pr" else stage
        for stage in raw_completed
        if stage not in {
            "specify",
            "create-implementation-plan",
            "request-pr-review",
            "address-bugbot",
            "test-and-fix",
        }
    ]
    state.update({"schema": 3, "task": task, "completed": list(dict.fromkeys(completed))})
    state.setdefault("attempts", {})
    state.setdefault("stage_sessions", {})
    state.setdefault("selected_stages", [])
    state.setdefault("failed_stage", None)
    state.setdefault("failed_reason", None)
    state.setdefault("pending_input", None)
    state.setdefault("implementation_verification_complete", legacy_test_and_fix_completed)
    return state


def save(root: Path, task: str, state: dict, plan_dir: Path | None = None) -> Path:
    path = state_path(root, task)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["schema"] = 3
    state["task"] = task
    state["updatedAt"] = utc_now()
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    if plan_dir:
        mirror = plan_dir / "pipeline-progress.json"
        mirror.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return path


def mark_started(
    state: dict,
    stage: str,
    *,
    provider: str,
    model: str,
    session_id: str,
    run_dir: str,
) -> None:
    attempts = state.setdefault("attempts", {})
    attempts[stage] = int(attempts.get(stage) or 0) + 1
    state.setdefault("stage_sessions", {}).setdefault(stage, []).append(
        {
            "provider": provider,
            "model": model,
            "session_id": session_id,
            "startedAt": utc_now(),
            "run_dir": run_dir,
        }
    )
    state["current_stage"] = stage
    state["last_run_dir"] = run_dir


def mark_complete(state: dict, stage: str, evidence: str = "") -> None:
    completed = state.setdefault("completed", [])
    if stage not in completed:
        completed.append(stage)
    state.setdefault("evidence", {})[stage] = evidence or "pipeline stage verified"
    sessions = state.get("stage_sessions", {}).get(stage) or []
    if sessions:
        sessions[-1].update(
            {
                "status": "complete",
                "completedAt": utc_now(),
                "evidence": evidence or "pipeline stage verified",
            }
        )
    state["failed_stage"] = None
    state["failed_reason"] = None
    state.pop("failed_at", None)
    state["current_stage"] = None
    if (state.get("pending_input") or {}).get("stage") == stage:
        state["pending_input"] = None


def mark_failed(state: dict, stage: str, reason: str) -> None:
    state["completed"] = [item for item in state.get("completed") or [] if item != stage]
    state["failed_stage"] = stage
    state["failed_reason"] = reason
    state["failed_at"] = utc_now()
    state["current_stage"] = None
    state.setdefault("evidence", {})[stage] = reason
    if stage == "implement":
        state["implementation_verification_complete"] = False
    sessions = state.get("stage_sessions", {}).get(stage) or []
    if sessions and sessions[-1].get("status") != "complete":
        sessions[-1].update(
            {"status": "failed", "completedAt": utc_now(), "reason": reason}
        )
    if (state.get("pending_input") or {}).get("stage") == stage:
        state["pending_input"] = None


def invalidate_from(state: dict, ordered_stages: list[str], stage: str) -> list[str]:
    """Invalidate a stage and every downstream completion after a rerun starts."""
    if stage not in ordered_stages:
        raise ValueError(f"cannot invalidate unknown stage '{stage}'")
    cutoff = ordered_stages.index(stage)
    invalidated = [
        item
        for item in state.get("completed") or []
        if item in ordered_stages and ordered_stages.index(item) >= cutoff
    ]
    invalidated_set = set(invalidated)
    state["completed"] = [
        item for item in state.get("completed") or [] if item not in invalidated_set
    ]
    evidence = state.setdefault("evidence", {})
    for item in invalidated:
        evidence.pop(item, None)
    if "implement" in invalidated_set:
        state["implementation_verification_complete"] = False
    if state.get("failed_stage") in invalidated_set:
        state["failed_stage"] = None
        state["failed_reason"] = None
        state.pop("failed_at", None)
    return invalidated


def normalize_completed_prefix(state: dict, selected: list[str]) -> list[str]:
    """Drop selected completions that occur after the first missing prerequisite."""
    completed = state.get("completed") or []
    completed_set = set(completed)
    missing_seen = False
    invalidated: list[str] = []
    for stage in selected:
        if stage not in completed_set:
            missing_seen = True
        elif missing_seen:
            invalidated.append(stage)
    invalidated_set = set(invalidated)
    if invalidated_set:
        state["completed"] = [stage for stage in completed if stage not in invalidated_set]
        evidence = state.setdefault("evidence", {})
        for stage in invalidated:
            evidence.pop(stage, None)
        if "implement" in invalidated_set:
            state["implementation_verification_complete"] = False
    return invalidated


def bind_plan(state: dict, fingerprint: str, plan_dir: str) -> str:
    """Rebind progress to a revised plan while retaining an append-only audit."""
    previous = str(state.get("plan_fingerprint") or "")
    previous_dir = str(state.get("plan_dir") or "")
    if not previous:
        state["plan_fingerprint"] = fingerprint
        state["plan_dir"] = plan_dir
        return "bound"
    if previous == fingerprint:
        state["plan_dir"] = plan_dir
        return ""
    history = state.setdefault("plan_history", [])
    history.append(
        {
            "plan_fingerprint": previous,
            "plan_dir": previous_dir,
            "completed": state.get("completed") or [],
            "evidence": state.get("evidence") or {},
            "attempts": state.get("attempts") or {},
            "stage_sessions": state.get("stage_sessions") or {},
            "failed_stage": state.get("failed_stage"),
            "failed_reason": state.get("failed_reason"),
            "last_run_dir": state.get("last_run_dir"),
            "pending_input": state.get("pending_input"),
            "revision_kind": "in-place" if previous_dir == plan_dir else "versioned",
            "archivedAt": utc_now(),
        }
    )
    state.update(
        {
            "plan_fingerprint": fingerprint,
            "plan_dir": plan_dir,
            "completed": [],
            "evidence": {},
            "attempts": {},
            "stage_sessions": {},
            "failed_stage": None,
            "failed_reason": None,
            "current_stage": None,
            "last_run_dir": None,
            "pending_input": None,
            "implementation_verification_complete": False,
        }
    )
    state.pop("failed_at", None)
    return "version_changed"


def remaining(
    selected: list[str],
    completed: list[str],
    *,
    no_resume: bool = False,
    from_stage: str = "",
    to_stage: str = "",
) -> list[str]:
    stages = list(selected)
    if from_stage:
        if from_stage not in stages:
            raise ValueError(f"--from stage '{from_stage}' is not selected")
        stages = stages[stages.index(from_stage) :]
    elif not no_resume:
        done = set(completed)
        stages = [stage for stage in stages if stage not in done]
    if to_stage:
        if to_stage not in selected:
            raise ValueError(f"--to stage '{to_stage}' is not selected")
        if to_stage not in stages:
            raise ValueError(
                f"--to stage '{to_stage}' precedes the current start or is already complete"
            )
        stages = stages[: stages.index(to_stage) + 1]
    return stages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--task", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("reset")
    args = parser.parse_args()
    root = Path(args.root)
    if args.command == "reset":
        path = state_path(root, args.task)
        if path.exists():
            path.unlink()
            print(f"reset {path}")
        else:
            print("no state file")
        return 0
    state = load(root, args.task)
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
