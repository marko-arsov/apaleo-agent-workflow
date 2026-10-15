#!/usr/bin/env python3
"""Create, validate, and resolve implementation-pipeline manifests.

Version 2 folds validation/fixing into ``implement`` and adds machine-readable
context, verification, traceability, diff-budget, and risk contracts. Version 1
plans remain immutable: they are upgraded in memory when loaded.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

from common import FEATURE_REPOS, repos_from_manifest, valid_extra_repo_name


VERSION = 2
LEGACY_VERSION = 1
STAGE_ORDER = [
    "implement-tests",
    "implement",
    "review",
    "commit-and-push",
    "draft-pr",
]
LEGACY_STAGE_ORDER = [
    "implement-tests",
    "implement",
    "review",
    "test-and-fix",
    "commit-and-push",
    "draft-pr",
]
AI_STAGES = frozenset({"implement-tests", "implement", "review"})
SCRIPT_STAGES = frozenset({"commit-and-push", "draft-pr"})
PROVIDERS = frozenset({"codex", "cursor", "claude"})
REASONING = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"})
CLAUDE_REASONING = frozenset({"low", "medium", "high", "xhigh", "max"})
RISK_LEVELS = frozenset({"standard", "elevated", "external", "destructive"})
ESTIMATE_POINTS = frozenset({1, 2, 3, 5})
DEFAULT_BASE_BRANCH = "master"
_BASE_BRANCH_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
TEST_PARSERS = frozenset({"dotnet", "jest", "playwright", "generic"})
SECRET_ENV_KEY = re.compile(r"(?:password|passwd|secret|token|api[_-]?key|credential)", re.I)
TEST_AUTHOR_FILE_THRESHOLD = 4
TEST_AUTHOR_EXPECTED_LINE_THRESHOLD = 300

# Immutable legacy defaults for old manifests and initial configuration only.
# New model recommendations belong to model_policy resources, never these tables.
DEFAULT_ROUTES = {
    "implement-tests": {
        "provider": "cursor",
        "model": "claude-sonnet-5-thinking-high",
    },
    "implement": {"provider": "cursor", "model": "grok-4.7-high"},
    # This is the neutral / unestimated fallback. /specify records the point-based
    # review suggestion below when an estimate is known.
    "review": {"provider": "cursor", "model": "gpt-5.6-sol-high"},
}

# Planning aids only. They never force review selection or override a route the
# user confirmed in pipeline.json.
REVIEW_SUGGESTIONS = {
    1: {"review": "skip", "reason": "small, low-ceremony change; offer an independent pass"},
    2: {
        "review": "run",
        "route": {"provider": "cursor", "model": "claude-sonnet-5-thinking-high"},
        "fallbacks": [
            {"provider": "cursor", "model": "grok-4.7-high"},
            {"provider": "claude", "model": "sonnet", "reasoning": "high"},
            {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high"},
        ],
    },
    3: {
        "review": "run",
        "route": {"provider": "cursor", "model": "gpt-5.6-sol-high"},
        "fallbacks": [
            {"provider": "cursor", "model": "grok-4.7-high"},
            {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high"},
            {"provider": "claude", "model": "sonnet", "reasoning": "high"},
        ],
    },
    5: {
        "review": "run",
        "route": {"provider": "cursor", "model": "claude-opus-5-5-high"},
        "fallbacks": [
            {"provider": "cursor", "model": "grok-4.7-high"},
            # Claude Code resolves this stable alias to the current Opus 5.5 model.
            {"provider": "claude", "model": "opus", "reasoning": "high"},
            {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high"},
        ],
    },
}

DEFAULT_REVIEW_FALLBACKS = REVIEW_SUGGESTIONS[3]["fallbacks"]

# Budgets guide planning and review; they never prevent a feature from moving.
DEFAULT_DIFF_BUDGET = {
    "expected_files": 0,
    "max_files": 200,
    "expected_lines": 0,
    "max_lines": 4000,
}

DEFAULT_CONTEXT_CONTRACTS = {
    "implement-tests": {
        "reads": ["plan", "test-conventions", "existing-tests"],
        "denied": ["product-source-under-change", "prior-implementation-attempts"],
        "writes": ["tests", "red-proof", "stage-report"],
    },
    "implement": {
        "reads": ["plan", "tests", "red-proof", "source", "failing-output"],
        "denied": ["specify-transcript", "provider-rationale"],
        "writes": ["product", "tests-during-fix-loop", "verification", "stage-report"],
    },
    "review": {
        "reads": ["plan", "tests", "filesystem", "diff"],
        "denied": ["progress", "provider-output", "recovery-packets", "prior-rationale"],
        "writes": ["plan-scoped-fixes", "review-report", "verification-after-fix"],
    },
}


class ManifestError(ValueError):
    pass


def _hc(value: str) -> str:
    match = re.search(r"(?i)hc[-_ ]?(\d+)", value)
    return f"hc-{match.group(1)}" if match else ""


def find_plan_dir(root: Path, task: str) -> Path:
    plans = root / "ai-plans"
    if not plans.is_dir():
        raise ManifestError(f"plan root missing: {plans}")
    task_norm = task.strip().lower().replace("_", "-")
    task_hc = _hc(task_norm)
    candidates: list[tuple[int, int, Path]] = []
    for implementation in plans.rglob("implementation.md"):
        directory = implementation.parent
        branch_dir = plan_branch_dir(directory)
        required = ("prompt.md", "product.md", "implementation.md", "deferred-scope.md", "pipeline.json")
        if not all((directory / name).is_file() for name in required):
            continue
        rel = branch_dir.relative_to(plans).as_posix().lower()
        version_match = re.fullmatch(r"v(\d+)", directory.name, re.I)
        version = int(version_match.group(1)) if version_match else 1
        score = 0
        if rel == task_norm:
            score = 100
        elif task_norm and task_norm in rel:
            score = 80
        elif task_hc and task_hc in rel:
            score = 70
        elif task_hc and _hc(rel) == task_hc:
            score = 60
        if score:
            candidates.append((score, version, directory))
    if not candidates:
        raise ManifestError(f"no complete five-file plan contract found for {task}; run /specify")
    candidates.sort(key=lambda item: (item[0], item[1], str(item[2])), reverse=True)
    best_score, best_version = candidates[0][:2]
    best = [path for score, version, path in candidates if score == best_score and version == best_version]
    if len(best) > 1:
        joined = ", ".join(str(path.relative_to(plans)) for path in best)
        raise ManifestError(f"ambiguous plan for {task}: {joined}; pass the full branch name")
    return best[0]


def plan_branch_dir(plan_dir: Path) -> Path:
    return plan_dir.parent if re.fullmatch(r"v\d+", plan_dir.name, re.I) else plan_dir


def base_branch(manifest: dict) -> str:
    """Branch the feature is measured against and its draft PR targets.

    Absent means master. A stacked plan names the unmerged branch it was cut from.
    """
    return manifest.get("base_branch") or DEFAULT_BASE_BRANCH


def task_base_branch(root: Path, task: str) -> str:
    return base_branch(load_manifest(find_plan_dir(root, task) / "pipeline.json"))


def parse_route(value: str) -> dict:
    bits = [bit.strip() for bit in value.split(":")]
    if len(bits) not in {2, 3} or not all(bits[:2]):
        raise ManifestError(f"invalid route '{value}'; expected provider:model[:reasoning]")
    provider = bits[0].lower()
    if provider == "agent":
        provider = "cursor"
    if provider not in PROVIDERS:
        raise ManifestError(f"unsupported provider '{provider}'; use codex, cursor, or claude")
    route = {"provider": provider, "model": bits[1]}
    if len(bits) == 3 and bits[2]:
        route["reasoning"] = bits[2].lower()
    if route.get("reasoning") and route["reasoning"] not in REASONING:
        raise ManifestError(
            f"invalid reasoning '{route['reasoning']}'; expected {', '.join(sorted(REASONING))}"
        )
    if provider == "claude" and route.get("reasoning") and route["reasoning"] not in CLAUDE_REASONING:
        raise ManifestError(
            f"Claude reasoning '{route.get('reasoning')}' is unsupported; expected "
            + ", ".join(sorted(CLAUDE_REASONING))
        )
    if provider == "cursor" and route.get("reasoning"):
        raise ManifestError("Cursor reasoning must be encoded in the selected model id")
    return route


def route_text(route: dict) -> str:
    value = f"{route['provider']}:{route['model']}"
    if route.get("reasoning"):
        value += f":{route['reasoning']}"
    return value


def model_family(route: dict) -> str:
    model = str(route.get("model") or "").lower()
    if "grok" in model:
        return "xai-grok"
    if any(name in model for name in ("claude", "opus", "sonnet", "haiku")):
        return "anthropic-claude"
    if any(name in model for name in ("gpt", "codex", "o1", "o3", "o4")):
        return "openai-gpt"
    return f"{route.get('provider', 'unknown')}:{model.split('-', 1)[0]}"


def review_suggestion(estimate_points: int) -> dict:
    """Return a copy of the non-binding review suggestion for a Linear estimate."""
    if estimate_points not in ESTIMATE_POINTS:
        raise ManifestError("estimate points must be one of 1, 2, 3, or 5")
    return deepcopy(REVIEW_SUGGESTIONS[estimate_points])


def test_author_suggestion(acceptance_criteria: list[dict], diff_budget: dict) -> dict:
    """Return the non-binding Cursor-first route suggested by planned test effort."""
    test_files = {
        str(criterion.get("test_path") or "")
        for criterion in acceptance_criteria
        if isinstance(criterion, dict) and str(criterion.get("test_path") or "")
    }
    try:
        expected_lines = int(diff_budget.get("expected_lines") or 0)
    except (TypeError, ValueError):
        expected_lines = 0
    use_opus = (
        len(test_files) >= TEST_AUTHOR_FILE_THRESHOLD
        or expected_lines >= TEST_AUTHOR_EXPECTED_LINE_THRESHOLD
    )
    if use_opus:
        route = {"provider": "cursor", "model": "claude-opus-5-5-high"}
        fallback = {"provider": "claude", "model": "opus", "reasoning": "high"}
        reason = "four or more planned test files or a substantial expected diff"
    else:
        route = {"provider": "cursor", "model": "claude-sonnet-5-thinking-high"}
        fallback = {"provider": "claude", "model": "sonnet", "reasoning": "high"}
        reason = "one to three modest planned test files"
    return {
        "test_file_count": len(test_files),
        "expected_lines": expected_lines,
        "suggestion": {"route": route, "fallbacks": [fallback], "reason": reason},
    }


def parse_assignment(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise ManifestError(f"invalid assignment '{value}'; expected stage=value")
    stage, raw = value.split("=", 1)
    stage = stage.strip()
    if stage not in AI_STAGES:
        raise ManifestError(
            f"route stage '{stage}' is not one of: {', '.join(s for s in STAGE_ORDER if s in AI_STAGES)}"
        )
    return stage, raw.strip()


def parse_stages(value: str | list[str]) -> list[str]:
    raw = value if isinstance(value, list) else re.split(r"[,\s]+", value.strip())
    seen: set[str] = set()
    for stage in raw:
        stage = stage.strip()
        if not stage:
            continue
        if stage == "test-and-fix":
            stage = "implement"
        if stage not in STAGE_ORDER:
            raise ManifestError(f"unknown stage '{stage}'; expected a subset of {', '.join(STAGE_ORDER)}")
        seen.add(stage)
    return [stage for stage in STAGE_ORDER if stage in seen]


def _safe_repo_path(path: str, repos: tuple[str, ...] = FEATURE_REPOS) -> bool:
    normalized = path.replace("\\", "/")
    parts = Path(normalized).parts
    return not normalized.startswith(("/", "~")) and ".." not in parts and any(
        normalized.startswith(f"{repo}/") for repo in repos
    )


def _legacy_upgrade(manifest: dict) -> dict:
    """Translate a v1 plan in memory without touching its immutable file."""
    runtime = deepcopy(manifest)
    if runtime.get("version") != LEGACY_VERSION:
        return runtime
    legacy_stages = runtime.get("stages") or []
    selected_test_fix = any(
        item.get("name") == "test-and-fix" and item.get("selected")
        for item in legacy_stages if isinstance(item, dict)
    )
    runtime["version"] = VERSION
    runtime["legacy_source_version"] = LEGACY_VERSION
    runtime["stages"] = [
        deepcopy(item) for item in legacy_stages
        if isinstance(item, dict) and item.get("name") != "test-and-fix"
    ]
    for item in runtime["stages"]:
        if item.get("name") == "implement":
            item["required"] = True
            item["selected"] = True
    runtime["context_contracts"] = deepcopy(DEFAULT_CONTEXT_CONTRACTS)
    runtime["test_commands"] = []
    runtime["acceptance_criteria"] = []
    runtime["diff_budget"] = {"expected_files": 0, "max_files": 0, "expected_lines": 0, "max_lines": 0}
    runtime["risk"] = {"level": "standard", "confirmed": True, "reasons": ["legacy-plan"]}
    runtime["mutation_testing"] = {"enabled": False}
    runtime["implementation_verification"] = {
        "required": bool(runtime.get("e2e_required") or selected_test_fix),
        "legacy_test_and_fix_selected": selected_test_fix,
    }
    return runtime


def normalize_manifest(manifest: dict) -> dict:
    runtime = _legacy_upgrade(manifest)
    if runtime.get("version") == VERSION:
        runtime.setdefault("context_contracts", deepcopy(DEFAULT_CONTEXT_CONTRACTS))
        runtime.setdefault("test_commands", [])
        runtime.setdefault("acceptance_criteria", [])
        runtime.setdefault("diff_budget", {})
        runtime.setdefault("risk", {"level": "standard", "confirmed": True, "reasons": []})
        runtime.setdefault("mutation_testing", {"enabled": False})
        runtime.setdefault(
            "implementation_verification",
            {"required": True, "legacy_test_and_fix_selected": False},
        )
    return runtime


def validate(manifest: dict) -> list[str]:
    manifest = normalize_manifest(manifest)
    errors: list[str] = []
    legacy = manifest.get("legacy_source_version") == LEGACY_VERSION
    if manifest.get("version") != VERSION:
        errors.append(f"version must be {VERSION}")
    stages = manifest.get("stages")
    if not isinstance(stages, list):
        return [*errors, "stages must be a list"]
    selected: list[str] = []
    names: set[str] = set()
    manifest_order: list[str] = []
    for item in stages:
        if not isinstance(item, dict):
            errors.append("each stage must be an object")
            continue
        name = str(item.get("name") or "")
        if name not in STAGE_ORDER:
            errors.append(f"unknown stage: {name or '<empty>'}")
            continue
        if name in names:
            errors.append(f"duplicate stage: {name}")
        names.add(name)
        manifest_order.append(name)
        if item.get("selected"):
            selected.append(name)
        expected_required = name == "implement" or (
            name == "implement-tests" and bool(manifest.get("tests_required"))
        )
        if bool(item.get("required")) != expected_required:
            errors.append(f"{name}: required must be {str(expected_required).lower()}")
        route = item.get("route")
        fallbacks = item.get("fallbacks") or []
        if name in AI_STAGES:
            if not isinstance(route, dict):
                errors.append(f"{name}: AI stage requires a route")
            else:
                try:
                    parse_route(route_text(route))
                except (KeyError, ManifestError) as exc:
                    errors.append(f"{name}: {exc}")
            if not isinstance(fallbacks, list):
                errors.append(f"{name}: fallbacks must be a list")
            else:
                seen_routes: set[str] = set()
                if isinstance(route, dict):
                    try:
                        seen_routes.add(route_text(route))
                    except KeyError:
                        pass
                for fallback in fallbacks:
                    try:
                        fallback_text = route_text(fallback)
                        parse_route(fallback_text)
                        if fallback_text in seen_routes:
                            errors.append(f"{name}: duplicate primary/fallback route {fallback_text}")
                        seen_routes.add(fallback_text)
                    except (KeyError, ManifestError) as exc:
                        errors.append(f"{name} fallback: {exc}")
        if name in SCRIPT_STAGES and route:
            errors.append(f"{name}: script stage must not have a model route")
    if "implement" not in selected:
        errors.append("implement is required")
    if manifest_order != STAGE_ORDER:
        errors.append("stages must contain every canonical stage exactly once and in order")
    if manifest.get("tests_required") and "implement-tests" not in selected:
        errors.append("implement-tests is required because tests_required=true")
    if "implement-tests" in selected and not manifest.get("tests_required"):
        errors.append("implement-tests may be selected only when tests_required=true")
    if "draft-pr" in selected and "commit-and-push" not in selected:
        errors.append("draft-pr requires commit-and-push")
    if "base_branch" in manifest:
        stacked_on = manifest["base_branch"]
        if (
            not isinstance(stacked_on, str)
            or not _BASE_BRANCH_PATTERN.fullmatch(stacked_on)
            or ".." in stacked_on
            or stacked_on.endswith(("/", ".lock"))
        ):
            errors.append("base_branch must be a plain branch name")
        elif stacked_on in {DEFAULT_BASE_BRANCH, "main"}:
            errors.append("base_branch is only for stacked plans; omit it for master")
    if selected != [stage for stage in STAGE_ORDER if stage in selected]:
        errors.append("selected stages are not in canonical order")
    extras = manifest.get("extra_repos", [])
    if "extra_repos" in manifest and (
        not isinstance(extras, list)
        or len(extras) != len(set(extras))
        or not all(isinstance(item, str) and valid_extra_repo_name(item) for item in extras)
    ):
        errors.append("extra_repos must be a list of apaleo repository names outside the parked five")
    repos = repos_from_manifest(manifest)
    allowed = manifest.get("allowed_paths") or []
    test_paths = manifest.get("test_paths") or []
    for label, paths in (("allowed_paths", allowed), ("test_paths", test_paths)):
        if not isinstance(paths, list) or not all(isinstance(path, str) and path for path in paths):
            errors.append(f"{label} must be a list of non-empty glob strings")
            continue
        if len(paths) != len(set(paths)):
            errors.append(f"{label} must not contain duplicates")
        for path in paths:
            if not _safe_repo_path(path, repos):
                errors.append(f"{label}: unsafe or non-worktree path glob {path}")
    if not allowed:
        errors.append("allowed_paths must name at least one product/generated path")
    if manifest.get("tests_required") and not test_paths:
        errors.append("test_paths must be explicit when tests_required=true")

    contracts = manifest.get("context_contracts")
    if not isinstance(contracts, dict):
        errors.append("context_contracts must be an object")
    else:
        for stage in AI_STAGES:
            contract = contracts.get(stage)
            if not isinstance(contract, dict):
                errors.append(f"context_contracts.{stage} is required")
                continue
            for key in ("reads", "denied", "writes"):
                values = contract.get(key)
                if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
                    errors.append(f"context_contracts.{stage}.{key} must be a string list")
                elif values != DEFAULT_CONTEXT_CONTRACTS[stage][key]:
                    errors.append(
                        f"context_contracts.{stage}.{key} must match the enforced canonical contract"
                    )

    commands = manifest.get("test_commands")
    command_ids: set[str] = set()
    if not isinstance(commands, list):
        errors.append("test_commands must be a list")
        commands = []
    for command in commands:
        if not isinstance(command, dict):
            errors.append("each test command must be an object")
            continue
        command_id = str(command.get("id") or "")
        if not command_id or command_id in command_ids:
            errors.append(f"test command id is empty or duplicated: {command_id or '<empty>'}")
        command_ids.add(command_id)
        if command.get("repo") not in repos:
            errors.append(f"{command_id}: repo must be one of {', '.join(repos)}")
        argv = command.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) and arg for arg in argv):
            errors.append(f"{command_id}: argv must be a non-empty string list")
        parser = command.get("parser")
        if parser not in TEST_PARSERS:
            errors.append(f"{command_id}: parser must be one of {', '.join(sorted(TEST_PARSERS))}")
        if parser == "generic" and not command.get("success_pattern"):
            errors.append(f"{command_id}: generic parser requires success_pattern")
        success_pattern = str(command.get("success_pattern") or "")
        if success_pattern:
            try:
                re.compile(success_pattern)
            except re.error as exc:
                errors.append(f"{command_id}: invalid success_pattern: {exc}")
        timeout = command.get("timeout_seconds", 1800)
        if not isinstance(timeout, int) or not 1 <= timeout <= 7200:
            errors.append(f"{command_id}: timeout_seconds must be an integer from 1 to 7200")
        environment = command.get("env", {})
        if not isinstance(environment, dict) or not all(
            isinstance(key, str) and isinstance(value, (str, int, float, bool))
            for key, value in environment.items()
        ):
            errors.append(f"{command_id}: env must be a scalar string-keyed object")
        elif any(SECRET_ENV_KEY.search(key) for key in environment):
            errors.append(f"{command_id}: secret-shaped env keys are forbidden in immutable plans")

    criteria = manifest.get("acceptance_criteria")
    criterion_ids: set[str] = set()
    if not isinstance(criteria, list):
        errors.append("acceptance_criteria must be a list")
        criteria = []
    for criterion in criteria:
        if not isinstance(criterion, dict):
            errors.append("each acceptance criterion mapping must be an object")
            continue
        criterion_id = str(criterion.get("id") or "")
        if not criterion_id or criterion_id in criterion_ids:
            errors.append(f"acceptance criterion id is empty or duplicated: {criterion_id or '<empty>'}")
        criterion_ids.add(criterion_id)
        path = str(criterion.get("test_path") or "")
        if not path or not _safe_repo_path(path, repos) or not path_allowed(path, test_paths):
            errors.append(f"{criterion_id}: test_path must match test_paths")
        if str(criterion.get("command") or "") not in command_ids:
            errors.append(f"{criterion_id}: command must reference a test_commands id")
        if not str(criterion.get("test") or ""):
            errors.append(f"{criterion_id}: test must name the mapped test")
        if not isinstance(criterion.get("red_required"), bool):
            errors.append(f"{criterion_id}: red_required must be boolean")
        evidence_pattern = str(criterion.get("evidence_pattern") or "")
        if not evidence_pattern:
            errors.append(f"{criterion_id}: evidence_pattern is required")
        else:
            try:
                re.compile(evidence_pattern)
            except re.error as exc:
                errors.append(f"{criterion_id}: invalid evidence_pattern: {exc}")
        command_id = str(criterion.get("command") or "")
        command = next((item for item in commands if item.get("id") == command_id), None)
        if command and path and not path.startswith(f"{command.get('repo')}/"):
            errors.append(f"{criterion_id}: test_path must be in the command's repository")
    if not legacy and (not commands or not criteria):
        errors.append("v2 plans need test_commands and acceptance_criteria mappings")
    # A tests-first plan may still have zero implement-tests-reachable red criteria when
    # the confirmed plan demonstrates assertion-level red during implement instead.

    budget = manifest.get("diff_budget")
    if not isinstance(budget, dict):
        errors.append("diff_budget must be an object")
    elif not legacy:
        for key in ("expected_files", "max_files", "expected_lines", "max_lines"):
            if not isinstance(budget.get(key), int) or budget[key] < 0:
                errors.append(f"diff_budget.{key} must be a non-negative integer")
        if all(isinstance(budget.get(key), int) for key in ("expected_files", "max_files")) and budget["max_files"] < budget["expected_files"]:
            errors.append("diff_budget.max_files must be >= expected_files")
        if all(isinstance(budget.get(key), int) for key in ("expected_lines", "max_lines")) and budget["max_lines"] < budget["expected_lines"]:
            errors.append("diff_budget.max_lines must be >= expected_lines")

    risk = manifest.get("risk")
    if not isinstance(risk, dict) or risk.get("level") not in RISK_LEVELS:
        errors.append(f"risk.level must be one of {', '.join(sorted(RISK_LEVELS))}")
    else:
        reasons = risk.get("reasons")
        if not isinstance(reasons, list) or not all(isinstance(reason, str) and reason for reason in reasons):
            errors.append("risk.reasons must be a string list")
        if risk.get("level") != "standard" and not risk.get("confirmed"):
            errors.append(f"risk level {risk.get('level')} requires explicit confirmation")

    mutation = manifest.get("mutation_testing")
    if not isinstance(mutation, dict) or not isinstance(mutation.get("enabled"), bool):
        errors.append("mutation_testing.enabled must be boolean")
    elif mutation.get("enabled"):
        argv = mutation.get("argv")
        if manifest.get("risk", {}).get("level") not in {"elevated", "external", "destructive"}:
            errors.append("mutation testing is opt-in only for elevated-risk plans")
        if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) and arg for arg in argv):
            errors.append("enabled mutation_testing requires argv")
        elif argv[:2] != ["dotnet", "stryker"]:
            errors.append("mutation testing must use dotnet stryker")
        if "--since:main" not in (argv or []):
            errors.append("mutation testing must be diff-scoped with --since:main")
        reason_text = " ".join(manifest.get("risk", {}).get("reasons") or [])
        if not re.search(r"\b(?:authori[sz]ation|billing|payment|money)\b", reason_text, re.I):
            errors.append("mutation testing is limited to authorization or billing risk")

    if "model_selection" in manifest:
        from model_policy.core import validate_snapshot
        try:
            actual = {item["name"]: [item["route"], *item.get("fallbacks", [])] for item in manifest["stages"] if item.get("selected") and item["name"] in AI_STAGES}
            validate_snapshot(manifest["model_selection"], actual)
            if manifest["model_selection"].get("unresolved"):
                errors.append("Resolve unavailable model selections before execution")
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc))

    selection = manifest.get("review_selection")
    if selection is not None:
        if not isinstance(selection, dict) or selection.get("estimate_points") not in ESTIMATE_POINTS:
            errors.append("review_selection.estimate_points must be one of 1, 2, 3, or 5")
        elif selection.get("suggestion") != REVIEW_SUGGESTIONS[selection["estimate_points"]]:
            errors.append("review_selection.suggestion must match the point-based review guidance")
    test_author = manifest.get("test_author_selection")
    if not legacy and test_author is not None:
        expected_test_author = test_author_suggestion(
            criteria,
            budget if isinstance(budget, dict) else DEFAULT_DIFF_BUDGET,
        )
        if test_author != expected_test_author:
            errors.append("test_author_selection must match planned test-file count and expected diff guidance")
    return errors


def make_manifest(
    *,
    stages: list[str],
    tests_required: bool,
    e2e_required: bool,
    route_assignments: list[str],
    fallback_assignments: list[str],
    allowed_paths: list[str],
    test_paths: list[str],
    test_commands: list[dict] | None = None,
    acceptance_criteria: list[dict] | None = None,
    diff_budget: dict | None = None,
    risk: dict | None = None,
    mutation_testing: dict | None = None,
    context_contracts: dict | None = None,
    estimate_points: int | None = None,
    stacked_on: str | None = None,
    model_selection: dict | None = None,
    extra_repos: list[str] | None = None,
) -> dict:
    chosen = set(parse_stages(stages))
    chosen.add("implement")
    if tests_required:
        chosen.add("implement-tests")
    if "draft-pr" in chosen and "commit-and-push" not in chosen:
        raise ManifestError("draft-pr requires commit-and-push")
    routes = deepcopy(DEFAULT_ROUTES)
    assigned_stages: set[str] = set()
    for assignment in route_assignments:
        stage, raw = parse_assignment(assignment)
        routes[stage] = parse_route(raw)
        assigned_stages.add(stage)
    selection: dict | None = None
    if estimate_points is not None:
        suggestion = review_suggestion(estimate_points)
        selection = {"estimate_points": estimate_points, "suggestion": deepcopy(suggestion)}
        if suggestion.get("route") and "review" not in assigned_stages:
            routes["review"] = deepcopy(suggestion["route"])
    effective_diff_budget = deepcopy(diff_budget or DEFAULT_DIFF_BUDGET)
    test_author_selection = test_author_suggestion(acceptance_criteria or [], effective_diff_budget)
    fallbacks: dict[str, list[dict]] = {stage: [] for stage in AI_STAGES}
    if "implement-tests" not in assigned_stages:
        routes["implement-tests"] = deepcopy(test_author_selection["suggestion"]["route"])
        fallbacks["implement-tests"] = deepcopy(test_author_selection["suggestion"]["fallbacks"])
    if "review" not in assigned_stages:
        review_fallbacks = (
            selection["suggestion"].get("fallbacks", DEFAULT_REVIEW_FALLBACKS)
            if selection
            else DEFAULT_REVIEW_FALLBACKS
        )
        fallbacks["review"] = deepcopy(review_fallbacks)
    assigned_fallback_stages: set[str] = set()
    for assignment in fallback_assignments:
        stage, raw = parse_assignment(assignment)
        if raw.lower() == "none":
            fallbacks[stage] = []
            assigned_fallback_stages.add(stage)
        else:
            if stage not in assigned_fallback_stages:
                fallbacks[stage] = []
                assigned_fallback_stages.add(stage)
            fallbacks.setdefault(stage, []).append(parse_route(raw))
    manifest = {
        "version": VERSION,
        "tests_required": bool(tests_required),
        "e2e_required": bool(e2e_required),
        "stages": [],
        "allowed_paths": sorted(dict.fromkeys(allowed_paths)),
        "test_paths": sorted(dict.fromkeys(test_paths)),
        "context_contracts": deepcopy(context_contracts or DEFAULT_CONTEXT_CONTRACTS),
        "test_commands": deepcopy(test_commands or []),
        "acceptance_criteria": deepcopy(acceptance_criteria or []),
        "diff_budget": effective_diff_budget,
        "risk": deepcopy(risk or {"level": "standard", "confirmed": True, "reasons": []}),
        "mutation_testing": deepcopy(mutation_testing or {"enabled": False}),
        "implementation_verification": {"required": True, "legacy_test_and_fix_selected": False},
    }
    if stacked_on:
        manifest["base_branch"] = stacked_on
    if extra_repos:
        manifest["extra_repos"] = list(dict.fromkeys(extra_repos))
    if selection:
        manifest["review_selection"] = selection
    if tests_required:
        manifest["test_author_selection"] = test_author_selection
    for stage in STAGE_ORDER:
        item = {
            "name": stage,
            "selected": stage in chosen,
            "required": stage == "implement" or (stage == "implement-tests" and tests_required),
        }
        if stage in AI_STAGES:
            item["route"] = routes[stage]
            item["fallbacks"] = fallbacks.get(stage, [])
        manifest["stages"].append(item)
    if model_selection is not None:
        from model_policy.core import validate_snapshot
        validate_snapshot(model_selection)
        selected_ai = {item["name"] for item in manifest["stages"] if item.get("selected") and item["name"] in AI_STAGES}
        if set(model_selection["routes"]) != selected_ai:
            raise ManifestError("Model selection must cover exactly the selected AI stages")
        for item in manifest["stages"]:
            rows = model_selection["routes"].get(item["name"])
            if rows:
                if item["name"] in assigned_stages and item["route"] != rows[0]:
                    raise ManifestError("Explicit route differs from model snapshot; re-evaluate with that choice")
                if item["name"] in assigned_fallback_stages and item["fallbacks"] != rows[1:]:
                    raise ManifestError("Explicit fallbacks differ from model snapshot")
                item["route"], item["fallbacks"] = deepcopy(rows[0]), deepcopy(rows[1:])
        manifest.pop("review_selection", None)
        manifest.pop("test_author_selection", None)
        manifest["model_selection"] = deepcopy(model_selection)
    problems = validate(manifest)
    if problems:
        raise ManifestError("; ".join(problems))
    return manifest


def load_manifest(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"pipeline manifest missing: {path}; rerun /specify") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid JSON in {path}: {exc}") from exc
    manifest = normalize_manifest(raw)
    problems = validate(manifest)
    if problems:
        raise ManifestError(f"invalid {path}: " + "; ".join(problems))
    return manifest


def runtime_manifest(
    manifest: dict,
    *,
    stages_override: str = "",
    route_assignments: list[str] | None = None,
    fallback_assignments: list[str] | None = None,
) -> dict:
    runtime = normalize_manifest(deepcopy(manifest))
    if stages_override:
        selected = set(parse_stages(stages_override))
        selected.add("implement")
        if runtime.get("tests_required"):
            selected.add("implement-tests")
        if "draft-pr" in selected and "commit-and-push" not in selected:
            raise ManifestError("draft-pr requires commit-and-push")
        for item in runtime["stages"]:
            item["selected"] = item["name"] in selected
    by_name = {item["name"]: item for item in runtime["stages"]}
    for assignment in route_assignments or []:
        stage, raw = parse_assignment(assignment)
        by_name[stage]["route"] = parse_route(raw)
    overridden_fallbacks: dict[str, list[dict]] = {}
    for assignment in fallback_assignments or []:
        stage, raw = parse_assignment(assignment)
        if raw.lower() == "none":
            overridden_fallbacks[stage] = []
        else:
            overridden_fallbacks.setdefault(stage, []).append(parse_route(raw))
    for stage, routes in overridden_fallbacks.items():
        by_name[stage]["fallbacks"] = routes
    runtime["runtime_override"] = bool(stages_override or route_assignments or fallback_assignments)
    if runtime["runtime_override"] and "model_selection" in runtime:
        # Explicit one-run changes preserve the approved source snapshot for audit.
        runtime["original_model_selection"] = runtime.pop("model_selection")
    problems = validate(runtime)
    if problems:
        raise ManifestError("; ".join(problems))
    return runtime


def selected_stages(manifest: dict) -> list[str]:
    manifest = normalize_manifest(manifest)
    selected = {item["name"] for item in manifest["stages"] if item.get("selected")}
    return [stage for stage in STAGE_ORDER if stage in selected]


def stage_routes(manifest: dict, stage: str) -> list[dict]:
    manifest = normalize_manifest(manifest)
    for item in manifest["stages"]:
        if item["name"] == stage:
            return [] if stage not in AI_STAGES else [item["route"], *(item.get("fallbacks") or [])]
    raise ManifestError(f"stage not found: {stage}")


def path_allowed(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    return any(fnmatch.fnmatch(normalized, pattern.lstrip("./")) for pattern in patterns)


def markdown(manifest: dict) -> str:
    manifest = normalize_manifest(manifest)
    lines = [
        "## Execution Pipeline",
        "",
        f"- Tests required before product implementation: **{'yes' if manifest.get('tests_required') else 'no'}**",
        f"- Local E2E execution inside implement: **{'yes' if manifest.get('e2e_required') else 'no'}**",
        "- Implementation always includes the deterministic verify/fix loop.",
        "- Provider fallbacks are suggested during specification and become executable only when confirmed; an empty fallback list fails closed.",
    ]
    if manifest.get("base_branch"):
        lines.append(
            f"- Stacked on `{manifest['base_branch']}`: diffs, scope, budget, the preflight sync and the draft PR use it instead of master."
        )
    if manifest.get("extra_repos"):
        listed = ", ".join(f"`{name}`" for name in manifest["extra_repos"])
        lines.append(f"- Extra repositories: {listed}.")
    lines += [
        "",
        "| Stage | Selected | Required | Provider | Model | Reasoning | Fallbacks |",
        "|---|---:|---:|---|---|---|---|",
    ]
    selection = manifest.get("review_selection") or {}
    if selection:
        suggestion = selection["suggestion"]
        if suggestion["review"] == "skip":
            lines.append(
                f"- {selection['estimate_points']}-point review suggestion: skip was offered; selection remains user-controlled."
            )
        else:
            lines.append(
                f"- {selection['estimate_points']}-point review suggestion: `{route_text(suggestion['route'])}` (user-confirmed route may differ)."
            )
    test_author = manifest.get("test_author_selection") or {}
    if test_author:
        suggestion = test_author["suggestion"]
        lines.append(
            "- Test-authoring suggestion: `{route}` with `{fallback}` fallback "
            "({count} planned test file(s), {lines} expected changed line(s); user-confirmed route may differ).".format(
                route=route_text(suggestion["route"]),
                fallback=route_text(suggestion["fallbacks"][0]),
                count=test_author["test_file_count"],
                lines=test_author["expected_lines"],
            )
        )
    selected_ai_routes = [
        item.get("route") or {}
        for item in manifest["stages"]
        if item.get("selected") and item.get("name") in AI_STAGES
    ]
    route_identities = {
        (str(route.get("provider") or ""), str(route.get("model") or ""))
        for route in selected_ai_routes
    }
    if len(selected_ai_routes) > 1 and len(route_identities) == 1:
        lines.append(
            "- Routing advisory: every AI stage uses the same provider/model. This is valid; "
            "consider a distinct test-author route only when independent coverage would help."
        )
    for item in manifest["stages"]:
        route = item.get("route") or {}
        fallbacks = ", ".join(route_text(value) for value in item.get("fallbacks") or []) or "none"
        lines.append(
            "| `{name}` | {selected} | {required} | {provider} | `{model}` | {reasoning} | {fallbacks} |".format(
                name=item["name"],
                selected="yes" if item.get("selected") else "no",
                required="yes" if item.get("required") else "no",
                provider=route.get("provider", "script"),
                model=route.get("model", "n/a"),
                reasoning=route.get("reasoning", "n/a"),
                fallbacks=fallbacks,
            )
        )
    lines += ["", "Context contracts:"]
    for stage in AI_STAGES:
        contract = manifest["context_contracts"][stage]
        lines.append(
            f"- `{stage}` reads {', '.join(contract['reads'])}; denied {', '.join(contract['denied'])}; writes {', '.join(contract['writes'])}."
        )
    if manifest.get("allowed_paths"):
        lines += ["", "Allowed implementation paths:", *[f"- `{path}`" for path in manifest["allowed_paths"]]]
    if manifest.get("test_paths"):
        lines += ["", "Test paths:", *[f"- `{path}`" for path in manifest["test_paths"]]]
    budget = manifest.get("diff_budget") or {}
    if budget:
        lines += [
            "",
            f"Diff budget: expected {budget.get('expected_files', 0)} files/{budget.get('expected_lines', 0)} lines; maximum {budget.get('max_files', 0)} files/{budget.get('max_lines', 0)} lines.",
        ]
    return "\n".join(lines) + "\n"


def _bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError("expected yes/no")


def _json_object(value: str, label: str) -> dict:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid {label} JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ManifestError(f"{label} must be a JSON object")
    return parsed


def _runtime_from_args(args: argparse.Namespace) -> tuple[Path, dict]:
    root = Path(args.root).resolve()
    plan_dir = find_plan_dir(root, args.task)
    base = load_manifest(plan_dir / "pipeline.json")
    runtime = runtime_manifest(
        base,
        stages_override=getattr(args, "stages", ""),
        route_assignments=getattr(args, "route", []),
        fallback_assignments=getattr(args, "fallback", []),
    )
    runtime["plan_dir"] = str(plan_dir)
    runtime["branch"] = plan_branch_dir(plan_dir).relative_to(root / "ai-plans").as_posix()
    runtime["task"] = args.task
    return plan_dir, runtime


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="write a confirmed plan manifest")
    create.add_argument("--plan-dir", required=True)
    create.add_argument("--stages", required=True)
    create.add_argument("--tests-required", type=_bool, required=True)
    create.add_argument("--e2e-required", type=_bool, required=True)
    create.add_argument("--route", action="append", default=[])
    create.add_argument("--fallback", action="append", default=[])
    create.add_argument("--allowed-path", action="append", default=[])
    create.add_argument("--test-path", action="append", default=[])
    create.add_argument("--test-command", action="append", default=[], help="JSON object")
    create.add_argument("--acceptance", action="append", default=[], help="JSON object")
    create.add_argument("--expected-files", type=int, default=DEFAULT_DIFF_BUDGET["expected_files"])
    create.add_argument("--max-files", type=int, default=DEFAULT_DIFF_BUDGET["max_files"])
    create.add_argument("--expected-lines", type=int, default=DEFAULT_DIFF_BUDGET["expected_lines"])
    create.add_argument("--max-lines", type=int, default=DEFAULT_DIFF_BUDGET["max_lines"])
    create.add_argument("--risk", choices=sorted(RISK_LEVELS), default="standard")
    create.add_argument("--risk-confirmed", type=_bool, default=True)
    create.add_argument("--risk-reason", action="append", default=[])
    create.add_argument("--mutation-command", default="", help="opt-in JSON argv list")
    create.add_argument("--estimate-points", type=int, choices=sorted(ESTIMATE_POINTS))
    create.add_argument("--model-selection", type=Path, help="Reviewed offline evaluator snapshot")
    create.add_argument("--base-branch", default="", help="unmerged branch a stacked plan is cut from")
    create.add_argument("--extra-repo", action="append", default=[], help="apaleo org repository attached to this branch")

    for name in ("resolve", "selected", "markdown", "plan-dir", "base-branch"):
        command = sub.add_parser(name)
        command.add_argument("--root", required=True)
        command.add_argument("--task", required=True)
        command.add_argument("--stages", default="")
        command.add_argument("--route", action="append", default=[])
        command.add_argument("--fallback", action="append", default=[])
        if name == "resolve":
            command.add_argument("--output", default="")

    routes = sub.add_parser("routes")
    routes.add_argument("--manifest", required=True)
    routes.add_argument("--stage", required=True)
    validate_cmd = sub.add_parser("validate")
    validate_cmd.add_argument("manifest")

    args = parser.parse_args()
    try:
        if args.command == "create":
            mutation = {"enabled": False}
            if args.mutation_command:
                argv = json.loads(args.mutation_command)
                mutation = {"enabled": True, "repo": "apaleo", "argv": argv}
            manifest = make_manifest(
                stages=parse_stages(args.stages),
                tests_required=args.tests_required,
                e2e_required=args.e2e_required,
                route_assignments=args.route,
                fallback_assignments=args.fallback,
                allowed_paths=args.allowed_path,
                test_paths=args.test_path,
                test_commands=[_json_object(value, "test-command") for value in args.test_command],
                acceptance_criteria=[_json_object(value, "acceptance") for value in args.acceptance],
                diff_budget={
                    "expected_files": args.expected_files,
                    "max_files": args.max_files,
                    "expected_lines": args.expected_lines,
                    "max_lines": args.max_lines,
                },
                risk={"level": args.risk, "confirmed": args.risk_confirmed, "reasons": args.risk_reason},
                mutation_testing=mutation,
                estimate_points=args.estimate_points,
                stacked_on=args.base_branch or None,
                model_selection=json.loads(args.model_selection.read_text()) if args.model_selection else None,
                extra_repos=args.extra_repo,
            )
            plan_dir = Path(args.plan_dir).resolve()
            plan_dir.mkdir(parents=True, exist_ok=True)
            path = plan_dir / "pipeline.json"
            path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(path)
            return 0
        if args.command == "validate":
            loaded = load_manifest(Path(args.manifest))
            suffix = " (v1 compatibility translation)" if loaded.get("legacy_source_version") else ""
            print(f"OK {args.manifest}{suffix}")
            return 0
        if args.command in {"resolve", "selected", "markdown", "plan-dir", "base-branch"}:
            plan_dir, runtime = _runtime_from_args(args)
            if args.command == "base-branch":
                print(base_branch(runtime))
            elif args.command == "selected":
                print("\n".join(selected_stages(runtime)))
            elif args.command == "markdown":
                print(markdown(runtime), end="")
            elif args.command == "plan-dir":
                print(plan_dir)
            else:
                body = json.dumps(runtime, indent=2) + "\n"
                if args.output:
                    Path(args.output).write_text(body, encoding="utf-8")
                    print(args.output)
                else:
                    print(body, end="")
            return 0
        if args.command == "routes":
            manifest = load_manifest(Path(args.manifest))
            for route in stage_routes(manifest, args.stage):
                print(route_text(route))
            return 0
    except (ManifestError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
