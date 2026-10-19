from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILLS = Path(__file__).resolve().parents[2]
OPEN_RIDER = SKILLS / "open-rider" / "open-rider.sh"


def init_repo(path: Path, branch: str) -> None:
    path.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-q", "-b", branch, str(path)],
        text=True,
        capture_output=True,
        check=True,
    )


class OpenRiderTests(unittest.TestCase):
    def test_issue_id_opens_apaleo_solution_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            branch = "jdoe/sl-100-example"
            apaleo = root / "worktrees" / branch / "apaleo"
            init_repo(root / "apaleo", "master")
            init_repo(apaleo, branch)
            (root / "AGENTS.md").write_text("# fixture\n", encoding="utf-8")
            (apaleo / "Apaleo.sln").write_text("fixture\n", encoding="utf-8")
            rider = root / "Rider.app"
            rider.mkdir()

            env = os.environ.copy()
            env.update({"APALEO_ROOT": str(root), "RIDER_APP": str(rider)})
            process = subprocess.run(
                [str(OPEN_RIDER), "SL-100", "--dry-run"],
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn(f"resolved: {branch}", process.stdout)
            self.assertIn(f"open Rider → {apaleo / 'Apaleo.sln'}", process.stdout)


if __name__ == "__main__":
    unittest.main()
