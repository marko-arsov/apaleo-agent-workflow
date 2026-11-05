from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))

from pipeline_manifest import make_manifest  # noqa: E402
from verification import (  # noqa: E402
    _added_diff,
    _budget_result,
    diff_stats,
    leftover_core_e2e_message,
    VerificationError,
    assert_no_new_decisions,
    assert_review_gates,
    parse_test_output,
    red_proof_cites_path,
    validate_red_proof,
)


class VerificationTests(unittest.TestCase):
    def test_diff_budget_overshoot_is_advisory(self) -> None:
        result = _budget_result(
            {"diff_budget": {"expected_files": 1, "max_files": 2, "expected_lines": 10, "max_lines": 4000}},
            {"files": 3, "lines": 4001},
        )
        self.assertEqual(result["status"], "advisory-overshoot")
        self.assertTrue(result["overshoot"])

    def test_stacked_plan_diff_excludes_the_base_branch_work(self) -> None:
        branch = "jdoe/sl-126-stacked"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "worktrees" / branch / "apaleo"
            repo.mkdir(parents=True)

            def git(*args: str) -> None:
                subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

            git("init", "-q", "-b", "master")
            git("config", "user.email", "test@example.com")
            git("config", "user.name", "Test")
            (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
            git("add", "-A")
            git("commit", "-qm", "seed")
            git("update-ref", "refs/remotes/origin/master", "HEAD")
            (repo / "base.txt").write_text("".join(f"{i}\n" for i in range(50)), encoding="utf-8")
            git("add", "-A")
            git("commit", "-qm", "base branch work")
            git("update-ref", "refs/remotes/origin/jdoe/sl-125-base", "HEAD")
            (repo / "feature.txt").write_text("one\ntwo\n", encoding="utf-8")

            plan = root / "ai-plans" / branch
            plan.mkdir(parents=True)
            for name in ("prompt.md", "product.md", "implementation.md", "deferred-scope.md"):
                (plan / name).write_text(name, encoding="utf-8")

            def write_manifest(stacked_on: str | None) -> None:
                manifest = make_manifest(
                    stages=["implement"],
                    tests_required=False,
                    e2e_required=False,
                    route_assignments=[],
                    fallback_assignments=[],
                    allowed_paths=["apaleo/**"],
                    test_paths=["apaleo/t"],
                    test_commands=[{"id": "t", "repo": "apaleo", "argv": ["true"], "parser": "generic", "success_pattern": "x"}],
                    acceptance_criteria=[{"id": "AC-1", "test": "t", "test_path": "apaleo/t", "command": "t", "evidence_pattern": "x", "red_required": False}],
                    stacked_on=stacked_on,
                )
                (plan / "pipeline.json").write_text(json.dumps(manifest), encoding="utf-8")

            write_manifest("jdoe/sl-125-base")
            stacked = diff_stats(root, branch)
            self.assertEqual(stacked["paths"], ["apaleo/feature.txt"])
            self.assertEqual(stacked["lines"], 2)

            write_manifest(None)
            unstacked = diff_stats(root, branch)
            self.assertEqual(unstacked["paths"], ["apaleo/base.txt", "apaleo/feature.txt"])

    def test_master_deletions_are_not_scanned_as_additions(self) -> None:
        branch = "jdoe/sl-179-leftover"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "worktrees" / branch / "development"
            repo.mkdir(parents=True)

            def git(*args: str) -> None:
                subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

            git("init", "-q", "-b", "master")
            git("config", "user.email", "test@example.com")
            git("config", "user.name", "Test")
            spec = repo / "src/tests/core/calendar/authz/calendar-events-authz-spec.ts"
            untouched = repo / "src/tests/core/booking/old-spec.ts"
            spec.parent.mkdir(parents=True)
            untouched.parent.mkdir(parents=True)
            spec.write_text("const ready = true;\n", encoding="utf-8")
            untouched.write_text("password = \"untouched-e2e-password\"\n", encoding="utf-8")
            git("add", "-A")
            git("commit", "-qm", "fork")
            git("update-ref", "refs/remotes/origin/master", "HEAD")
            git("checkout", "-q", "-b", "feature")
            spec.write_text("const ready = true;\npassword = \"branch-e2e-password\"\n", encoding="utf-8")
            git("add", "-A")
            git("commit", "-qm", "e2e")
            git("checkout", "-q", "master")
            git("rm", "-q", "src/tests/core/calendar/authz/calendar-events-authz-spec.ts", "src/tests/core/booking/old-spec.ts")
            git("commit", "-qm", "master drops core e2e")
            git("update-ref", "refs/remotes/origin/master", "HEAD")
            git("checkout", "-q", "feature")

            plan = root / "ai-plans" / branch
            plan.mkdir(parents=True)
            for name in ("prompt.md", "product.md", "implementation.md", "deferred-scope.md"):
                (plan / name).write_text(name, encoding="utf-8")
            manifest = make_manifest(
                stages=["implement"],
                tests_required=False,
                e2e_required=False,
                route_assignments=[],
                fallback_assignments=[],
                allowed_paths=["apaleo/**"],
                test_paths=["apaleo/t"],
                test_commands=[{"id": "t", "repo": "apaleo", "argv": ["true"], "parser": "generic", "success_pattern": "x"}],
                acceptance_criteria=[{"id": "AC-1", "test": "t", "test_path": "apaleo/t", "command": "t", "evidence_pattern": "x", "red_required": False}],
                stacked_on=None,
            )
            (plan / "pipeline.json").write_text(json.dumps(manifest), encoding="utf-8")

            stats = diff_stats(root, branch)
            self.assertEqual(
                stats["paths"],
                ["development/src/tests/core/calendar/authz/calendar-events-authz-spec.ts"],
            )
            added = _added_diff(root, branch)
            self.assertIn("branch-e2e-password", added)
            self.assertNotIn("untouched-e2e-password", added)
            message = leftover_core_e2e_message(root, branch)
            self.assertIsNotNone(message)
            self.assertIn("calendar-events-authz-spec.ts", message or "")
            self.assertIn("worktree remove --force", message or "")

            payment = repo / "src/tests/payment/pay-spec.ts"
            payment.parent.mkdir(parents=True)
            payment.write_text("const pay = true;\n", encoding="utf-8")
            self.assertIsNone(leftover_core_e2e_message(root, branch))

    def test_dotnet_success_requires_observed_summary(self) -> None:
        command = {"parser": "dotnet"}
        self.assertTrue(parse_test_output(command, "Passed!  - Failed: 0, Passed: 4", 0)[0])
        self.assertFalse(parse_test_output(command, "agent says tests passed", 0)[0])
        self.assertFalse(parse_test_output(command, "Failed: 1, Passed: 3", 0)[0])
        self.assertFalse(parse_test_output(command, "Passed! - Failed: 0, Passed: 0, Total: 0", 0)[0])

    def test_compile_failure_is_not_red_proof(self) -> None:
        manifest = {
            "acceptance_criteria": [
                {
                    "id": "AC-1",
                    "test": "RejectsMissingScope",
                    "command": "auth-tests",
                    "red_required": True,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp:
            plan = Path(temp)
            (plan / "red-proof.md").write_text(
                "Failure level: assertion\nRejectsMissingScope\nauth-tests\nerror CS1002\nExpected: 403 Actual: 200\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VerificationError, "compile/type failure"):
                validate_red_proof(plan, manifest)

    def test_red_proof_requires_each_mapped_test_and_command(self) -> None:
        manifest = {
            "acceptance_criteria": [
                {
                    "id": "AC-1",
                    "test": "RejectsMissingScope",
                    "command": "auth-tests",
                    "red_required": True,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp:
            plan = Path(temp)
            (plan / "red-proof.md").write_text(
                "Failure level: assertion\nExpected: 403\nActual: 200\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VerificationError, "missing mapped"):
                validate_red_proof(plan, manifest)

    def test_red_proof_cites_workspace_or_repo_relative_paths(self) -> None:
        workspace = (
            "Failure level: assertion\n"
            "`apaleo/test/Apaleo.Calendar.Tests/Services/ForkCalendarEventServiceTest.cs`\n"
        )
        grouped = (
            "Failure level: assertion\n"
            "apaleo:\n"
            "- `test/Apaleo.Api.Tests/Modules/Calendar/Models/ForkCalendarEventModelTest.cs`\n"
        )
        self.assertTrue(
            red_proof_cites_path(
                workspace,
                "apaleo/test/Apaleo.Calendar.Tests/Services/ForkCalendarEventServiceTest.cs",
            )
        )
        self.assertTrue(
            red_proof_cites_path(
                grouped,
                "apaleo/test/Apaleo.Api.Tests/Modules/Calendar/Models/ForkCalendarEventModelTest.cs",
            )
        )
        self.assertFalse(
            red_proof_cites_path(
                "Failure level: assertion\nForkCalendarEventModelTest.cs\n",
                "apaleo/test/Apaleo.Api.Tests/Modules/Calendar/Models/ForkCalendarEventModelTest.cs",
            )
        )

    def test_red_proof_accepts_repo_relative_changed_paths(self) -> None:
        manifest = {
            "acceptance_criteria": [
                {
                    "id": "AC-1",
                    "test": "RejectsMissingScope",
                    "command": "auth-tests",
                    "red_required": True,
                }
            ]
        }
        path = "apaleo/test/Apaleo.Api.Tests/Modules/Calendar/Models/ForkCalendarEventModelTest.cs"
        with tempfile.TemporaryDirectory() as temp:
            plan = Path(temp)
            (plan / "red-proof.md").write_text(
                "Failure level: assertion\n"
                "Expected: 403\nActual: 200\n"
                "RejectsMissingScope\nauth-tests\n"
                "apaleo:\n"
                f"- `test/Apaleo.Api.Tests/Modules/Calendar/Models/ForkCalendarEventModelTest.cs`\n",
                encoding="utf-8",
            )
            validate_red_proof(plan, manifest, changed_test_paths=[path])
            (plan / "red-proof.md").write_text(
                "Failure level: assertion\n"
                "Expected: 403\nActual: 200\n"
                "RejectsMissingScope\nauth-tests\n"
                "ForkCalendarEventModelTest.cs\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VerificationError, "missing changed test file"):
                validate_red_proof(plan, manifest, changed_test_paths=[path])

    def test_red_proof_accepts_none_when_no_criterion_requires_red(self) -> None:
        manifest = {
            "acceptance_criteria": [
                {
                    "id": "AC-1",
                    "test": "PropertyAdmin keeps write allows",
                    "command": "e2e-authz",
                    "red_required": False,
                }
            ]
        }
        path = "development/src/tests/core/calendar/authz/calendar-events-authz-spec.ts"
        with tempfile.TemporaryDirectory() as temp:
            plan = Path(temp)
            (plan / "red-proof.md").write_text(
                "Failure level: none — verified by design\n"
                f"{path}\n",
                encoding="utf-8",
            )
            validate_red_proof(plan, manifest, changed_test_paths=[path])
            (plan / "red-proof.md").write_text(
                "Failure level: assertion\nExpected: 403\nActual: 200\n" + path + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VerificationError, "Failure level: none"):
                validate_red_proof(plan, manifest, changed_test_paths=[path])

    def test_stage_report_cannot_set_a_new_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "review-1.md"
            report.write_text("Architecture decision: add a cache\n", encoding="utf-8")
            with self.assertRaisesRegex(VerificationError, "plan defect"):
                assert_no_new_decisions([report])

    def test_stage_report_requires_explicit_none_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "review-1.md"
            report.write_text("Findings: none\n", encoding="utf-8")
            with self.assertRaisesRegex(VerificationError, "lacks the required"):
                assert_no_new_decisions([report], require_declaration=True)
            report.write_text(
                "New product/architectural decisions: none\n",
                encoding="utf-8",
            )
            assert_no_new_decisions([report], require_declaration=True)

    def test_review_report_requires_evidenced_convention_and_reuse_audits(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "review-1.md"
            report.write_text(
                "Convention compliance: passed\n"
                "Reuse/DRY audit: passed — searched only the diff\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VerificationError, "convention or repository-wide"):
                assert_review_gates([report])
            report.write_text(
                "Convention compliance: passed — checked everything\n"
                "Reuse/DRY audit: passed — no duplicates found\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VerificationError, "convention or repository-wide"):
                assert_review_gates([report])
            report.write_text(
                "Convention compliance: passed — AGENTS.md, scoped rules, and detector passed\n"
                "Reuse/DRY audit: fixed — searched the repository; reused ExistingMapper.cs\n",
                encoding="utf-8",
            )
            assert_review_gates([report])


if __name__ == "__main__":
    unittest.main()
