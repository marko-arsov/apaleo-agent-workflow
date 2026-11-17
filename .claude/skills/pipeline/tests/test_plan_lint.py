from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))

from plan_lint import lint, main  # noqa: E402

PRODUCT = """# SL-1 — Return original event dates

## Observable outcome
Occurrences carry the stored event dates.

## Examples
- **AC-1** Given a weekly event stored 2026-09-19, when listing 2026-09-26, then originalEvent.from is 2026-09-19.

## Scope
### In
- Occurrence list response
### Out
- Public v1
"""

IMPLEMENTATION = """# SL-1 — Implementation

## Lane
manual → /implement

## Decisions
- D1 — Copy the title mapping (`apaleo/src/Booking.cs:3`). Why: same seam. Rejected: a new service.

## Traps
- `OriginalFrom` already means a cancelled slot (`src/Booking.cs:5`).

## Read first
- `apaleo/src/Booking.cs:1-4` — mapping shape

## Steps
1. Add the dates — `src/Booking.cs` — done when ReturnsOriginalEventDates passes.

## Tests
| AC | Layer | File | Test name | Command | Red |
|---|---|---|---|---|---|
| AC-1 | unit | `apaleo/test/BookingTest.cs` | ReturnsOriginalEventDates | unit | yes |

## Assumptions
none
"""


def _git(repo: Path, *args: str) -> None:
    env = os.environ | {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


class PlanLintTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        repo = self.root / "apaleo"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "Booking.cs").write_text("\n".join(f"line {n}" for n in range(1, 11)) + "\n")
        _git(repo, "init", "-q")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "init")
        _git(repo, "update-ref", "refs/remotes/origin/master", "HEAD")
        self.plan = self.root / "ai-plans" / "markoarsov" / "sl-1-dates"
        self.plan.mkdir(parents=True)
        self.write(PRODUCT, IMPLEMENTATION, test="ReturnsOriginalEventDates")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, product: str, implementation: str, *, test: str, expected_lines: int = 100) -> None:
        (self.plan / "product.md").write_text(product)
        (self.plan / "implementation.md").write_text(implementation)
        manifest = {
            "acceptance_criteria": [
                {"id": "AC-1", "test": test, "test_path": "apaleo/test/BookingTest.cs", "command": "unit"}
            ],
            "diff_budget": {"expected_lines": expected_lines},
        }
        (self.plan / "pipeline.json").write_text(json.dumps(manifest))

    def test_a_complete_plan_passes_cleanly(self) -> None:
        result = lint(self.plan, self.root)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.citations_checked, 3)

    def test_a_partial_path_resolves_by_unique_suffix(self) -> None:
        partial = IMPLEMENTATION.replace("`apaleo/src/Booking.cs:3`", "`Repo/Booking.cs:3`")
        self.write(PRODUCT, partial, test="ReturnsOriginalEventDates")
        self.assertTrue(any("not on origin" in error for error in lint(self.plan, self.root).errors))
        repo = self.root / "apaleo"
        (repo / "src" / "Repo").mkdir()
        (repo / "src" / "Repo" / "Booking.cs").write_text("a\nb\nc\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "repo")
        _git(repo, "update-ref", "refs/remotes/origin/master", "HEAD")
        result = lint(self.plan, self.root)
        self.assertEqual(result.errors, [])
        self.assertTrue(any("abbreviated; cite `apaleo/src/Repo/Booking.cs`" in w for w in result.warnings))

    def test_missing_file_and_line_past_the_end_are_errors(self) -> None:
        broken = IMPLEMENTATION.replace("`apaleo/src/Booking.cs:3`", "`apaleo/src/Missing.cs:3`").replace(
            "`apaleo/src/Booking.cs:1-4`", "`apaleo/src/Booking.cs:9-40`"
        )
        self.write(PRODUCT, broken, test="ReturnsOriginalEventDates")
        errors = lint(self.plan, self.root).errors
        self.assertTrue(any("not on origin" in error and "Missing.cs" in error for error in errors))
        self.assertTrue(any("past the end" in error and "10 lines" in error for error in errors))

    def test_suffix_match_resolves_an_abbreviated_path(self) -> None:
        abbreviated = IMPLEMENTATION.replace("`apaleo/src/Booking.cs:3`", "`Booking.cs:3` and `src/Booking.cs:3`")
        self.write(PRODUCT, abbreviated, test="ReturnsOriginalEventDates")
        result = lint(self.plan, self.root)
        self.assertEqual(result.errors, [])
        self.assertTrue(any("without a directory" in warning for warning in result.warnings))

    def test_csharp_description_test_name_and_missing_example_are_errors(self) -> None:
        self.write(PRODUCT.replace("**AC-1**", "**Example**"), IMPLEMENTATION, test="returns the original dates")
        errors = lint(self.plan, self.root).errors
        self.assertIn("product.md: no example for AC-1", errors)
        self.assertTrue(any("literal method name" in error for error in errors))

    def test_placeholder_and_missing_sections_are_errors(self) -> None:
        self.write(PRODUCT.replace("## Examples", "## Behaviour"), IMPLEMENTATION.replace("## Steps", "## Order") + "\nTBD\n", test="ReturnsOriginalEventDates")
        errors = lint(self.plan, self.root).errors
        self.assertIn("product.md: missing `## Examples` section", errors)
        self.assertIn("implementation.md: missing `## Steps` section", errors)
        self.assertIn("implementation.md: unresolved placeholder `TBD`", errors)

    def test_plan_over_budget_warns(self) -> None:
        padded = IMPLEMENTATION + "\n".join(f"- detail {n}" for n in range(200))
        self.write(PRODUCT, padded, test="ReturnsOriginalEventDates", expected_lines=100)
        warnings = lint(self.plan, self.root).warnings
        self.assertTrue(any("budget for ~100 changed lines is 120" in warning for warning in warnings))

    def test_rendered_pipeline_section_does_not_count_toward_the_budget(self) -> None:
        rendered = IMPLEMENTATION + "\n## Execution Pipeline\n" + "\n".join(f"| row {n} |" for n in range(200))
        self.write(PRODUCT, rendered, test="ReturnsOriginalEventDates")
        self.assertFalse(any("budget" in warning for warning in lint(self.plan, self.root).warnings))

    def test_cli_lints_the_newest_version_and_fails_on_errors(self) -> None:
        version = self.plan / "v2"
        version.mkdir()
        (version / "product.md").write_text(PRODUCT.replace("## Examples", "## Behaviour"))
        (version / "implementation.md").write_text(IMPLEMENTATION)
        (version / "pipeline.json").write_text((self.plan / "pipeline.json").read_text())
        output = io.StringIO()
        with redirect_stdout(output):
            status = main([str(self.plan), "--root", str(self.root)])
        self.assertEqual(status, 1)
        self.assertIn("v2", output.getvalue())
        self.assertIn("missing `## Examples`", output.getvalue())


if __name__ == "__main__":
    unittest.main()
