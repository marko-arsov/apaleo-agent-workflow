from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


PIPELINE = Path(__file__).resolve().parents[1]
ROOT_SH = PIPELINE / "root.sh"


class RootShTests(unittest.TestCase):
    def test_issue_id_ignores_repo_named_source_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            branch = "jdoe/sl-100-example"
            development = root / "worktrees" / branch / "development"
            (development / ".git").mkdir(parents=True)
            (development / "apaleo").mkdir()

            process = subprocess.run(
                [
                    "bash",
                    "-c",
                    'source "$1"; ROOT="$2"; resolve_feature_branch "$3"',
                    "bash",
                    str(ROOT_SH),
                    str(root),
                    "sl-100",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stdout, branch)


if __name__ == "__main__":
    unittest.main()
