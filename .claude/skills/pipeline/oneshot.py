#!/usr/bin/env python3
"""Manual Bugbot-reply drafting: cheapest model, no tools, no repo access.

Uses `agent -p --mode ask --model <cheap> --output-format text`.
Ask mode is read-only. Shell does git/gh around this.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from models import CHEAP_DEFAULT

TEMPLATES = {
    "bugbot-replies": """Draft paste-ready GitHub replies for these UNFIXABLE Bugbot ledger entries only.
Factual team tone. No posting. No AI attribution. No @cursor control commands.
Return markdown with one reply per entry.

Entries:
{entries}
""",
}


def agent_bin() -> str:
    b = os.environ.get("AGENT_BIN") or shutil.which("agent")
    if not b:
        p = Path.home() / ".local" / "bin" / "agent"
        b = str(p) if p.is_file() else ""
    if not b:
        raise SystemExit("ERROR: agent CLI not found")
    return b


def complete(name: str, model: str | None = None, **kwargs: str) -> str:
    model = model or os.environ.get("PIPELINE_CHEAP_MODEL") or CHEAP_DEFAULT
    keys = ("entries",)
    prompt = TEMPLATES[name].format(**{k: kwargs.get(k, "") for k in keys})
    prompt += "\n\nDo not use tools. Do not read files. Reply with the requested text only."
    cmd = [
        agent_bin(),
        "-p",
        "--mode",
        "ask",
        "--model",
        model,
        "--output-format",
        "text",
        prompt,
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or proc.stdout)
        raise SystemExit(proc.returncode)
    return (proc.stdout or "").strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="One-shot prose completion (no tools)")
    ap.add_argument("--template", required=True, choices=sorted(TEMPLATES))
    ap.add_argument("--model", default="")
    ap.add_argument("--entries-file", default="")
    args = ap.parse_args()

    def read(p: str) -> str:
        return Path(p).read_text(encoding="utf-8", errors="replace") if p and Path(p).is_file() else ""

    sys.stdout.write(
        complete(
            args.template,
            model=args.model or None,
            entries=read(args.entries_file),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
