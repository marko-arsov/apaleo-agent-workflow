from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import unittest.mock
from unittest.mock import patch


PIPELINE = Path(__file__).resolve().parents[1]
ROOT = PIPELINE.parents[2]
sys.path.insert(0, str(PIPELINE))

import implement_pipeline as runner  # noqa: E402
from models import models_match, parse_stream_json  # noqa: E402
from pipeline_state import (  # noqa: E402
    bind_plan,
    invalidate_from,
    load as load_state,
    mark_complete,
    mark_failed,
    normalize_completed_prefix,
    remaining,
)


class RunnerContractTests(unittest.TestCase):
    def test_zombie_pid_is_not_treated_as_an_active_worker(self) -> None:
        with patch.object(runner.os, "kill"), patch.object(
            runner.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(["ps"], 0, "Z\n", ""),
        ):
            self.assertFalse(runner.pid_alive(42))

    def test_stage_policy_snapshot_ignores_unrelated_workflow_files(self) -> None:
        old_root = runner.ROOT
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / "AGENTS.md").write_text("agents", encoding="utf-8")
                (root / ".claude/skills/implement-tests").mkdir(parents=True)
                (root / ".claude/skills/references").mkdir(parents=True)
                (root / ".claude/skills/implement-tests/SKILL.md").write_text("tests", encoding="utf-8")
                (root / ".claude/skills/references/e2e-stack.md").write_text("e2e", encoding="utf-8")
                (root / ".claude/skills/WORKFLOW.md").write_text("unrelated", encoding="utf-8")
                runner.ROOT = root
                before = runner.workflow_policy_snapshot("implement-tests")
                (root / ".claude/skills/WORKFLOW.md").write_text("changed", encoding="utf-8")
                self.assertEqual([], runner.ensure_workflow_policy_unchanged("implement-tests", before))
                (root / ".claude/skills/implement-tests/SKILL.md").write_text("changed", encoding="utf-8")
                self.assertEqual(
                    [str(root / ".claude/skills/implement-tests/SKILL.md")],
                    runner.ensure_workflow_policy_unchanged("implement-tests", before),
                )
        finally:
            runner.ROOT = old_root

    def test_overdue_provider_tool_call_uses_declared_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            stream = Path(temp) / "stream.jsonl"
            stream.write_text(
                json.dumps(
                    {
                        "type": "tool_call",
                        "subtype": "started",
                        "call_id": "tool-1",
                        "timestamp_ms": 1_000_000,
                        "tool_call": {"shellToolCall": {"args": {"timeout": 60_000}}},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(runner.overdue_provider_tool_call(stream, 1_179, 120), "")
            self.assertIn(
                "shellToolCall exceeded its declared 60000ms timeout",
                runner.overdue_provider_tool_call(stream, 1_181, 120),
            )

    def test_completed_provider_tool_is_not_overdue(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            stream = Path(temp) / "stream.jsonl"
            stream.write_text(
                "\n".join(
                    json.dumps(event)
                    for event in (
                        {
                            "type": "tool_call",
                            "subtype": "started",
                            "call_id": "tool-1",
                            "timestamp_ms": 1_000_000,
                            "tool_call": {"shellToolCall": {"args": {"timeout": 60_000}}},
                        },
                        {"type": "tool_call", "subtype": "completed", "call_id": "tool-1"},
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(runner.overdue_provider_tool_call(stream, 2_000, 120), "")

    def test_failed_test_stage_recovers_from_valid_current_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plan = Path(temp)
            (plan / "tests-implementation-1.md").write_text(
                "New product/architectural decisions: none\n", encoding="utf-8"
            )
            (plan / "red-proof.md").write_text("Failure level: assertion\n", encoding="utf-8")
            (plan / "progress.md").write_text("No new decisions.\n", encoding="utf-8")
            state = {"failed_stage": "implement-tests"}
            manifest = {
                "test_paths": ["apaleo/test/**"],
                "allowed_paths": ["apaleo/src/**"],
            }
            with (
                patch.object(runner, "plan_branch_dir", return_value=plan),
                patch.object(runner, "working_paths", return_value=["apaleo/test/Foo.cs"]),
                patch.object(runner, "validate_red_proof"),
            ):
                evidence = runner.recover_implement_tests_from_artifacts(
                    "branch", plan, manifest, state
                )
            self.assertIn("recovered from tests-implementation-1.md", evidence)
    def test_review_postcondition_repeats_fast_rule_scan_without_rerunning_tests(self) -> None:
        manifest = {"allowed_paths": ["apaleo/**"], "test_paths": []}
        report = Path("/tmp/review-1.md")
        shared = [
            patch.object(runner, "snapshot", return_value={}),
            patch.object(runner, "working_paths", return_value=[]),
            patch.object(runner, "stage_paths_allowed", return_value=True),
            patch.object(runner, "new_artifact_paths", return_value=[report]),
            patch.object(runner, "assert_no_new_decisions"),
            patch.object(runner, "assert_review_gates"),
        ]
        for item in shared:
            item.start()
        try:
            with patch.object(runner, "snapshot_delta", return_value=[]), patch.object(
                runner, "verify_implementation"
            ) as verify, patch.object(runner, "precommit_scan", return_value={"status": "passed"}) as scan:
                runner.verify_stage("review", "branch", Path("/tmp/plan"), manifest, {})
                verify.assert_not_called()
                scan.assert_called_once_with(runner.ROOT, "branch")

            with patch.object(
                runner, "snapshot_delta", return_value=["apaleo/src/Foo.cs"]
            ), patch.object(
                runner,
                "verify_implementation",
                return_value={"commands": [], "convention_scan": {"status": "passed"}},
            ) as verify, patch.object(runner, "precommit_scan", return_value={"status": "passed"}) as scan:
                runner.verify_stage("review", "branch", Path("/tmp/plan"), manifest, {})
                verify.assert_not_called()
                scan.assert_called_once_with(runner.ROOT, "branch")
        finally:
            for item in reversed(shared):
                item.stop()

    def test_review_postcondition_rejects_a_rule_scan_failure(self) -> None:
        manifest = {"allowed_paths": ["apaleo/**"], "test_paths": []}
        report = Path("/tmp/review-1.md")
        with (
            patch.object(runner, "snapshot", return_value={}),
            patch.object(runner, "snapshot_delta", return_value=["apaleo/src/Foo.cs"]),
            patch.object(runner, "working_paths", return_value=["apaleo/src/Foo.cs"]),
            patch.object(runner, "stage_paths_allowed", return_value=True),
            patch.object(runner, "new_artifact_paths", return_value=[report]),
            patch.object(
                runner,
                "precommit_scan",
                side_effect=runner.VerificationError("blocking convention matched"),
            ),
        ):
            with self.assertRaisesRegex(runner.PipelineError, "deterministic secret/convention scan"):
                runner.verify_stage("review", "branch", Path("/tmp/plan"), manifest, {})

    def test_initial_provider_commands_start_fresh_persisted_sessions(self) -> None:
        old = (runner.find_cursor, runner.find_codex, runner.find_claude)
        runner.find_cursor = lambda: "/tmp/agent"
        runner.find_codex = lambda: "/tmp/codex"
        runner.find_claude = lambda: "/tmp/claude"
        try:
            with tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / "last.txt"
                commands = [
                    runner.provider_command(
                        {"provider": "cursor", "model": "cursor-grok-4.6-high"}, "p", output
                    ),
                    runner.provider_command(
                        {"provider": "codex", "model": "gpt-5.6-terra", "reasoning": "high"}, "p", output
                    ),
                    runner.provider_command(
                        {"provider": "claude", "model": "opus", "reasoning": "high"}, "p", output
                    ),
                ]
        finally:
            runner.find_cursor, runner.find_codex, runner.find_claude = old
        for command in commands:
            self.assertNotIn("--resume", command)
            self.assertNotIn("--continue", command)
        self.assertNotIn("--ephemeral", commands[1])
        self.assertNotIn("--no-session-persistence", commands[2])
        claude = commands[2]
        self.assertEqual(
            claude[claude.index("--output-format") + 1],
            "stream-json",
        )
        self.assertIn("--verbose", claude)

    def test_paused_stage_commands_resume_the_exact_provider_session(self) -> None:
        old = (runner.find_cursor, runner.find_codex, runner.find_claude)
        runner.find_cursor = lambda: "/tmp/agent"
        runner.find_codex = lambda: "/tmp/codex"
        runner.find_claude = lambda: "/tmp/claude"
        try:
            with tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / "last.txt"
                commands = [
                    runner.provider_resume_command(
                        {"provider": "cursor", "model": "cursor-grok-4.6-high"},
                        "cursor-session",
                        "answer",
                        output,
                    ),
                    runner.provider_resume_command(
                        {"provider": "codex", "model": "gpt-5.6-terra", "reasoning": "high"},
                        "codex-session",
                        "answer",
                        output,
                    ),
                    runner.provider_resume_command(
                        {"provider": "claude", "model": "opus", "reasoning": "high"},
                        "claude-session",
                        "answer",
                        output,
                    ),
                ]
        finally:
            runner.find_cursor, runner.find_codex, runner.find_claude = old
        self.assertEqual(commands[0][commands[0].index("--resume") + 1], "cursor-session")
        self.assertIn("resume", commands[1])
        self.assertIn("codex-session", commands[1])
        self.assertEqual(commands[2][commands[2].index("--resume") + 1], "claude-session")
        self.assertIn("--verbose", commands[2])

    def test_autonomy_continuation_does_not_ask_for_reversible_local_work(self) -> None:
        prompt = runner.continuation_prompt("review", "Docker image pull timed out")
        self.assertIn("same provider session", prompt)
        self.assertIn("lock-protected local container/image switching", prompt)
        self.assertIn("PIPELINE_INPUT_REQUIRED", prompt)

    def test_recoverable_block_classifier_rejects_hc3333_permission_questions(self) -> None:
        recoverable = (
            ("implement", "The test helper coalesces null recurrence and must be corrected."),
            ("implement", "CalendarEventDto does not contain a definition for EntityId."),
            ("review", "May I authorize temporary local API container replacement for Swagger?"),
            ("review", "Docker timed out pulling the registry image; should I try again?"),
        )
        for stage, reason in recoverable:
            with self.subTest(stage=stage, reason=reason):
                self.assertTrue(runner.recoverable_block_reason(stage, reason))
        self.assertFalse(
            runner.recoverable_block_reason(
                "review", "Should the public endpoint return 404 or 403 for another property?"
            )
        )
        self.assertFalse(runner.concrete_user_action("May I authorize the local container swap?"))
        self.assertFalse(runner.concrete_user_action("Docker pull timed out; should I try again?"))
        self.assertTrue(
            runner.concrete_user_action(
                "Recovery is exhausted; please authenticate to the private registry."
            )
        )

    def test_model_names_normalize(self) -> None:
        self.assertTrue(models_match("cursor-grok-4.6-high", "Cursor Grok 4.6 High"))
        self.assertTrue(models_match("grok-4.7-high", "Grok 4.7  High"))
        self.assertTrue(models_match("grok-4.7-medium-fast", "Grok 4.7  Medium Fast\u200b\u200b"))
        self.assertTrue(models_match("opus", "claude-opus-4-1"))
        self.assertTrue(
            models_match("claude-sonnet-5-thinking-high", "Claude Sonnet 5 300K High")
        )
        self.assertTrue(models_match("gpt-5.6-sol-high", "GPT-5.6 Sol 272K High"))
        self.assertTrue(
            models_match("claude-opus-5-thinking-high", "Claude Opus 5 200K High")
        )
        self.assertTrue(models_match("claude-opus-5-5-high", "Claude Opus 5.5 1M High"))
        self.assertFalse(models_match("claude-opus-5-5-high", "Claude Opus 5 1M High"))
        self.assertFalse(models_match("claude-opus-5-thinking-high", "Claude Opus 5.5 1M High"))
        self.assertFalse(models_match("cursor-grok-4.6-high", "cursor-grok-4.6-medium"))
        self.assertFalse(models_match("grok-4.7-high", "grok-4.7-medium"))
        self.assertFalse(
            models_match("claude-sonnet-5-thinking-high", "Claude Sonnet 4 200K High")
        )
        self.assertFalse(models_match("gpt-5.6-sol-high", "GPT-5.6 Sol Medium"))

    def test_cursor_model_limit_does_not_open_a_provider_wide_circuit(self) -> None:
        self.assertFalse(runner.provider_wide_failure("cursor", "You've hit your individual spend limit"))
        self.assertTrue(runner.provider_wide_failure("cursor", "authentication failed"))
        self.assertTrue(runner.provider_wide_failure("claude", "You've hit your individual spend limit"))
        self.assertTrue(
            runner.provider_wide_failure(
                "claude",
                "Failed to authenticate: OAuth session expired and could not be refreshed",
            )
        )

    def test_codex_thread_id_is_captured_for_same_session_continuation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            stream = Path(temp) / "codex.jsonl"
            stream.write_text(
                json.dumps({"type": "thread.started", "thread_id": "thread-42"}) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(parse_stream_json(stream)["session_id"], "thread-42")

    def test_new_state_has_no_pending_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            self.assertIsNone(load_state(Path(temp), "HC-42")["pending_input"])

    def test_stage_completion_clears_its_pending_input(self) -> None:
        state = {
            "completed": [],
            "pending_input": {"stage": "review", "session_id": "session-42"},
        }
        mark_complete(state, "review", "verified")
        self.assertIsNone(state["pending_input"])

    def test_waiting_recap_distinguishes_session_answer_from_local_intervention(self) -> None:
        manifest = {
            "stages": [
                {
                    "name": "implement",
                    "selected": True,
                    "route": {"provider": "cursor", "model": "cursor-grok-4.6-high"},
                    "fallbacks": [],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            session_recap = runner.recap(
                run_dir,
                "HC-42",
                "markoarsov/hc-42",
                manifest,
                [],
                "WAITING_FOR_INPUT",
                "question",
                resumable_session=True,
            ).read_text(encoding="utf-8")
            self.assertIn("--answer '<answer>'", session_recap)
            local_recap = runner.recap(
                run_dir,
                "HC-42",
                "markoarsov/hc-42",
                manifest,
                [],
                "WAITING_FOR_INPUT",
                "start Docker manually",
            ).read_text(encoding="utf-8")
            self.assertNotIn("--answer", local_recap)
            self.assertIn("Complete the requested local intervention", local_recap)

    def test_hc3333_dry_run_preserves_its_confirmed_routes(self) -> None:
        # Confirmed manifests are immutable execution contracts. Changing a
        # global default must not silently reroute an existing plan.
        result = subprocess.run(
            [
                str(PIPELINE / "implement-pipeline.sh"),
                "HC-3333",
                "--dry-run",
                "--no-resume",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in (
            "implement-tests: codex:gpt-5.6-terra:high",
            "implement: cursor:cursor-grok-4.6-high",
            "review: codex:gpt-5.6-terra:high",
            "commit-and-push: script",
            "draft-pr: script",
        ):
            self.assertIn(expected, result.stdout)
        self.assertNotIn("test-and-fix:", result.stdout)

    def test_commit_path_runs_fast_precommit_scanners(self) -> None:
        script = (PIPELINE.parent / "commit" / "commit.sh").read_text(encoding="utf-8")
        self.assertIn('verification.py"', script)
        self.assertIn("--precommit", script)

    def test_invalid_range_does_not_run_past_to_stage(self) -> None:
        with self.assertRaisesRegex(ValueError, "precedes"):
            remaining(
                ["implement", "review", "commit-and-push"],
                [],
                from_stage="review",
                to_stage="implement",
            )

    def test_hc_spellings_share_one_progress_key(self) -> None:
        for value in (
            "HC-3333",
            "hc3333",
            "c3333",
            "markoarsov/hc-3333-add-calendar-event-fork-endpoint",
        ):
            with self.subTest(value=value):
                self.assertEqual(runner.canonical_task(value), "HC-3333")

    def test_rerun_invalidates_every_downstream_gate(self) -> None:
        order = [
            "implement-tests",
            "implement",
            "review",
            "commit-and-push",
            "draft-pr",
        ]
        state = {
            "completed": list(order),
            "evidence": {stage: "ok" for stage in order},
        }
        invalidated = invalidate_from(state, order, "implement")
        self.assertEqual(invalidated, order[1:])
        self.assertEqual(state["completed"], ["implement-tests"])
        self.assertEqual(state["evidence"], {"implement-tests": "ok"})

    def test_missing_new_test_stage_invalidates_old_implement_completion(self) -> None:
        selected = ["implement-tests", "implement", "review"]
        state = {
            "completed": ["implement", "review"],
            "evidence": {"implement": "old", "review": "old"},
        }
        invalidated = normalize_completed_prefix(state, selected)
        self.assertEqual(invalidated, ["implement", "review"])
        self.assertEqual(state["completed"], [])
        self.assertEqual(remaining(selected, state["completed"]), selected)

    def test_legacy_implement_without_retired_verification_is_rerun(self) -> None:
        manifest = {
            "implementation_verification": {"legacy_test_and_fix_selected": True}
        }
        state = {
            "completed": ["implement", "review", "commit-and-push"],
            "evidence": {stage: "old" for stage in ("implement", "review", "commit-and-push")},
            "implementation_verification_complete": False,
        }
        invalidated = runner.reset_unverified_legacy_implementation(state, manifest)
        self.assertEqual(invalidated, ["implement", "review", "commit-and-push"])
        self.assertEqual(state["completed"], [])

    def test_legacy_completed_test_and_fix_maps_to_internal_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            progress = Path(temp) / ".local/pipeline-state/HC-42/progress.json"
            progress.parent.mkdir(parents=True)
            progress.write_text(
                json.dumps({"completed": ["implement", "test-and-fix"]}),
                encoding="utf-8",
            )
            state = load_state(Path(temp), "HC-42")
            self.assertTrue(state["implementation_verification_complete"])
            self.assertEqual(state["completed"], ["implement"])

    def test_new_plan_version_archives_and_resets_progress(self) -> None:
        state = {
            "plan_fingerprint": "v1",
            "plan_dir": "/tmp/plan",
            "completed": ["implement", "review"],
            "evidence": {"implement": "ok"},
            "attempts": {"implement": 1},
            "stage_sessions": {"implement": [{"status": "complete"}]},
        }
        result = bind_plan(state, "v2", "/tmp/plan/v2")
        self.assertEqual(result, "version_changed")
        self.assertEqual(state["completed"], [])
        self.assertEqual(state["plan_history"][-1]["completed"], ["implement", "review"])

    def test_bound_plan_can_be_edited_in_place(self) -> None:
        state = {"plan_fingerprint": "before", "plan_dir": "/tmp/plan", "completed": ["implement"]}
        result = bind_plan(state, "after", "/tmp/plan")
        self.assertEqual(result, "version_changed")
        self.assertEqual(state["completed"], [])
        self.assertEqual(state["plan_history"][-1]["revision_kind"], "in-place")

    def test_same_provider_fallbacks_keep_separate_attempt_logs(self) -> None:
        first = runner.attempt_stem(
            "review", {"provider": "codex", "model": "gpt-5.6-terra"}, 1, 1
        )
        fallback = runner.attempt_stem(
            "review", {"provider": "codex", "model": "gpt-5.6-sol"}, 2, 1
        )
        self.assertNotEqual(first, fallback)

    def test_verification_failure_overrides_provider_ok_session(self) -> None:
        state = {
            "completed": [],
            "stage_sessions": {
                "review": [
                    {"status": "provider_ok", "provider_outcome": "ok"}
                ]
            },
        }
        mark_failed(state, "review", "review artifact missing")
        self.assertEqual(state["stage_sessions"]["review"][-1]["status"], "failed")
        self.assertEqual(state["stage_sessions"]["review"][-1]["provider_outcome"], "ok")

    def test_retry_after_survives_concise_429_classification(self) -> None:
        reason = runner.include_retry_after("429", "HTTP 429; Retry-After: 75 seconds")
        self.assertEqual(reason, "429; retry-after=75")

    def test_watcher_prints_only_a_fresh_final_recap(self) -> None:
        old_runs, old_live = runner.RUNS_DIR, runner.LIVE_DIR
        try:
            with tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                run_dir = base / "run"
                run_dir.mkdir()
                runner.RUNS_DIR = base
                runner.LIVE_DIR = base
                task = "HC-42"
                recap = run_dir / "recap.md"
                recap.write_text("# fresh recap\n", encoding="utf-8")
                (run_dir / "events.jsonl").write_text(
                    json.dumps({"when": "now", "event": "run_completed", "task": task}) + "\n",
                    encoding="utf-8",
                )
                runner.atomic_json(
                    runner.live_status_path(task),
                    {"pid": 99999999, "run_dir": str(run_dir), "updated_unix": 1},
                )
                runner.atomic_json(
                    runner.live_last_path(task),
                    {"status": "SUCCESS", "exit_code": 0, "recap": str(recap)},
                )
                fresh = io.StringIO()
                with redirect_stdout(fresh):
                    result = runner.watch(task, target_pid=99999999)
                self.assertEqual(result, 0)
                self.assertIn("# fresh recap", fresh.getvalue())

                stale_ns = runner.live_last_path(task).stat().st_mtime_ns
                stale = io.StringIO()
                with redirect_stdout(stale):
                    result = runner.watch(
                        task, target_pid=99999999, last_after_ns=stale_ns
                    )
                self.assertEqual(result, 2)
                self.assertNotIn("# fresh recap", stale.getvalue())
        finally:
            runner.RUNS_DIR, runner.LIVE_DIR = old_runs, old_live

    def test_manual_watch_does_not_replay_a_stale_run(self) -> None:
        old_runs, old_live = runner.RUNS_DIR, runner.LIVE_DIR
        try:
            with tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                runner.RUNS_DIR = base
                runner.LIVE_DIR = base
                task = "HC-42"
                runner.atomic_json(
                    runner.live_status_path(task),
                    {
                        "pid": 99999999,
                        "run_dir": str(base / "old-run"),
                        "updated_unix": 1,
                    },
                )
                output = io.StringIO()
                with redirect_stdout(output):
                    result = runner.watch(task)
                self.assertEqual(result, 0)
                self.assertIn("No active run found.", output.getvalue())
                self.assertNotIn("# fresh recap", output.getvalue())
        finally:
            runner.RUNS_DIR, runner.LIVE_DIR = old_runs, old_live

    def test_versioned_plan_contract_prefers_versioned_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            branch = Path(temp) / "hc-42"
            version = branch / "v2"
            version.mkdir(parents=True)
            (branch / "prompt.md").write_text("old", encoding="utf-8")
            (version / "prompt.md").write_text("new", encoding="utf-8")
            self.assertEqual(runner.plan_contract_path(version, "prompt.md"), version / "prompt.md")

    def test_plan_contract_mutation_is_accepted_for_next_rebind(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plan = Path(temp) / "hc-42"
            plan.mkdir()
            for name in (
                "prompt.md",
                "product.md",
                "implementation.md",
                "deferred-scope.md",
                "pipeline.json",
            ):
                (plan / name).write_text(name, encoding="utf-8")
            before = runner.plan_contract_snapshot(plan)
            (plan / "product.md").write_text("changed", encoding="utf-8")
            runner.ensure_plan_contract_unchanged(plan, before)

    def test_recovery_packet_is_handed_to_fresh_retry_but_not_review(self) -> None:
        packet = Path("/tmp/recovery.json")
        implement = runner.stage_context(
            "implement", "HC-42", "markoarsov/hc-42", Path("/tmp/plan"), [packet]
        )
        review = runner.stage_context(
            "review", "HC-42", "markoarsov/hc-42", Path("/tmp/plan"), [packet]
        )
        self.assertIn(str(packet), implement)
        self.assertNotIn(str(packet), review)

    def test_draft_verification_targets_only_repositories_with_base_diffs(self) -> None:
        repos = {"apaleo": Path("/tmp/apaleo"), "identity": Path("/tmp/identity")}

        def fake_git(repo: Path, *args: str, **_kwargs) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(
                ["git", *args], 1 if repo == repos["apaleo"] else 0, "", ""
            )

        with patch.object(runner, "worktrees", return_value=repos), patch.object(
            runner, "git", side_effect=fake_git
        ) as git, patch.object(runner, "task_base_branch", return_value="master"):
            self.assertEqual(
                runner.repositories_with_base_diff("markoarsov/hc-42"),
                {"apaleo": repos["apaleo"]},
            )
        self.assertIn("origin/master...HEAD", git.call_args_list[0].args)

    def test_draft_verification_of_a_stacked_plan_compares_with_its_base_branch(self) -> None:
        repos = {"apaleo": Path("/tmp/apaleo")}
        completed = subprocess.CompletedProcess(["git"], 1, "", "")
        with patch.object(runner, "worktrees", return_value=repos), patch.object(
            runner, "git", return_value=completed
        ) as git, patch.object(runner, "task_base_branch", return_value="markoarsov/sl-125"):
            self.assertEqual(runner.repositories_with_base_diff("markoarsov/sl-126"), repos)
        self.assertIn("origin/markoarsov/sl-125...HEAD", git.call_args.args)

    def test_preflight_sync_of_a_stacked_plan_merges_its_base_branch_not_master(self) -> None:
        repos = {"apaleo": Path("/tmp/apaleo")}
        calls: list[tuple[str, ...]] = []

        def fake_git(_repo: Path, *args: str, **_kwargs) -> subprocess.CompletedProcess:
            calls.append(args)
            stdout = "2" if args[0] == "rev-list" else ""
            return subprocess.CompletedProcess(["git", *args], 0, stdout, "")

        reporter = unittest.mock.Mock()
        with patch.object(runner, "worktrees", return_value=repos), patch.object(
            runner, "dirty_paths", return_value=[]
        ), patch.object(runner, "git", side_effect=fake_git), patch.object(
            runner, "task_base_branch", return_value="markoarsov/sl-125"
        ):
            runner.sync_master("markoarsov/sl-126", reporter)
        self.assertIn(("fetch", "--prune", "origin", "markoarsov/sl-125"), calls)
        self.assertIn(("merge", "--no-edit", "origin/markoarsov/sl-125"), calls)
        self.assertFalse(any("origin/master" in arg for call in calls for arg in call))


if __name__ == "__main__":
    unittest.main()
