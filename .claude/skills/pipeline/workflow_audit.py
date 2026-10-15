#!/usr/bin/env python3
"""Produce a deterministic checkpoint and security-boundary audit."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from common import find_root


CHECKPOINTS = {
    "IN-1": ("enforced", "specify/SKILL.md", "One written five-file spec names tests and completion artifacts."),
    "IN-2": ("enforced", "references/specify-process.md", "Research/interview and final confirmation precede product writes."),
    "IN-3": ("external", "references/specify-process.md", "Tracker priority/ownership is not enforced by this local runner."),
    "IN-4": ("advisory", "pipeline/pipeline_manifest.py", "Expected and maximum file/line budgets guide scope; overshoots are recorded, not blocked."),
    "CTX-1": ("partial", "AGENTS.md", "Compact root instructions exist, but the workspace root is not a versioned repository."),
    "CTX-2": ("enforced", "prune-context/SKILL.md", "AGENTS.md is compact and deterministic pruning is proposal-only."),
    "CTX-3": ("partial", "references/e2e-stack.md", "Setup is scripted, but provider environments are not immutable snapshots."),
    "CTX-4": ("deferred", ".claude/conventions/", "Local mechanical conventions exist; repository architecture/doc CI awaits repository work."),
    "CTX-5": ("enforced", "add-rule/SKILL.md", "Discoveries route to mechanical rules, scoped knowledge, counters, and pruning."),
    "PLN-1": ("enforced", "specify/SKILL.md", "Specify is no-product-code; execution starts only from its complete plan set."),
    "PLN-2": ("enforced", "references/specify-process.md", "Human final confirmation challenges every plan without another recurring model call."),
    "PLN-3": ("enforced", "pipeline/implement_pipeline.py", "Plan and implementation use fresh sessions; plan hashes preserve revision audit and rebind state."),
    "PLN-4": ("documented", "references/specify-process.md", "Plans require independently testable phases and exact per-AC checks."),
    "EXE-1": ("gap", "references/security-boundary.md", "Provider processes use host-level permission bypass rather than OS isolation."),
    "EXE-2": ("gap", "references/security-boundary.md", "Outbound provider/process network access is not allowlisted."),
    "EXE-3": ("partial", "pipeline/untrusted_input.py", "Known external ingestions are sanitised; direct filesystem/tool reads are not isolated."),
    "EXE-4": ("enforced", "pipeline/pipeline_manifest.py", "Risk, path, mutation, and high-risk confirmation contracts fail closed."),
    "EXE-5": ("enforced", "references/worktrees.md", "Feature work runs in per-branch worktrees; parked mains are checked."),
    "VER-1": ("enforced", "pipeline/verification.py", "Every AC references an exact runnable command and parser."),
    "VER-2": ("enforced", "pipeline/verification.py", "Completion parses observed command output and current diff evidence."),
    "VER-3": ("conditional", "review/SKILL.md", "Fresh review is risk-recommended but remains optional by hard stage constraint."),
    "VER-4": ("conditional", "implement/SKILL.md", "Plan-selected E2E runs inside implementation; not every change requires E2E."),
    "VER-5": ("enforced", "implement-tests/SKILL.md", "Route choice is flexible; red proof and opt-in diff mutation challenge tests remain enforced."),
    "VER-6": ("partial", "pipeline/verification.py", "Diff static/convention and secret scans run; dependency/SAST CI awaits repo work."),
    "REV-1": ("external", "references/security-boundary.md", "Human approval/branch protection is GitHub-owned."),
    "REV-2": ("enforced", "pipeline/verification.py", "Evidence records commands, parsed results, outputs, ACs, and diff fingerprint."),
    "REV-3": ("external", "references/pr-review.md", "Team review latency/capacity metrics are outside this local workflow."),
    "REV-4": ("enforced", "references/pipeline-autonomy.md", "Provider retries and all fix loops are bounded and escalate."),
    "PST-1": ("policy-gap", "AGENTS.md", "AI attribution is deliberately prohibited, so provenance is not labelled."),
    "PST-2": ("partial", "pipeline/pipeline_state.py", "Local attempts/routes/durations/evidence persist; no central OpenTelemetry export."),
    "PST-3": ("partial", "address-pr-comments/SKILL.md", "Human comments feed counters/proposals; no unattended SessionEnd model call."),
    "ORG-1": ("external", "references/security-boundary.md", "Stability/provenance metrics are organization-owned."),
    "ORG-2": ("partial", "WORKFLOW.md", "Changes carry cost classes; provider token spend is not centrally measured here."),
    "ORG-3": ("gap", "references/security-boundary.md", "Host credentials are not proven short-lived or stage-scoped."),
    "ORG-4": ("partial", "references/staging-smoke.md", "Production writes are prohibited; identity/credential layers remain external."),
    "ORG-5": ("enforced", "prune-context/SKILL.md", "Skills are listed, tested, logged, and proposal-pruned."),
}


def security(root: Path) -> dict:
    runner = (root / ".claude" / "skills" / "pipeline" / "implement_pipeline.py").read_text(
        encoding="utf-8", errors="replace"
    )
    bypass = "dangerously-bypass-approvals-and-sandbox" in runner or "dangerously-skip-permissions" in runner
    return {
        "token_scope_and_lifetime": {
            "status": "external-unverified",
            "finding": "Provider and gh credentials are inherited from the host; the runner cannot prove short lifetime or per-stage scope.",
        },
        "tool_allowlisting": {
            "status": "partial",
            "finding": "Plan path contracts and deterministic hooks constrain outcomes, but provider CLIs run with permission bypass flags."
            if bypass else "Provider command policy did not expose known bypass flags.",
        },
        "outbound_network": {
            "status": "unrestricted",
            "finding": "Provider, git, package, Docker, and GitHub network access is not separated by an egress firewall.",
        },
        "triple_coexistence": {
            "status": "present",
            "finding": "Untrusted content, host write-capable credentials, and outbound network access can coexist in AI stages; sanitization lowers prompt-injection risk but is not isolation.",
        },
        "local_tools": {
            name: bool(shutil.which(name)) for name in ("semgrep", "gitleaks", "dotnet-stryker")
        },
    }


def render(checkpoints: dict, boundary: dict) -> str:
    lines = [
        "# Agentic workflow checkpoint audit",
        "",
        "Statuses describe current evidence; `external` and `deferred` are explicit gaps, not passes.",
        "",
        "| Checkpoint | Status | Evidence | Note |",
        "|---|---|---|---|",
    ]
    for checkpoint, (status, evidence, note) in checkpoints.items():
        lines.append(f"| `{checkpoint}` | **{status}** | `{evidence}` | {note} |")
    lines += ["", "## Primary security controls", ""]
    for name, value in boundary.items():
        if name == "local_tools":
            tools = ", ".join(f"{tool}={'yes' if installed else 'no'}" for tool, installed in value.items())
            lines.append(f"- **Local scanners:** {tools}.")
        else:
            lines.append(f"- **{name.replace('_', ' ').title()}: {value['status']}** — {value['finding']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else find_root()
    boundary = security(root)
    output = Path(args.output) if args.output else root / ".local" / "workflow-audits" / "latest.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(CHECKPOINTS, boundary), encoding="utf-8")
    output.with_suffix(".json").write_text(
        json.dumps(
            {
                "checkpoints": {
                    key: {"status": value[0], "evidence": value[1], "note": value[2]}
                    for key, value in CHECKPOINTS.items()
                },
                "security": boundary,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
