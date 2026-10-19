from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PIPELINE = Path(__file__).resolve().parents[1]
SCRIPT = PIPELINE.parent / "publish-workflow" / "publish-workflow.sh"


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


class PublishWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.origin = self.root / "apaleo-agent-workflow.git"
        self.workspace = self.root / "workspace"
        (self.workspace / "apaleo").mkdir(parents=True)
        (self.workspace / "development").mkdir()
        (self.workspace / "AGENTS.md").write_text("# test\n", encoding="utf-8")
        subprocess.run(["git", "init", "--bare", "-b", "master", str(self.origin)], check=True, capture_output=True)
        subprocess.run(["git", "init", "-b", "master", str(self.workspace)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.workspace), "remote", "add", "origin", str(self.origin)], check=True)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        self.gh_args = self.root / "gh.args"
        gh = bin_dir / "gh"
        gh.write_text(
            "#!/bin/sh\n: > \"$GH_ARGS_FILE\"\n"
            "while [ $# -gt 0 ]; do printf '%s\\n' \"$1\" >> \"$GH_ARGS_FILE\"; shift; done\n"
            "printf '%s\\n' 'https://github.com/example-owner/apaleo-agent-workflow/pull/1'\n",
            encoding="utf-8",
        )
        gh.chmod(0o755)
        self.git_env = {
            "GIT_AUTHOR_NAME": "Publish Test",
            "GIT_AUTHOR_EMAIL": "publish-test@example.com",
            "GIT_COMMITTER_NAME": "Publish Test",
            "GIT_COMMITTER_EMAIL": "publish-test@example.com",
            "GH_ARGS_FILE": str(self.gh_args),
            "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        }
        self.commit("AGENTS.md", "Initial workflow checkout")
        subprocess.run(
            ["git", "-C", str(self.workspace), "push", "-u", "origin", "master"],
            check=True,
            capture_output=True,
            env={**os.environ, **self.git_env},
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def commit(self, relative: str, message: str) -> None:
        path = self.workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(message + "\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.workspace), "add", relative], check=True)
        subprocess.run(
            ["git", "-C", str(self.workspace), "commit", "-m", message],
            check=True,
            capture_output=True,
            env={**os.environ, **self.git_env},
        )

    def test_publishes_workflow_files_and_leaves_product_files_untracked(self) -> None:
        (self.workspace / ".gitignore").write_text("/*\n!/.gitignore\n!/AGENTS.md\n!/README.md\n", encoding="utf-8")
        (self.workspace / "README.md").write_text("workflow\n", encoding="utf-8")
        (self.workspace / "apaleo" / "keep.txt").write_text("product\n", encoding="utf-8")
        result = run(self.workspace, "Add a workflow note", env=self.git_env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("URL: https://github.com/example-owner/apaleo-agent-workflow/pull/1", result.stdout)
        branch = subprocess.run(
            ["git", "-C", str(self.workspace), "branch", "--show-current"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        self.assertEqual(branch, "workflow/add-a-workflow-note")
        names = subprocess.run(
            ["git", "-C", str(self.workspace), "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("README.md", names)
        self.assertNotIn("apaleo/keep.txt", names)

    def test_refuses_a_product_path_without_creating_a_branch(self) -> None:
        (self.workspace / "README.md").write_text("workflow\n", encoding="utf-8")
        (self.workspace / "apaleo" / "keep.txt").write_text("product\n", encoding="utf-8")
        result = run(self.workspace, "Add a workflow note", env=self.git_env)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("ASK: refusing to publish apaleo/keep.txt", result.stderr)
        branch = subprocess.run(
            ["git", "-C", str(self.workspace), "branch", "--show-current"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        self.assertEqual(branch, "master")

    def test_publishes_local_commits_and_edits_from_another_branch(self) -> None:
        self.commit("AGENTS.md", "Local commit")
        subprocess.run(["git", "-C", str(self.workspace), "checkout", "-b", "feature"], check=True)
        (self.workspace / "README.md").write_text("workflow\n", encoding="utf-8")
        master = subprocess.run(
            ["git", "-C", str(self.workspace), "rev-parse", "master"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        result = run(self.workspace, "Add a workflow note", env=self.git_env)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        names = subprocess.run(
            ["git", "-C", str(self.workspace), "diff", "--name-only", "origin/master...HEAD"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertIn("README.md", names)
        self.assertIn("AGENTS.md", names)
        self.assertEqual(
            subprocess.run(
                ["git", "-C", str(self.workspace), "rev-parse", "master"],
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip(),
            master,
        )
        self.assertEqual(
            subprocess.run(
                ["git", "-C", str(self.workspace), "rev-parse", "feature"],
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip(),
            master,
        )

    def test_asks_when_the_branch_does_not_apply_onto_origin_master(self) -> None:
        self.commit("README.md", "On master")
        subprocess.run(
            ["git", "-C", str(self.workspace), "push", "origin", "master"],
            check=True,
            capture_output=True,
            env={**os.environ, **self.git_env},
        )
        subprocess.run(["git", "-C", str(self.workspace), "checkout", "-b", "feature"], check=True)
        self.commit("README.md", "Feature edit")
        subprocess.run(["git", "-C", str(self.workspace), "checkout", "master"], check=True)
        self.commit("README.md", "Updated master")
        subprocess.run(
            ["git", "-C", str(self.workspace), "push", "origin", "master"],
            check=True,
            capture_output=True,
            env={**os.environ, **self.git_env},
        )
        subprocess.run(["git", "-C", str(self.workspace), "checkout", "feature"], check=True)
        result = run(self.workspace, "Add a workflow note", env=self.git_env)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("ASK: could not replay the current branch onto origin/master", result.stderr)
        branch = subprocess.run(
            ["git", "-C", str(self.workspace), "branch", "--show-current"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        self.assertEqual(branch, "feature")
        branches = subprocess.run(
            ["git", "-C", str(self.workspace), "branch"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertNotIn("workflow/add-a-workflow-note", branches)
        self.assertEqual((self.workspace / "README.md").read_text(encoding="utf-8"), "Feature edit\n")

    def test_derives_a_summary_when_omitted(self) -> None:
        skill = self.workspace / ".claude" / "skills" / "publish-workflow"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("skill\n", encoding="utf-8")
        (self.workspace / ".cursor" / "agents").mkdir(parents=True)
        (self.workspace / ".cursor" / "agents" / "publish-workflow-cursor.md").write_text("agent\n", encoding="utf-8")
        result = run(self.workspace, env=self.git_env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Summary: Update publish-workflow", result.stdout)
        message = subprocess.run(
            ["git", "-C", str(self.workspace), "log", "-1", "--format=%s"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        self.assertEqual(message, "Update publish-workflow")
        body = self.gh_args.read_text(encoding="utf-8")
        self.assertIn("Add `/publish-workflow`.", body)
        self.assertNotIn("## Changes", body)
        branch = subprocess.run(
            ["git", "-C", str(self.workspace), "branch", "--show-current"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        self.assertEqual(branch, "workflow/update-publish-workflow")

    def test_dry_run_does_not_create_a_branch(self) -> None:
        (self.workspace / "README.md").write_text("workflow\n", encoding="utf-8")
        result = run(self.workspace, "--dry-run", "Add a workflow note", env=self.git_env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Branch: workflow/add-a-workflow-note", result.stdout)
        branches = subprocess.run(
            ["git", "-C", str(self.workspace), "branch"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertNotIn("workflow/add-a-workflow-note", branches)
