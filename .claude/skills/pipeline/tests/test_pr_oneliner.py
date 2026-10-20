from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[2] / "pr-oneliner" / "pr_oneliner.py"
SPEC = importlib.util.spec_from_file_location("pr_oneliner", MODULE)
pr_oneliner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pr_oneliner)


class PrOnelinerTests(unittest.TestCase):
    def test_outcome_sentence_is_the_first_sentence_only(self) -> None:
        text = """# Title

## Outcome

When a reservation comes out of a group block, each night is charged at the price stored for that
night on the block. Older blocks keep one daily rate.

## Behavior
"""
        self.assertEqual(
            pr_oneliner.outcome_sentence(text),
            "When a reservation comes out of a group block, each night is charged at the price stored for that night on the block.",
        )

    def test_outcome_sentence_missing_heading_is_empty(self) -> None:
        self.assertEqual(pr_oneliner.outcome_sentence("# Title\n\nNo outcome.\n"), "")

    def test_message_uses_the_pr_title_and_short_links(self) -> None:
        text = pr_oneliner.format_message(
            [
                {
                    "title": "SL-129 Price picked-up block nights from their stored GrossRate",
                    "url": "https://github.com/apaleo/apaleo/pull/13315",
                },
                {
                    "title": "Cover SL-129 Price picked-up block nights from their stored GrossRate in E2E",
                    "url": "https://github.com/apaleo/development/pull/6544",
                },
            ]
        )
        self.assertEqual(
            text,
            "\n".join(
                [
                    "Price picked-up block nights from their stored GrossRate:",
                    "• github.com/apaleo/apaleo/pull/13315",
                    "• github.com/apaleo/development/pull/6544",
                ]
            ),
        )

    def test_pr_urls_keep_record_order(self) -> None:
        record = """## apaleo
- URL: https://github.com/apaleo/apaleo/pull/1

## development
- URL: https://github.com/apaleo/development/pull/2
"""
        self.assertEqual(
            pr_oneliner.pr_urls(record),
            [
                "https://github.com/apaleo/apaleo/pull/1",
                "https://github.com/apaleo/development/pull/2",
            ],
        )


if __name__ == "__main__":
    unittest.main()
