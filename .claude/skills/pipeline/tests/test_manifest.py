from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))

from common import FEATURE_REPOS  # noqa: E402
from pipeline_manifest import (  # noqa: E402
    ManifestError,
    base_branch,
    validate,
    make_manifest,
    find_plan_dir,
    markdown,
    parse_route,
    path_allowed,
    runtime_manifest,
    review_suggestion,
    selected_stages,
    stage_routes,
    test_author_suggestion,
)


class ManifestTests(unittest.TestCase):
    def make(self, stages: list[str] | None = None, tests: bool = True) -> dict:
        return make_manifest(**self._make_kwargs(stages, tests))

    def _make_kwargs(self, stages: list[str] | None = None, tests: bool = True) -> dict:
        return dict(
            stages=stages
            or [
                "implement-tests",
                "implement",
                "review",
                "commit-and-push",
                "draft-pr",
            ],
            tests_required=tests,
            e2e_required=tests,
            route_assignments=[],
            fallback_assignments=[],
            allowed_paths=["apaleo/src/**"],
            test_paths=["apaleo/test/**"],
            test_commands=[
                {
                    "id": "ac-1",
                    "repo": "apaleo",
                    "argv": ["dotnet", "test", "--filter", "FullyQualifiedName~ExpectedBehaviour"],
                    "parser": "dotnet",
                }
            ],
            acceptance_criteria=[
                {
                    "id": "AC-1",
                    "test": "ExpectedBehaviour",
                    "test_path": "apaleo/test/ExpectedBehaviourTests.cs",
                    "command": "ac-1",
                    "evidence_pattern": "Passed:\\s*1",
                    "red_required": True,
                }
            ],
            diff_budget={
                "expected_files": 2,
                "max_files": 4,
                "expected_lines": 40,
                "max_lines": 80,
            },
        )

    def test_base_branch_defaults_to_master_and_is_omitted(self) -> None:
        manifest = self.make()
        self.assertNotIn("base_branch", manifest)
        self.assertEqual(base_branch(manifest), "master")
        self.assertNotIn("Stacked on", markdown(manifest))

    def test_stacked_plan_records_and_renders_its_base_branch(self) -> None:
        manifest = make_manifest(**{**self._make_kwargs(), "stacked_on": "jdoe/sl-125-columns"})
        self.assertEqual(manifest["base_branch"], "jdoe/sl-125-columns")
        self.assertEqual(base_branch(manifest), "jdoe/sl-125-columns")
        self.assertIn("Stacked on `jdoe/sl-125-columns`", markdown(manifest))
        self.assertEqual(runtime_manifest(manifest)["base_branch"], "jdoe/sl-125-columns")

    def test_base_branch_must_be_a_plain_non_master_branch(self) -> None:
        for bad in ("master", "main", "", "-x", "a..b", "feature/", "x.lock", "has space", 5):
            manifest = copy.deepcopy(self.make())
            manifest["base_branch"] = bad
            self.assertTrue(
                any("base_branch" in error for error in validate(manifest)), f"accepted {bad!r}"
            )

    def test_defaults_match_confirmed_routes(self) -> None:
        manifest = self.make()
        routes = {stage: stage_routes(manifest, stage)[0] for stage in (
            "implement-tests", "implement", "review"
        )}
        self.assertEqual(routes["implement-tests"], {
            "provider": "cursor", "model": "claude-sonnet-5-thinking-high"
        })
        self.assertEqual(routes["implement"], {
            "provider": "cursor", "model": "grok-4.7-high"
        })
        self.assertEqual(routes["review"], {
            "provider": "cursor", "model": "gpt-5.6-sol-high"
        })
        self.assertEqual(
            stage_routes(manifest, "implement-tests")[1:],
            [{"provider": "claude", "model": "sonnet", "reasoning": "high"}],
        )

    def test_estimate_only_suggests_review_and_never_forces_stage_selection(self) -> None:
        one_point = self.make(["implement"], tests=False)
        self.assertNotIn("review", selected_stages(one_point))

        two_point = make_manifest(
            stages=["implement", "review"],
            tests_required=False,
            e2e_required=False,
            route_assignments=[],
            fallback_assignments=[],
            allowed_paths=["apaleo/src/**"],
            test_paths=["apaleo/test/**"],
            test_commands=[{"id": "ac-1", "repo": "apaleo", "argv": ["dotnet", "test"], "parser": "dotnet"}],
            acceptance_criteria=[{
                "id": "AC-1", "test": "ExpectedBehaviour", "test_path": "apaleo/test/ExpectedBehaviourTests.cs",
                "command": "ac-1", "evidence_pattern": "Passed", "red_required": False,
            }],
            estimate_points=2,
        )
        self.assertEqual(
            stage_routes(two_point, "review")[0],
            {"provider": "cursor", "model": "claude-sonnet-5-thinking-high"},
        )
        self.assertEqual(
            stage_routes(two_point, "review")[1:],
            [
                {"provider": "cursor", "model": "grok-4.7-high"},
                {"provider": "claude", "model": "sonnet", "reasoning": "high"},
                {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high"},
            ],
        )
        self.assertEqual(two_point["review_selection"]["suggestion"], review_suggestion(2))
        self.assertEqual(review_suggestion(1)["review"], "skip")

    def test_test_author_suggestion_uses_opus_for_many_files_or_large_diff(self) -> None:
        small = test_author_suggestion(
            [{"test_path": "apaleo/test/SmallTests.cs"}], {"expected_lines": 80}
        )
        self.assertEqual(
            small["suggestion"]["route"],
            {"provider": "cursor", "model": "claude-sonnet-5-thinking-high"},
        )
        many_files = test_author_suggestion(
            [{"test_path": f"apaleo/test/Test{i}.cs"} for i in range(4)], {"expected_lines": 80}
        )
        self.assertEqual(
            many_files["suggestion"]["route"],
            {"provider": "cursor", "model": "claude-opus-5-5-high"},
        )
        large_file = test_author_suggestion(
            [{"test_path": "apaleo/test/LargeTests.cs"}], {"expected_lines": 300}
        )
        self.assertEqual(
            large_file["suggestion"]["route"],
            {"provider": "cursor", "model": "claude-opus-5-5-high"},
        )

    def test_explicit_review_route_wins_over_estimate_suggestion(self) -> None:
        manifest = make_manifest(
            stages=["implement", "review"],
            tests_required=False,
            e2e_required=False,
            route_assignments=["review=claude:opus:high"],
            fallback_assignments=[],
            allowed_paths=["apaleo/src/**"],
            test_paths=["apaleo/test/**"],
            test_commands=[{"id": "ac-1", "repo": "apaleo", "argv": ["dotnet", "test"], "parser": "dotnet"}],
            acceptance_criteria=[{
                "id": "AC-1", "test": "ExpectedBehaviour", "test_path": "apaleo/test/ExpectedBehaviourTests.cs",
                "command": "ac-1", "evidence_pattern": "Passed", "red_required": False,
            }],
            estimate_points=3,
        )
        self.assertEqual(
            stage_routes(manifest, "review")[0],
            {"provider": "claude", "model": "opus", "reasoning": "high"},
        )

    def test_required_stages_are_inserted(self) -> None:
        manifest = self.make(["review"], tests=True)
        self.assertEqual(
            selected_stages(manifest),
            ["implement-tests", "implement", "review"],
        )

    def test_tests_required_allows_green_only_acceptance_criteria(self) -> None:
        manifest = make_manifest(
            stages=["implement-tests", "implement"],
            tests_required=True,
            e2e_required=False,
            route_assignments=[],
            fallback_assignments=[],
            allowed_paths=["apaleo/src/**"],
            test_paths=["apaleo/test/**"],
            test_commands=[{
                "id": "ac-1", "repo": "apaleo", "argv": ["dotnet", "test"], "parser": "dotnet",
            }],
            acceptance_criteria=[{
                "id": "AC-1", "test": "ExpectedBehaviour",
                "test_path": "apaleo/test/ExpectedBehaviourTests.cs",
                "command": "ac-1", "evidence_pattern": "Passed", "red_required": False,
            }],
        )
        self.assertFalse(manifest["acceptance_criteria"][0]["red_required"])

    def test_test_authoring_stage_requires_explicit_test_contract(self) -> None:
        with self.assertRaisesRegex(ManifestError, "tests_required=true"):
            self.make(["implement-tests", "implement"], tests=False)

    def test_draft_requires_publish(self) -> None:
        with self.assertRaises(ManifestError):
            self.make(["implement", "draft-pr"], tests=False)

    def test_runtime_override_is_ephemeral(self) -> None:
        manifest = self.make()
        original = copy.deepcopy(manifest)
        runtime = runtime_manifest(
            manifest,
            stages_override="implement,review",
            route_assignments=["review=claude:opus:high"],
            fallback_assignments=["review=cursor:cursor-grok-4.6-high"],
        )
        self.assertEqual(manifest, original)
        self.assertEqual(
            selected_stages(runtime),
            ["implement-tests", "implement", "review"],
        )
        self.assertEqual(stage_routes(runtime, "review"), [
            {"provider": "claude", "model": "opus", "reasoning": "high"},
            {"provider": "cursor", "model": "cursor-grok-4.6-high"},
        ])

    def test_codex_and_claude_can_use_host_default_effort(self) -> None:
        for route in ("codex:gpt-5.6-terra", "claude:opus"):
            with self.subTest(route=route):
                self.assertNotIn("reasoning", parse_route(route))
        with self.assertRaisesRegex(ManifestError, "encoded"):
            parse_route("cursor:cursor-grok-4.6-high:high")
        with self.assertRaisesRegex(ManifestError, "Claude reasoning"):
            parse_route("claude:opus:ultra")

    def test_runtime_can_clear_confirmed_fallback(self) -> None:
        manifest = runtime_manifest(
            self.make(),
            fallback_assignments=["review=cursor:cursor-grok-4.6-high"],
        )
        runtime = runtime_manifest(manifest, fallback_assignments=["review=none"])
        self.assertEqual(len(stage_routes(runtime, "review")), 1)

    def test_unsafe_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(ManifestError, "unsafe or non-worktree path"):
            make_manifest(
                stages=["implement"],
                tests_required=False,
                e2e_required=False,
                route_assignments=[],
                fallback_assignments=[],
                allowed_paths=["../secrets/**"],
                test_paths=["apaleo/test/**"],
                test_commands=[
                    {
                        "id": "ac-1",
                        "repo": "apaleo",
                        "argv": ["dotnet", "test"],
                        "parser": "dotnet",
                    }
                ],
                acceptance_criteria=[
                    {
                        "id": "AC-1",
                        "test": "ExpectedBehaviour",
                        "test_path": "apaleo/test/ExpectedBehaviourTests.cs",
                        "command": "ac-1",
                        "evidence_pattern": "Passed",
                        "red_required": True,
                    }
                ],
                diff_budget={"expected_files": 1, "max_files": 1, "expected_lines": 1, "max_lines": 1},
            )

    def test_agent_skills_paths_and_repo_are_valid(self) -> None:
        manifest = make_manifest(
            stages=["implement"],
            tests_required=True,
            e2e_required=False,
            route_assignments=[],
            fallback_assignments=[],
            allowed_paths=["agent-skills/plugins/**"],
            test_paths=["agent-skills/plugins/linear-issue-writer/**"],
            test_commands=[
                {
                    "id": "catalog-check",
                    "repo": "agent-skills",
                    "argv": ["python3", "scripts/sync_cursor_catalog.py", "--check"],
                    "parser": "generic",
                    "success_pattern": "ok",
                }
            ],
            acceptance_criteria=[
                {
                    "id": "AC-1",
                    "test": "catalog-check",
                    "test_path": "agent-skills/plugins/linear-issue-writer/skills/linear-issue-writer/SKILL.md",
                    "command": "catalog-check",
                    "evidence_pattern": "ok",
                    "red_required": True,
                }
            ],
            diff_budget={"expected_files": 4, "max_files": 8, "expected_lines": 80, "max_lines": 200},
        )
        self.assertEqual(manifest["test_commands"][0]["repo"], "agent-skills")
        self.assertTrue(path_allowed("agent-skills/plugins/linear-issue-writer/SKILL.md", [
            "agent-skills/plugins/**"
        ]))

    def test_angular_api_proxy_paths_and_repo_are_valid(self) -> None:
        manifest = make_manifest(
            stages=["implement"],
            tests_required=False,
            e2e_required=False,
            route_assignments=[],
            fallback_assignments=[],
            allowed_paths=["angular-api-proxy/openapi-generator-solution/**"],
            test_paths=["angular-api-proxy/openapi-generator-solution/tools/tests/**"],
            test_commands=[
                {
                    "id": "generator-discovery",
                    "repo": "angular-api-proxy",
                    "argv": ["yarn", "test:generator"],
                    "parser": "generic",
                    "success_pattern": "ALL TESTS PASSED",
                }
            ],
            acceptance_criteria=[
                {
                    "id": "AC-1",
                    "test": "discovered_calendar_is_generated_and_wired",
                    "test_path": (
                        "angular-api-proxy/openapi-generator-solution/tools/tests/"
                        "core-module-discovery.test.sh"
                    ),
                    "command": "generator-discovery",
                    "evidence_pattern": "PASS",
                    "red_required": True,
                }
            ],
            diff_budget={
                "expected_files": 20,
                "max_files": 26,
                "expected_lines": 470,
                "max_lines": 760,
            },
        )
        self.assertEqual(manifest["test_commands"][0]["repo"], "angular-api-proxy")
        self.assertTrue(
            path_allowed(
                "angular-api-proxy/openapi-generator-solution/tools/core-module-generator.sh",
                ["angular-api-proxy/openapi-generator-solution/**"],
            )
        )

    def test_apaleo_only_manifest_is_unaffected(self) -> None:
        """Adding an optional repo must not change ordinary apaleo-only plans."""
        manifest = make_manifest(
            stages=["implement"],
            tests_required=False,
            e2e_required=False,
            route_assignments=[],
            fallback_assignments=[],
            allowed_paths=["apaleo/src/Apaleo.Calendar/**"],
            test_paths=["apaleo/test/Apaleo.Calendar.Tests/**"],
            test_commands=[
                {
                    "id": "calendar-unit",
                    "repo": "apaleo",
                    "argv": ["dotnet", "test", "test/Apaleo.Calendar.Tests"],
                    "parser": "dotnet",
                }
            ],
            acceptance_criteria=[
                {
                    "id": "AC-1",
                    "test": "ExpectedBehaviour",
                    "test_path": "apaleo/test/Apaleo.Calendar.Tests/ExpectedBehaviourTests.cs",
                    "command": "calendar-unit",
                    "evidence_pattern": r"Passed:\s*1",
                    "red_required": True,
                }
            ],
            diff_budget={
                "expected_files": 2,
                "max_files": 4,
                "expected_lines": 40,
                "max_lines": 90,
            },
        )
        self.assertEqual(manifest["test_commands"][0]["repo"], "apaleo")
        self.assertFalse(
            path_allowed(
                "angular-api-proxy/openapi-generator-solution/generate-modules.sh",
                ["apaleo/src/Apaleo.Calendar/**"],
            )
        )

    def test_feature_repos_inventory(self) -> None:
        """pipeline/common.py and pipeline/root.sh must declare the same repos.

        root.sh keeps its own bash array; this pins the Python side so the two
        cannot drift silently when a repo is added or retired.
        """
        self.assertEqual(
            FEATURE_REPOS,
            ("apaleo", "development", "identity", "agent-skills", "angular-api-proxy"),
        )
        root_sh = (PIPELINE / "root.sh").read_text(encoding="utf-8")
        self.assertIn(
            "FEATURE_REPOS=(apaleo development identity agent-skills angular-api-proxy)",
            root_sh,
        )
        self.assertIn(
            "GITHUB_REPOS=(apaleo/apaleo apaleo/development apaleo/identity "
            "apaleo/agent-skills apaleo/angular-api-proxy)",
            root_sh,
        )

    def test_all_ai_stages_may_share_one_route(self) -> None:
        manifest = make_manifest(
                stages=["implement-tests", "implement"],
                tests_required=True,
                e2e_required=False,
                route_assignments=[
                    "implement-tests=codex:gpt-5.6-terra:high",
                    "implement=codex:gpt-5.6-terra:high",
                ],
                fallback_assignments=[],
                allowed_paths=["apaleo/src/**"],
                test_paths=["apaleo/test/**"],
                test_commands=[
                    {"id": "ac-1", "repo": "apaleo", "argv": ["dotnet", "test"], "parser": "dotnet"}
                ],
                acceptance_criteria=[
                    {
                        "id": "AC-1",
                        "test": "ExpectedBehaviour",
                        "test_path": "apaleo/test/ExpectedBehaviourTests.cs",
                        "command": "ac-1",
                        "evidence_pattern": "Passed",
                        "red_required": True,
                    }
                ],
                diff_budget={"expected_files": 1, "max_files": 1, "expected_lines": 1, "max_lines": 1},
            )
        self.assertEqual(
            stage_routes(manifest, "implement-tests")[0],
            stage_routes(manifest, "implement")[0],
        )
        self.assertIn("Routing advisory", markdown(manifest))

    def test_path_boundaries_use_repo_relative_globs(self) -> None:
        self.assertTrue(path_allowed("development/src/proxy/calendar-nsfw/foo/a.ts", [
            "development/src/proxy/calendar-nsfw/**"
        ]))
        self.assertFalse(path_allowed("development/src/config.ts", [
            "development/src/proxy/calendar-nsfw/**"
        ]))

    def test_context_contract_cannot_reintroduce_denied_review_history(self) -> None:
        manifest = self.make()
        manifest["context_contracts"]["review"]["reads"].append("progress")
        from pipeline_manifest import validate

        self.assertTrue(
            any("context_contracts.review.reads" in error for error in validate(manifest))
        )

    def test_latest_versioned_plan_wins_without_changing_branch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            branch = root / "ai-plans" / "jdoe" / "hc-42-example"
            branch.mkdir(parents=True)
            for directory in (branch, branch / "v2"):
                directory.mkdir(exist_ok=True)
                (directory / "prompt.md").write_text("task", encoding="utf-8")
                (directory / "product.md").write_text("product", encoding="utf-8")
                (directory / "implementation.md").write_text("plan", encoding="utf-8")
                (directory / "deferred-scope.md").write_text("none", encoding="utf-8")
                (directory / "pipeline.json").write_text("{}", encoding="utf-8")
            self.assertEqual(find_plan_dir(root, "HC-42"), branch / "v2")

    def test_incomplete_version_cannot_borrow_contract_files_from_v1(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            branch = root / "ai-plans" / "jdoe" / "hc-42-example"
            version = branch / "v2"
            version.mkdir(parents=True)
            for name in (
                "prompt.md",
                "product.md",
                "implementation.md",
                "deferred-scope.md",
                "pipeline.json",
            ):
                (branch / name).write_text(name, encoding="utf-8")
            for name in ("product.md", "implementation.md", "pipeline.json"):
                (version / name).write_text(name, encoding="utf-8")
            self.assertEqual(find_plan_dir(root, "HC-42"), branch)

    def test_plan_dir_command_returns_latest_version_for_script_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            branch = root / "ai-plans" / "jdoe" / "hc-42-example"
            version = branch / "v2"
            version.mkdir(parents=True)
            (version / "prompt.md").write_text("task", encoding="utf-8")
            (version / "product.md").write_text("product", encoding="utf-8")
            (version / "implementation.md").write_text("plan", encoding="utf-8")
            (version / "deferred-scope.md").write_text("none", encoding="utf-8")
            (version / "pipeline.json").write_text(
                json.dumps(self.make()), encoding="utf-8"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(PIPELINE / "pipeline_manifest.py"),
                    "plan-dir",
                    "--root",
                    str(root),
                    "--task",
                    "HC-42",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(result.stdout.strip()).resolve(), version.resolve())

    def test_v1_test_and_fix_is_translated_in_memory(self) -> None:
        legacy = copy.deepcopy(self.make())
        legacy["version"] = 1
        for key in (
            "context_contracts",
            "test_commands",
            "acceptance_criteria",
            "diff_budget",
            "risk",
            "mutation_testing",
            "implementation_verification",
        ):
            legacy.pop(key, None)
        legacy["stages"].insert(
            3,
            {
                "name": "test-and-fix",
                "selected": True,
                "required": True,
                "route": {"provider": "cursor", "model": "cursor-grok-4.6-medium"},
                "fallbacks": [],
            },
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pipeline.json"
            path.write_text(json.dumps(legacy), encoding="utf-8")
            from pipeline_manifest import load_manifest

            loaded = load_manifest(path)
        self.assertEqual(selected_stages(loaded), [
            "implement-tests",
            "implement",
            "review",
            "commit-and-push",
            "draft-pr",
        ])
        self.assertTrue(loaded["implementation_verification"]["legacy_test_and_fix_selected"])


if __name__ == "__main__":
    unittest.main()
