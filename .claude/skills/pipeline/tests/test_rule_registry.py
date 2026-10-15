from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))

from rule_registry import (  # noqa: E402
    RuleError,
    candidates,
    load_rules,
    promote,
    record_violation,
    register,
    route_tier,
)


class RuleRegistryTests(unittest.TestCase):
    def test_checkability_question_selects_tier(self) -> None:
        self.assertEqual(route_tier(checkable=False, always_wrong=True), 3)
        self.assertEqual(route_tier(checkable=True, always_wrong=False), 2)
        self.assertEqual(route_tier(checkable=True, always_wrong=True), 1)

    def test_router_has_no_operator_selected_tier(self) -> None:
        source = (PIPELINE / "rule_registry.py").read_text(encoding="utf-8")
        self.assertNotIn('add_argument("--tier"', source)

    def test_second_tier_three_violation_requires_escalation_and_deduplicates_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            register(
                root,
                rule_id="user-facing-errors",
                statement="Errors shown to users must use user-facing language.",
                source="manual",
                checkable=False,
                always_wrong=False,
                added="2026-01-01",
            )
            first = record_violation(root, "user-facing-errors", "pr-comment-1", "2026-02-01")
            duplicate = record_violation(root, "user-facing-errors", "pr-comment-1", "2026-02-01")
            second = record_violation(root, "user-facing-errors", "pr-comment-2", "2026-03-01")
            self.assertEqual(first["violations"], 1)
            self.assertTrue(duplicate["duplicate"])
            self.assertEqual(second["violations"], 2)
            self.assertTrue(second["escalation_required"])
            self.assertEqual(load_rules(root)["user-facing-errors"][1]["violations"], 2)

    def test_promotion_only_strengthens_a_mechanically_checkable_rule(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            register(
                root,
                rule_id="advisory-example",
                statement="Flag endpoint try blocks for review.",
                source="manual",
                checkable=True,
                always_wrong=False,
                added="2026-01-01",
            )
            promoted = promote(root, "advisory-example", checkable=True, always_wrong=True)
            self.assertEqual(promoted["tier"], 1)
            with self.assertRaisesRegex(RuleError, "cannot be forced"):
                promote(root, "advisory-example", checkable=False, always_wrong=False)

    def test_pruning_candidates_apply_six_month_and_recurrence_ratchets(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            register(
                root,
                rule_id="unused-rule",
                statement="An old rule.",
                source="manual",
                checkable=False,
                always_wrong=False,
                added="2026-02-28",
            )
            register(
                root,
                rule_id="recurring-rule",
                statement="A recurring rule.",
                source="manual",
                checkable=False,
                always_wrong=False,
                added="2026-08-01",
            )
            record_violation(root, "recurring-rule", "a", "2026-08-10")
            record_violation(root, "recurring-rule", "b", "2026-08-20")
            result = candidates(root, as_of="2026-08-31")
            self.assertEqual([rule["id"] for rule in result["deletion"]], ["unused-rule"])
            self.assertEqual([rule["id"] for rule in result["escalation"]], ["recurring-rule"])

    def test_six_month_cutoff_uses_calendar_months(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            register(
                root,
                rule_id="calendar-boundary",
                statement="A rule exactly six calendar months old.",
                source="manual",
                checkable=False,
                always_wrong=False,
                added="2026-02-28",
            )
            result = candidates(root, as_of="2026-08-31")
            self.assertEqual([rule["id"] for rule in result["deletion"]], ["calendar-boundary"])


if __name__ == "__main__":
    unittest.main()
