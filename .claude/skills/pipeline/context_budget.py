#!/usr/bin/env python3
"""Context-size budget. Loud warning, not a hard stop.

Limits:
  AGENTS.md                 ≤ 6 KB
  any SKILL.md              ≤ 200 lines
  any references/*.md       ≤ 300 lines
  WORKFLOW.md               ≤ 600 lines
  README-apaleo-pipeline.md ≤ 200 lines
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import find_root, skills_dir

LIMITS = {
    "AGENTS.md": ("bytes", 6 * 1024),
    "SKILL.md": ("lines", 200),
    "references": ("lines", 300),
    "WORKFLOW.md": ("lines", 600),
    "README-apaleo-pipeline.md": ("lines", 200),
}


def _lines(p: Path) -> int:
    return len(p.read_text(encoding="utf-8", errors="replace").splitlines())


def check(root: Path | None = None) -> list[str]:
    root = root or find_root()
    skills = skills_dir(root)
    warnings: list[str] = []

    agents = root / "AGENTS.md"
    if agents.is_file():
        n = agents.stat().st_size
        lim = LIMITS["AGENTS.md"][1]
        status = "OK" if n <= lim else "OVER"
        print(f"{status:4} AGENTS.md  {n} bytes  (limit {lim})")
        if n > lim:
            warnings.append(f"AGENTS.md {n} bytes > {lim}")

    wf = skills / "WORKFLOW.md"
    if wf.is_file():
        n = _lines(wf)
        lim = LIMITS["WORKFLOW.md"][1]
        status = "OK" if n <= lim else "OVER"
        print(f"{status:4} WORKFLOW.md  {n} lines  (limit {lim})")
        if n > lim:
            warnings.append(f"WORKFLOW.md {n} lines > {lim}")

    readme = skills / "README-apaleo-pipeline.md"
    if readme.is_file():
        n = _lines(readme)
        lim = LIMITS["README-apaleo-pipeline.md"][1]
        status = "OK" if n <= lim else "OVER"
        print(f"{status:4} README-apaleo-pipeline.md  {n} lines  (limit {lim})")
        if n > lim:
            warnings.append(f"README {n} lines > {lim}")

    for skill in sorted(skills.glob("*/SKILL.md")):
        n = _lines(skill)
        lim = LIMITS["SKILL.md"][1]
        rel = skill.relative_to(skills)
        status = "OK" if n <= lim else "OVER"
        if n > lim:
            print(f"{status:4} {rel}  {n} lines  (limit {lim})")
            warnings.append(f"{rel} {n} lines > {lim}")

    refs = skills / "references"
    if refs.is_dir():
        for md in sorted(refs.glob("*.md")):
            n = _lines(md)
            lim = LIMITS["references"][1]
            status = "OK" if n <= lim else "OVER"
            if n > lim:
                print(f"{status:4} references/{md.name}  {n} lines  (limit {lim})")
                warnings.append(f"references/{md.name} {n} lines > {lim}")

    if not warnings:
        print("context budget: all files within limits")
    else:
        print(f"context budget: {len(warnings)} OVER (warning, not a hard stop)", file=sys.stderr)
    return warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="Check pipeline markdown against size budgets")
    ap.add_argument("--root", default="")
    args = ap.parse_args()
    root = Path(args.root) if args.root else find_root()
    check(root)
    return 0  # warnings are not failures


if __name__ == "__main__":
    raise SystemExit(main())
