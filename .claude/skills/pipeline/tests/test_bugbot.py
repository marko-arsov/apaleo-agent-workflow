from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


PIPELINE = Path(__file__).resolve().parents[1]
BUGBOT_DIR = PIPELINE.parent / "address-pr-comments"
sys.path.insert(0, str(BUGBOT_DIR))

import bugbot  # noqa: E402


class BugbotTests(unittest.TestCase):
    def test_restore_preserves_pr_that_was_already_ready(self) -> None:
        calls: list[list[str]] = []
        old = bugbot.run_gh
        bugbot.run_gh = lambda args, cwd, timeout=90: calls.append(args) or subprocess.CompletedProcess(args, 0, "", "")
        try:
            result = bugbot.restore_from_state(
                {"prs": [{"path": "/tmp", "number": 1, "was_draft": False, "marked_ready": False}]}
            )
        finally:
            bugbot.run_gh = old
        self.assertEqual(result, 0)
        self.assertEqual(calls, [])

    def test_restore_reverts_only_temporarily_readied_pr(self) -> None:
        calls: list[list[str]] = []
        old = bugbot.run_gh
        bugbot.run_gh = lambda args, cwd, timeout=90: calls.append(args) or subprocess.CompletedProcess(args, 0, "", "")
        try:
            result = bugbot.restore_from_state(
                {"prs": [{"path": "/tmp", "number": 2, "was_draft": True, "marked_ready": True}]},
                quiet=True,
            )
        finally:
            bugbot.run_gh = old
        self.assertEqual(result, 0)
        self.assertEqual(calls, [["pr", "ready", "--undo", "2"]])


if __name__ == "__main__":
    unittest.main()
