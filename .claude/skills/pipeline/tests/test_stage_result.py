from __future__ import annotations

import sys
import unittest
from pathlib import Path


PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))

from stage_result import (  # noqa: E402
    classify,
    classify_failure,
    health_failure_reason,
    provider_diagnostic_text,
)


class StageResultTests(unittest.TestCase):
    def test_spend_limit_is_permanent(self) -> None:
        kind, _ = classify_failure("You've hit your individual spend limit")
        self.assertEqual(kind, "permanent_provider")

    def test_claude_oauth_expiry_is_permanent(self) -> None:
        blob = (
            '{"terminal_reason":"api_error","result":'
            '"Failed to authenticate: OAuth session expired and could not be refreshed"}'
        )
        kind, matched = classify_failure(blob)
        self.assertEqual(kind, "permanent_provider")
        self.assertRegex(matched.lower(), r"failed to authenticate|oauth session expired")

    def test_health_reason_prefers_json_result_over_json_tail(self) -> None:
        raw = (
            '{"presence_geo":"","iterations":[],"speed":"standard","modelUsage":{},'
            '"permission_denials":[],"terminal_reason":"api_error",'
            '"fast_mode_state":"off","fast_mode_disabled_reason":"sdk_opt_in_required",'
            '"subtype":"success","api_error_status":null,'
            '"result":"Failed to authenticate: OAuth session expired and could not be refreshed",'
            '"type":"result","duration_ms":26}'
        )
        reason = health_failure_reason(raw, "", 1)
        self.assertEqual(
            reason,
            "Failed to authenticate: OAuth session expired and could not be refreshed",
        )
        self.assertNotIn("presence_geo", reason)

    def test_plain_429_is_temporary(self) -> None:
        kind, _ = classify_failure("HTTP 429 Too Many Requests; retry-after: 30")
        self.assertEqual(kind, "transient_provider")

    def test_reconnect_loop_is_stall(self) -> None:
        kind, _ = classify_failure("stream repeatedly disconnected during reconnect loop")
        self.assertEqual(kind, "provider_stall")

    def test_success_marker_must_start_a_line(self) -> None:
        outcome, _ = classify({}, "The prompt says `PIPELINE_STAGE_OK: implement`.", "")
        self.assertEqual(outcome, "error")
        outcome, _ = classify({}, "done\nPIPELINE_STAGE_OK: implement\n", "")
        self.assertEqual(outcome, "ok")

    def test_glued_success_marker_is_accepted(self) -> None:
        blob = (
            "property creation is failing with 500 across almost all tests. "
            "Nothing committed or pushed.PIPELINE_STAGE_OK: implement-tests"
        )
        outcome, reason = classify({}, blob, "")
        self.assertEqual(outcome, "ok")
        self.assertEqual(reason, "")

    def test_prompt_wording_is_not_a_permanent_provider_failure(self) -> None:
        blob = (
            "Never add AI attribution, model names, or generated-by trailers to commits.\n"
            + ("x" * 400)
            + "\nfile not found in the worktree"
        )
        kind, _ = classify_failure(blob)
        self.assertNotEqual(kind, "permanent_provider")

    def test_narrative_application_500_is_not_a_provider_outage(self) -> None:
        blob = (
            "property creation (`ensureNewPropertyCreated`) is failing with 500 "
            "across almost all tests"
        )
        kind, _ = classify_failure(blob)
        self.assertEqual(kind, "semantic")
        outcome, reason = classify({}, blob, "")
        self.assertEqual(outcome, "error")
        self.assertNotEqual(reason, "500")

    def test_provider_http_500_stays_transient(self) -> None:
        kind, matched = classify_failure("API error: HTTP 500 Internal Server Error")
        self.assertEqual(kind, "transient_provider")
        self.assertIn("500", matched)

    def test_model_not_found_stays_permanent(self) -> None:
        kind, _ = classify_failure("The model 'claude-missing' was not found")
        self.assertEqual(kind, "permanent_provider")

    def test_successful_transcript_is_not_a_provider_diagnostic(self) -> None:
        transcript = (
            "Never add AI attribution, model names, or generated-by trailers.\n"
            "property creation is failing with 500. file not found"
        )
        diagnostic = provider_diagnostic_text(
            {"subtype": "success", "is_error": False, "result": transcript},
            "",
        )
        kind, _ = classify_failure(diagnostic)
        self.assertEqual(kind, "semantic")

    def test_selected_stage_skip_is_visible(self) -> None:
        outcome, reason = classify({}, "PIPELINE_STAGE_SKIPPED: review reason=no build", "")
        self.assertEqual(outcome, "skipped")
        self.assertIn("no build", reason)

    def test_input_questions_are_preserved_before_or_after_marker(self) -> None:
        before = "1. Confirm the external production action.\n\nPIPELINE_INPUT_REQUIRED\n"
        after = "PIPELINE_INPUT_REQUIRED\n\n1. Confirm the external production action.\n"
        for blob in (before, after):
            with self.subTest(blob=blob):
                outcome, reason = classify({}, blob, "")
                self.assertEqual(outcome, "blocked")
                self.assertIn("Confirm the external production action", reason)


if __name__ == "__main__":
    unittest.main()
