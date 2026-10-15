from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PIPELINE = Path(__file__).resolve().parents[1]
ROOT = PIPELINE.parents[2]
sys.path.insert(0, str(PIPELINE))
SPEC = importlib.util.spec_from_file_location("conventions_hook", ROOT / ".claude/hooks/conventions.py")
assert SPEC and SPEC.loader
conventions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(conventions)


class ConventionHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        convention_dir = self.root / ".claude/conventions"
        rules_dir = convention_dir / "rules"
        rules_dir.mkdir(parents=True)
        self.registry = convention_dir / "registry.json"
        self.allowlist = convention_dir / "allowlist.json"
        self.registry.write_text(
            json.dumps(
                {
                    "version": 1,
                    "rules": [
                        {
                            "id": "authorization-must-use-opa",
                            "severity": "block",
                            "file_globs": ["apaleo/**/*.cs"],
                            "allowed_paths": ["apaleo/**/Infrastructure/Authorization/**/*.cs"],
                            "allowed_namespaces": ["Apaleo.Api.Infrastructure.Authorization"],
                            "patterns": [r":\s*(?:IAuthorizationHandler|AuthorizationHandler\s*<)"],
                            "message": "Put authorization policy in the OPA layer.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.allowlist.write_text('{"version":1,"exemptions":[]}', encoding="utf-8")
        (rules_dir / "authorization-must-use-opa.yml").write_text(
            '\n'.join(
                (
                    'id: "authorization-must-use-opa"',
                    "tier: 1",
                    'added: "2026-08-31"',
                    'source: "manual"',
                    'statement: "Authorization belongs in OPA."',
                    "violations: 0",
                    "last_violation: null",
                    "",
                )
            ),
            encoding="utf-8",
        )
        self.patches = (
            patch.object(conventions, "ROOT", self.root),
            patch.object(conventions, "REGISTRY", self.registry),
            patch.object(conventions, "ALLOWLIST", self.allowlist),
        )
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_opa_worked_example_blocks_outside_layer(self) -> None:
        findings = conventions.check(
            str(
                self.root
                / "worktrees/example/apaleo/src/Apaleo.Api/Features/Foo/FooAuthorizationService.cs"
            ),
            "public sealed class FooAuthorizationHandler : IAuthorizationHandler {}",
        )
        self.assertEqual(findings[0]["severity"], "block")
        self.assertIn("OPA layer", findings[0]["message"])

    def test_opa_layer_and_reviewable_allowlist_are_accepted(self) -> None:
        self.assertEqual(
            conventions.check(
                "apaleo/src/Apaleo.Api/Infrastructure/Authorization/FooAuthorizationService.cs",
                "public sealed class FooAuthorizationHandler : IAuthorizationHandler {}",
            ),
            [],
        )
        self.allowlist.write_text(
            json.dumps(
                {
                    "version": 1,
                    "exemptions": [
                        {
                            "rule": "authorization-must-use-opa",
                            "path": "apaleo/src/Legacy/FooAuthorizationService.cs",
                            "reason": "Approved legacy integration boundary.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(
            conventions.check(
                "apaleo/src/Legacy/FooAuthorizationService.cs",
                "public sealed class FooAuthorizationHandler : IAuthorizationHandler {}",
            ),
            [],
        )

    def test_advisory_findings_do_not_block(self) -> None:
        registry = json.loads(self.registry.read_text(encoding="utf-8"))
        registry["rules"][0]["severity"] = "advisory"
        self.registry.write_text(json.dumps(registry), encoding="utf-8")
        metadata = self.root / ".claude/conventions/rules/authorization-must-use-opa.yml"
        metadata.write_text(metadata.read_text(encoding="utf-8").replace("tier: 1", "tier: 2"), encoding="utf-8")
        findings = conventions.check(
            "apaleo/src/FooAuthorizationService.cs",
            "public sealed class FooAuthorizationHandler : IAuthorizationHandler {}",
        )
        self.assertEqual(findings[0]["severity"], "advisory")

    def test_enforcement_files_remain_repairable_during_promotion(self) -> None:
        self.assertEqual(
            conventions.hook_findings(
                str(self.root / ".claude/conventions/registry.json"),
                "temporarily inconsistent while the approved promotion is applied",
            ),
            [],
        )

    def test_exemption_allowlist_rejects_globs(self) -> None:
        allowlist = {
            "version": 1,
            "exemptions": [
                {
                    "rule": "authorization-must-use-opa",
                    "path": "apaleo/src/Legacy/**",
                    "reason": "Too broad.",
                }
            ],
        }
        errors = conventions.validate_config(
            json.loads(self.registry.read_text(encoding="utf-8")),
            allowlist,
        )
        self.assertIn("exemption paths must be exact; globs are not allowed", errors)

    def test_hook_payload_accepts_cursor_write_and_strreplace(self) -> None:
        write_pairs = conventions.hook_payload(
            {
                "tool_name": "Write",
                "tool_input": {
                    "path": "development/src/tests/core/calendar/calendar-events-spec.ts",
                    "contents": "export const x = 1;",
                },
            }
        )
        self.assertEqual(write_pairs[0][1], "export const x = 1;")
        replace_pairs = conventions.hook_payload(
            {
                "tool_name": "StrReplace",
                "tool_input": {
                    "path": "development/src/tests/core/calendar/calendar-events-spec.ts",
                    "old_string": "a",
                    "new_string": "b",
                },
            }
        )
        self.assertEqual(replace_pairs[0][1], "b")

    def _findings(self, payload: dict) -> list[dict]:
        return [
            finding
            for path, content, baseline in conventions.hook_payload(payload)
            for finding in conventions.hook_findings(path, content, baseline)
        ]

    def test_whole_file_write_keeps_a_violation_the_file_already_had(self) -> None:
        handler = "class OldHandler : IAuthorizationHandler {}\n"
        target = self.root / "worktrees/markoarsov/x/apaleo/src/Legacy/OldHandler.cs"
        target.parent.mkdir(parents=True)
        target.write_text(handler + "// before\n", encoding="utf-8")
        write = {"tool_name": "Write", "tool_input": {"path": str(target), "contents": handler + "// after\n"}}
        self.assertEqual(self._findings(write), [])

        write["tool_input"]["contents"] = handler + "class NewHandler : IAuthorizationHandler {}\n"
        self.assertEqual(
            [item["rule"] for item in self._findings(write)], ["authorization-must-use-opa"]
        )

    def test_whole_file_write_of_a_new_file_is_checked_in_full(self) -> None:
        target = self.root / "worktrees/markoarsov/x/apaleo/src/New/NewHandler.cs"
        write = {
            "tool_name": "Write",
            "tool_input": {"path": str(target), "contents": "class NewHandler : IAuthorizationHandler {}"},
        }
        self.assertEqual(
            [item["rule"] for item in self._findings(write)], ["authorization-must-use-opa"]
        )

    def test_replace_blocks_only_a_violation_it_adds(self) -> None:
        path = "apaleo/src/Legacy/OldHandler.cs"
        kept = {
            "tool_name": "StrReplace",
            "tool_input": {
                "path": path,
                "old_string": "class OldHandler : IAuthorizationHandler { int a; }",
                "new_string": "class OldHandler : IAuthorizationHandler { int b; }",
            },
        }
        self.assertEqual(self._findings(kept), [])
        added = {
            "tool_name": "StrReplace",
            "tool_input": {"path": path, "old_string": "class OldHandler {}", "new_string": "class OldHandler : IAuthorizationHandler {}"},
        }
        self.assertEqual(
            [item["rule"] for item in self._findings(added)], ["authorization-must-use-opa"]
        )

    def test_hook_stdout_is_cursor_json(self) -> None:
        allow, allow_code = conventions.hook_stdout([])
        self.assertEqual(allow, {"permission": "allow"})
        self.assertEqual(allow_code, 0)
        deny, deny_code = conventions.hook_stdout(
            [
                {
                    "rule": "authorization-must-use-opa",
                    "path": "apaleo/src/Foo.cs",
                    "severity": "block",
                    "message": "Put authorization policy in the OPA layer.",
                    "patterns": [": IAuthorizationHandler"],
                }
            ]
        )
        self.assertEqual(deny["permission"], "deny")
        self.assertIn("OPA layer", deny["agent_message"])
        self.assertEqual(deny_code, 2)


class ProductionConventionConfigTests(unittest.TestCase):
    WRAPPER = """
package core

allow_put_calendar_event_occurrence_override if {
	is_interactive_user
	mcp_gate_passed
	calendar_event_action_interactive_user_has_access
}
"""
    UNIQUE = """
package core

allow_delete_calendar_events_bulk if {
	is_interactive_user
	mcp_gate_passed
	count(property_ids) > 0
	every property_id in property_ids {
		some user_permission in user_property_permissions[property_id]
	}
}
"""
    CLASSIC_CTOR = """
internal class SplitCalendarEventService : ISplitCalendarEventService
{
    private readonly ICalendarEventRepository _repository;

    public SplitCalendarEventService(ICalendarEventRepository repository)
    {
        _repository = Check.NotNull(repository);
    }
}
"""
    PRIMARY_CTOR = """
internal class SplitCalendarEventService(
    ICalendarEventRepository repository)
    : ISplitCalendarEventService
{
    private readonly ICalendarEventRepository _repository = Check.NotNull(repository);
}
"""

    def test_real_registry_validates(self) -> None:
        errors = conventions.validate_config(
            json.loads((ROOT / ".claude/conventions/registry.json").read_text(encoding="utf-8")),
            json.loads((ROOT / ".claude/conventions/allowlist.json").read_text(encoding="utf-8")),
        )
        self.assertEqual(errors, [])

    def test_opa_rename_wrapper_is_blocked_and_owner_file_is_allowed(self) -> None:
        blocked = conventions.check(
            "apaleo/src/Apaleo.Api/Infrastructure/Authorization/core/policies/calendar/event/put-occurrence-override.rego",
            self.WRAPPER,
        )
        self.assertEqual(blocked[0]["rule"], "reuse-identical-opa-decision")
        self.assertEqual(blocked[0]["severity"], "block")
        self.assertEqual(
            conventions.check(
                "apaleo/src/Apaleo.Api/Infrastructure/Authorization/core/policies/calendar/event/calendar-event-write.rego",
                self.WRAPPER,
            )[0]["rule"],
            "reuse-identical-opa-decision",
        )
        self.assertEqual(
            conventions.check(
                "apaleo/src/Apaleo.Api/Infrastructure/Authorization/core/policies/calendar/event/calendar-event-action.rego",
                self.WRAPPER,
            ),
            [],
        )
        self.assertEqual(
            conventions.check(
                "apaleo/src/Apaleo.Api/Infrastructure/Authorization/core/policies/calendar/event/delete-bulk.rego",
                self.UNIQUE,
            ),
            [],
        )

    def test_check_not_null_is_advisory_outside_generated_clients(self) -> None:
        findings = conventions.check(
            "apaleo/src/Apaleo.Core/Extensions/EntityResolver.cs",
            "ArgumentNullException.ThrowIfNull(ids);",
        )
        self.assertEqual(findings[0]["rule"], "application-csharp-use-check-not-null")
        self.assertEqual(findings[0]["severity"], "advisory")
        allow, code = conventions.hook_stdout(findings)
        self.assertEqual(code, 0)
        self.assertEqual(allow["permission"], "allow")
        self.assertIn("Check.NotNull", allow["agent_message"])
        self.assertEqual(
            conventions.check(
                "apaleo/src/Clients/Apaleo.Automation.ApiClient/AutomationAPI.cs",
                "ArgumentNullException.ThrowIfNull(ids);",
            ),
            [],
        )

    def test_primary_constructor_is_advisory_for_classic_di_ctors(self) -> None:
        findings = conventions.check(
            "apaleo/src/Apaleo.Calendar/Services/SplitCalendarEventService.cs",
            self.CLASSIC_CTOR,
        )
        self.assertEqual(findings[0]["rule"], "application-csharp-use-primary-constructor")
        self.assertEqual(findings[0]["severity"], "advisory")
        allow, code = conventions.hook_stdout(findings)
        self.assertEqual(code, 0)
        self.assertEqual(allow["permission"], "allow")
        self.assertIn("primary constructor", allow["agent_message"])
        self.assertEqual(
            conventions.check(
                "apaleo/src/Apaleo.Calendar/Services/SplitCalendarEventService.cs",
                self.PRIMARY_CTOR,
            ),
            [],
        )
        self.assertEqual(
            conventions.check(
                "apaleo/test/Apaleo.Calendar.Tests/Services/SplitCalendarEventServiceTest.cs",
                self.CLASSIC_CTOR,
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
