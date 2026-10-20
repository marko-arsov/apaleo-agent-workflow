from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


PIPELINE = Path(__file__).resolve().parents[1]
ROOT_SH = PIPELINE / "root.sh"


def resolve(root: Path, query: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; ROOT="$2"; resolve_feature_branch "$3"',
            "bash",
            str(ROOT_SH),
            str(root),
            query,
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )


def worktree(root: Path, branch: str) -> None:
    development = root / "worktrees" / branch / "development"
    (development / ".git").mkdir(parents=True)
    (development / "apaleo").mkdir()


class RootShTests(unittest.TestCase):
    def test_issue_id_ignores_repo_named_source_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            branch = "jdoe/sl-100-example"
            worktree(root, branch)

            process = resolve(root, "sl-100")

            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stdout, branch)

    def test_issue_id_without_a_dash_matches_the_dashed_branch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            branch = "jdoe/sl-129-example"
            worktree(root, branch)
            worktree(root, "jdoe/sl-1290-other")

            process = resolve(root, "sl129")

            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stdout, branch)

    def test_legacy_c_id_still_resolves_to_hc(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            branch = "jdoe/hc-3331-example"
            worktree(root, branch)

            process = resolve(root, "c3331")

            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stdout, branch)


if __name__ == "__main__":
    unittest.main()
