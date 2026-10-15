from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PIPELINE = Path(__file__).resolve().parents[1]
SKILLS = PIPELINE.parent
ROOT_SH = PIPELINE / "root.sh"
START = SKILLS / "worktree-start" / "worktree-start.sh"
REMOVE = SKILLS / "worktree-remove" / "worktree-remove.sh"

import sys

sys.path.insert(0, str(PIPELINE))

from common import attached_repo_names  # noqa: E402
from pipeline_manifest import make_manifest, markdown, validate  # noqa: E402
from verification import red_proof_cites_path  # noqa: E402


def git(repo: Path, *args: str, env: dict[str, str]) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env)


def run(argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, text=True, capture_output=True, env=env)


def init_repo(path: Path, env: dict[str, str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-b", "master", env=env)
    git(path, "config", "user.email", "t@example.com", env=env)
    git(path, "config", "user.name", "Test", env=env)
    git(path, "config", "commit.gpgsign", "false", env=env)
    (path / "README").write_text("x\n", encoding="utf-8")
    git(path, "add", "README", env=env)
    git(path, "commit", "-m", "init", env=env)


def parked(root: Path, name: str, seeds: Path, env: dict[str, str]) -> Path:
    seed = seeds / f"{name}.git"
    subprocess.run(["git", "init", "--bare", "-b", "master", str(seed)], check=True, capture_output=True, text=True, env=env)
    repo = root / name
    init_repo(repo, env)
    git(repo, "remote", "add", "origin", str(seed), env=env)
    git(repo, "push", "-u", "origin", "master", env=env)
    return repo


class ExtraRepoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.env = os.environ.copy()
        self.env["GIT_CONFIG_GLOBAL"] = str(self.root / "gitconfig")
        self.env["GIT_CONFIG_SYSTEM"] = "/dev/null"
        (self.root / "gitconfig").write_text("[safe]\n\tdirectory = *\n", encoding="utf-8")
        (self.root / "AGENTS.md").write_text("# test\n", encoding="utf-8")
        seeds = self.root / "seeds"
        seeds.mkdir()
        parked(self.root, "apaleo", seeds, self.env)
        parked(self.root, "development", seeds, self.env)
        self.seeds = seeds
        self.branch = "tester/sl-9-extra"

    def test_manifest_accepts_a_recorded_extra_repo_and_rejects_an_unlisted_one(self) -> None:
        manifest = make_manifest(
            stages=["implement"],
            tests_required=False,
            e2e_required=False,
            route_assignments=[],
            fallback_assignments=[],
            allowed_paths=["payments/src/**"],
            test_paths=["payments/test/**"],
            test_commands=[
                {
                    "id": "payments-unit",
                    "repo": "payments",
                    "argv": ["echo", "ok"],
                    "parser": "generic",
                    "success_pattern": "ok",
                }
            ],
            acceptance_criteria=[
                {
                    "id": "AC-1",
                    "test": "ExpectedBehaviour",
                    "test_path": "payments/test/ExpectedBehaviourTests.cs",
                    "command": "payments-unit",
                    "evidence_pattern": r"Passed:\s*1",
                    "red_required": True,
                }
            ],
            extra_repos=["payments"],
        )
        self.assertEqual(manifest["extra_repos"], ["payments"])
        self.assertIn("Extra repositories: `payments`", markdown(manifest))
        unlisted = dict(manifest)
        unlisted["test_commands"] = [dict(manifest["test_commands"][0], repo="other")]
        self.assertTrue(any("repo must be one of" in error for error in validate(unlisted)))
        collided = dict(manifest)
        collided["extra_repos"] = ["worktrees"]
        self.assertTrue(any("extra_repos" in error for error in validate(collided)))

    def test_red_proof_accepts_an_extra_repo_prefix(self) -> None:
        self.assertTrue(red_proof_cites_path("test/Foo.cs", "payments/test/Foo.cs", ("payments",)))
        self.assertFalse(red_proof_cites_path("test/Foo.cs", "payments/test/Foo.cs"))

    def test_existing_sibling_checkout_is_reused(self) -> None:
        payments = parked(self.root, "payments", self.seeds, self.env)
        git(payments, "remote", "set-url", "origin", "git@github.com:apaleo/payments.git", env=self.env)
        seed = self.seeds / "payments.git"
        git(payments, "config", f"url.{seed}.insteadOf", "git@github.com:apaleo/payments.git", env=self.env)

        result = run(
            [str(START), self.branch, "--from-master", "--with", "payments"],
            self.root,
            self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        checkout = self.root / "worktrees" / self.branch / "payments"
        self.assertTrue((checkout / ".git").exists())
        self.assertFalse((self.root / ".repos" / "payments.git").exists())
        self.assertEqual(
            subprocess.run(
                ["git", "-C", str(payments), "branch", "--show-current"],
                check=True, capture_output=True, text=True, env=self.env,
            ).stdout.strip(),
            "master",
        )
        self.assertEqual(
            (self.root / "worktrees" / self.branch / ".extra-repos").read_text(encoding="utf-8").split(),
            ["payments"],
        )
        stranger = self.root / "worktrees" / self.branch / "stranger"
        init_repo(stranger, self.env)
        self.assertEqual(
            attached_repo_names(self.root, self.branch),
            ["apaleo", "payments"],
        )

        removed = run([str(REMOVE), self.branch, "--yes"], self.root, self.env)
        self.assertEqual(removed.returncode, 0, removed.stderr + removed.stdout)
        self.assertFalse(checkout.exists())
        self.assertTrue(payments.is_dir())

    def test_missing_checkout_uses_a_bare_mirror(self) -> None:
        seed = self.seeds / "payments.git"
        subprocess.run(
            ["git", "init", "--bare", "-b", "master", str(seed)],
            check=True, capture_output=True, text=True, env=self.env,
        )
        bare_work = self.root / "seeds" / "payments-work"
        init_repo(bare_work, self.env)
        git(bare_work, "remote", "add", "origin", str(seed), env=self.env)
        git(bare_work, "push", "-u", "origin", "master", env=self.env)
        mirror = self.root / ".repos" / "payments.git"
        subprocess.run(
            ["git", "clone", "--bare", str(seed), str(mirror)],
            check=True, capture_output=True, text=True, env=self.env,
        )

        result = run(
            [str(START), self.branch, "--from-master", "--with", "payments"],
            self.root,
            self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        checkout = self.root / "worktrees" / self.branch / "payments"
        self.assertTrue((checkout / ".git").exists())
        self.assertTrue(mirror.is_dir())

        removed = run([str(REMOVE), self.branch, "--yes"], self.root, self.env)
        self.assertEqual(removed.returncode, 0, removed.stderr + removed.stdout)
        self.assertFalse(checkout.exists())
        self.assertTrue(mirror.is_dir())

    def test_unknown_name_and_invisible_repo_are_refused(self) -> None:
        refused = run([str(START), self.branch, "--with", "worktrees"], self.root, self.env)
        self.assertEqual(refused.returncode, 2, refused.stderr)
        self.assertIn("refusing repository name", refused.stderr)
        self.assertFalse((self.root / "worktrees" / self.branch).exists())

        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        gh.chmod(0o755)
        env = dict(self.env)
        env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
        missing = run([str(START), self.branch, "--from-master", "--with", "billing"], self.root, env)
        self.assertEqual(missing.returncode, 2, missing.stderr + missing.stdout)
        self.assertIn("apaleo/billing", missing.stderr)
        self.assertFalse((self.root / ".repos" / "billing.git").exists())

    def test_cwd_inside_an_extra_checkout_resolves_the_branch(self) -> None:
        checkout = self.root / "worktrees" / self.branch / "payments" / "src"
        checkout.mkdir(parents=True)
        (checkout.parent / ".git").mkdir()
        process = run(
            [
                "bash",
                "-c",
                'source "$1"; ROOT="$2"; cd "$3"; resolve_feature_branch',
                "bash",
                str(ROOT_SH),
                str(self.root),
                str(checkout),
            ],
            self.root,
            self.env,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stdout, self.branch)


if __name__ == "__main__":
    unittest.main()
