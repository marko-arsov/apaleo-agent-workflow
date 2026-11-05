from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))

from test_judge import (  # noqa: E402
    affected_commands,
    checkpoint_message,
    classify_diff,
    commit_worktree,
    file_diff,
    render_report,
    restore_test_file,
)


def _diff(before: str, after: str) -> str:
    return "\n".join(
        [
            "diff --git a/spec.ts b/spec.ts",
            "--- a/spec.ts",
            "+++ b/spec.ts",
            "@@ -1,3 +1,3 @@",
            *[f"-{line}" for line in before.splitlines()],
            *[f"+{line}" for line in after.splitlines()],
        ]
    )


class ClassifyTests(unittest.TestCase):
    def test_assertion_change_is_a_cheat(self) -> None:
        kind, reason = classify_diff(
            _diff('expect(response.status).toBe(403);', 'expect(response.status).toBe(200);')
        )
        self.assertEqual((kind, reason), ("cheat", "assertion changed"))

    def test_removed_assertion_is_a_cheat(self) -> None:
        kind, reason = classify_diff(_diff("expect(result).toEqual(1);", "const result = 1;"))
        self.assertEqual((kind, reason), ("cheat", "assertion removed"))

    def test_skip_is_a_cheat(self) -> None:
        kind, reason = classify_diff(_diff('it("books", () => {', 'it.skip("books", () => {'))
        self.assertEqual((kind, reason), ("cheat", "skip or only"))

    def test_deleted_test_is_a_cheat(self) -> None:
        kind, reason = classify_diff(_diff('it("books", () => {});', "const unused = 1;"))
        self.assertEqual((kind, reason), ("cheat", "test case removed"))

    def test_import_only_is_safe(self) -> None:
        kind, reason = classify_diff(
            _diff(
                'import { create } from "./old";',
                'import { create } from "./booking";',
            )
        )
        self.assertEqual((kind, reason), ("safe", "imports or comments only"))

    def test_helper_call_is_kept(self) -> None:
        kind, reason = classify_diff(
            _diff("await ensureProperty(account);", "await ensureProperty(account, property);")
        )
        self.assertEqual((kind, reason), ("kept", "setup or helper edit"))

    def test_added_assertion_is_kept(self) -> None:
        kind, reason = classify_diff(_diff("const result = 1;", "expect(result).toBe(1);"))
        self.assertEqual((kind, reason), ("kept", "setup or helper edit"))


class ReportTests(unittest.TestCase):
    def test_failing_restore_is_not_described_as_passed(self) -> None:
        report = render_report(
            [{"path": "apaleo/e2e/tests/book-spec.ts", "reason": "assertion changed", "excerpt": "-toBe(403)\n+toBe(200)"}],
            [],
            [],
            [{"argv": ["yarn", "test", "--", "tests/book-spec.ts"], "passed": False}],
        )
        self.assertIn("## Restored tests failing locally", report)
        self.assertIn("not a passed verification", report)
        self.assertIn("apaleo/e2e/tests/book-spec.ts", report)
        self.assertIn("yarn test -- tests/book-spec.ts", report)
        self.assertIn("failed", report)

    def test_commands_follow_the_restored_acceptance_path(self) -> None:
        manifest = {
            "acceptance_criteria": [
                {"test_path": "apaleo/e2e/tests/book-spec.ts", "command": "book"},
                {"test_path": "apaleo/e2e/tests/other-spec.ts", "command": "other"},
            ],
            "test_commands": [
                {"id": "book", "argv": ["yarn", "test"]},
                {"id": "other", "argv": ["yarn", "test", "other"]},
            ],
        }
        commands = affected_commands(manifest, ["apaleo/e2e/tests/book-spec.ts"])
        self.assertEqual([item["id"] for item in commands], ["book"])

    def test_checkpoint_message_uses_the_issue(self) -> None:
        self.assertEqual(
            checkpoint_message("markoarsov/sl-179-calendar", "implement-tests"),
            "SL-179 checkpoint implement-tests",
        )


class GitRestoreTests(unittest.TestCase):
    def test_commit_and_restore_one_file(self) -> None:
        env = os.environ.copy()
        env.update(
            {
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@example.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@example.com",
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, env=env)
            spec = repo / "book-spec.ts"
            spec.write_text('expect(status).toBe(403);\n', encoding="utf-8")
            baseline = commit_worktree(repo, "SL-1 checkpoint implement-tests", env=env)
            self.assertIsNotNone(baseline)
            spec.write_text('expect(status).toBe(200);\n', encoding="utf-8")
            commit_worktree(repo, "SL-1 checkpoint implement", env=env)
            diff = file_diff(repo, baseline or "", "book-spec.ts")
            self.assertEqual(classify_diff(diff)[0], "cheat")
            self.assertTrue(restore_test_file(repo, baseline or "", "book-spec.ts"))
            self.assertEqual(spec.read_text(encoding="utf-8"), "expect(status).toBe(403);\n")


if __name__ == "__main__":
    unittest.main()
