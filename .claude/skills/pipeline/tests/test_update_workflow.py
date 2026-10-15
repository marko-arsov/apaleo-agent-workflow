from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PIPELINE = Path(__file__).resolve().parents[1]
SCRIPT = PIPELINE.parent / "update-workflow" / "update-workflow.sh"


def run(root: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env or {})
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=root,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )


class UpdateWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.origin = self.root / "apaleo-agent-workflow.git"
        self.workspace = self.root / "workspace"
        (self.workspace / "apaleo").mkdir(parents=True)
        (self.workspace / "development").mkdir()
        (self.workspace / "AGENTS.md").write_text("# test\n", encoding="utf-8")
        install = self.workspace / "install.sh"
        install.write_text("#!/bin/sh\nprintf '%s\\n' \"$1\" > \"$1/installed.txt\"\n", encoding="utf-8")
        install.chmod(0o755)
        subprocess.run(["git", "init", "--bare", "-b", "master", str(self.origin)], check=True, capture_output=True)
        subprocess.run(["git", "init", "-b", "master", str(self.workspace)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.workspace), "remote", "add", "origin", str(self.origin)], check=True)
        self.git_env = {
            "GIT_AUTHOR_NAME": "Update Test",
            "GIT_AUTHOR_EMAIL": "update-test@example.com",
            "GIT_COMMITTER_NAME": "Update Test",
            "GIT_COMMITTER_EMAIL": "update-test@example.com",
        }
        subprocess.run(["git", "-C", str(self.workspace), "add", "AGENTS.md", "install.sh"], check=True)
        subprocess.run(
            ["git", "-C", str(self.workspace), "commit", "-m", "Initial workflow checkout"],
            check=True,
            capture_output=True,
            env={**os.environ, **self.git_env},
        )
        subprocess.run(
            ["git", "-C", str(self.workspace), "push", "-u", "origin", "master"],
            check=True,
            capture_output=True,
            env={**os.environ, **self.git_env},
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def commit_here(self, relative: str, message: str) -> None:
        path = self.workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(message + "\n", encoding="utf-8")
        self.commit_repo(self.workspace, relative, message)

    def commit_repo(self, repo: Path, relative: str, message: str) -> None:
        subprocess.run(["git", "-C", str(repo), "add", relative], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", message],
            check=True,
            capture_output=True,
            env={**os.environ, **self.git_env},
        )

    def push_remote_change(self) -> str:
        other = self.root / "other"
        subprocess.run(["git", "clone", str(self.origin), str(other)], check=True, capture_output=True)
        (other / "README.md").write_text("remote\n", encoding="utf-8")
        self.commit_repo(other, "README.md", "Remote change")
        subprocess.run(
            ["git", "-C", str(other), "push"],
            check=True,
            capture_output=True,
            env={**os.environ, **self.git_env},
        )
        return subprocess.run(
            ["git", "-C", str(other), "rev-parse", "HEAD"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()

    def head(self) -> str:
        return subprocess.run(
            ["git", "-C", str(self.workspace), "rev-parse", "HEAD"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()

    def test_fast_forwards_master_and_registers_commands(self) -> None:
        remote_head = self.push_remote_change()
        before = self.head()
        result = run(self.workspace, env=self.git_env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Result: Updated", result.stdout)
        self.assertNotEqual(before, self.head())
        self.assertEqual(self.head(), remote_head)
        recorded = Path((self.workspace / "installed.txt").read_text(encoding="utf-8").strip())
        self.assertEqual(recorded.resolve(), self.workspace.resolve())

    def test_already_current_still_registers_commands(self) -> None:
        result = run(self.workspace, env=self.git_env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Result: Already up to date", result.stdout)
        self.assertTrue((self.workspace / "installed.txt").is_file())

    def test_refuses_uncommitted_changes(self) -> None:
        before = self.head()
        (self.workspace / "README.md").write_text("local\n", encoding="utf-8")
        result = run(self.workspace, env=self.git_env)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("ASK: checkout has uncommitted changes", result.stderr)
        self.assertEqual(before, self.head())
        self.assertFalse((self.workspace / "installed.txt").exists())

    def test_refuses_a_feature_branch(self) -> None:
        subprocess.run(["git", "-C", str(self.workspace), "checkout", "-b", "workflow/example"], check=True, capture_output=True)
        result = run(self.workspace, env=self.git_env)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("ASK: checkout is on workflow/example", result.stderr)
        self.assertFalse((self.workspace / "installed.txt").exists())

    def test_refuses_a_diverged_master(self) -> None:
        self.push_remote_change()
        self.commit_here("LOCAL.md", "Local commit")
        before = self.head()
        result = run(self.workspace, env=self.git_env)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("ASK: master cannot fast-forward", result.stderr)
        self.assertEqual(before, self.head())
        self.assertFalse((self.workspace / "installed.txt").exists())
