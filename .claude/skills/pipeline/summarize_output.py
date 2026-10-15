#!/usr/bin/env python3
"""Shrink red build/test/Jenkins logs before they reach a model.

Full log stays on disk; stdout is the capped summary + a one-line totals tail.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from untrusted_input import sanitize, wrap_data

MAX_DOTNET_BUILD = 40
MAX_DOTNET_FAIL = 25
MAX_JEST_FAIL = 25
STACK_LINES = 8


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it in seen:
            continue
        seen.add(it)
        out.append(it)
    return out


def _dotnet_totals(text: str) -> str:
    err = wrn = 0
    m = re.search(r"(\d+)\s+Error\(s\)", text, re.I)
    if m:
        err = int(m.group(1))
    m = re.search(r"(\d+)\s+Warning\(s\)", text, re.I)
    if m:
        wrn = int(m.group(1))
    passed = failed = skipped = None
    m = re.search(r"Failed:\s*(\d+).*Passed:\s*(\d+).*Skipped:\s*(\d+)", text, re.I | re.S)
    if m:
        failed, passed, skipped = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return (
        f"passed={passed} failed={failed} skipped={skipped} errors={err} warnings={wrn}"
        if passed is not None
        else f"errors={err} warnings={wrn}"
    )


def summarize_dotnet_build(text: str) -> tuple[list[str], str]:
    hits: list[str] = []
    pat = re.compile(
        r"^(.+?)\((\d+)(?:,\d+)?\):\s+(error|warning)\s+([A-Z]{2}\d+)\s*:\s*(.+)$",
        re.I | re.M,
    )
    for m in pat.finditer(text):
        path, line, _kind, code, msg = m.groups()
        hits.append(f"{path}:{line}: {code} {msg.strip()}")
    for m in re.finditer(r"^(error|warning)\s+([A-Z]{2}\d+)\s*:\s*(.+)$", text, re.I | re.M):
        hits.append(f"{m.group(2)} {m.group(3).strip()}")
    return _dedupe(hits)[:MAX_DOTNET_BUILD], _dotnet_totals(text)


def summarize_dotnet_test(text: str) -> tuple[list[str], str, int]:
    blocks: list[str] = []
    chunks = re.split(r"(?=^\s*Failed\s+)", text, flags=re.M)
    for chunk in chunks:
        m = re.match(r"\s*Failed\s+(.+)", chunk)
        if not m:
            continue
        fq = m.group(1).split("\n", 1)[0].strip()
        msg_m = re.search(r"(Error Message|Assert[\w.]*Exception|Xunit\.Sdk\.\w+):\s*(.+)", chunk)
        msg = (msg_m.group(2).strip() if msg_m else "").split("\n", 1)[0]
        if not msg:
            am = re.search(r"^\s*(Expected[\s\S]{0,400}?Actual.+)$", chunk, re.M)
            msg = am.group(1).strip()[:400] if am else "(no assertion message)"
        stack: list[str] = []
        for sm in re.finditer(r"^\s+at (\S+) in (.+):line (\d+)\s*$", chunk, re.M):
            loc = sm.group(2)
            if "nuget" in loc.lower() or "xunit" in loc.lower():
                continue
            stack.append(f"    at {sm.group(1)} in {loc}:{sm.group(3)}")
            if len(stack) >= STACK_LINES:
                break
        blocks.append(f"{fq}\n  {msg}\n" + ("\n".join(stack) if stack else "  (no repo frames)"))
    if not blocks:
        names = [m.group(1).strip() for m in re.finditer(r"^\s*(?:Failed\s+|\[FAIL\]\s+)(.+)$", text, re.M)]
        blocks = _dedupe(names)
    extra = max(0, len(blocks) - MAX_DOTNET_FAIL)
    return blocks[:MAX_DOTNET_FAIL], _dotnet_totals(text), extra


def summarize_jest(text: str) -> tuple[list[str], str, int]:
    blocks: list[str] = []
    fail_files = re.findall(r"^FAIL\s+(\S+)", text, re.M)
    parts = re.split(r"(?=^FAIL\s+)", text, flags=re.M)
    for part in parts:
        fm = re.match(r"FAIL\s+(\S+)", part)
        if not fm:
            continue
        spec = fm.group(1)
        for tm in re.finditer(r"^\s*●\s+(.+)$", part, re.M):
            name = tm.group(1).strip()
            rest = part[tm.end() :]
            nxt = re.search(r"^\s*●\s+", rest, re.M)
            body = rest[: nxt.start() if nxt else None]
            diff_lines: list[str] = []
            for ln in body.splitlines():
                if re.match(r"^\s*(Expected|Received|Difference|[-+>]\s)", ln) or "expect(" in ln:
                    diff_lines.append(ln.rstrip())
                if re.match(r"^\s+at\s+", ln) and "node_modules" not in ln:
                    diff_lines.append(ln.rstrip())
                if len(diff_lines) >= STACK_LINES:
                    break
            diff = "\n".join(diff_lines) if diff_lines else "(no assertion diff captured)"
            blocks.append(f"{spec}\n  {name}\n{diff}")
    extra = max(0, len(blocks) - MAX_JEST_FAIL)
    suites_f = tests_f = tests_p = tests_s = 0
    m = re.search(r"Test Suites:\s+(\d+)\s+failed", text)
    if m:
        suites_f = int(m.group(1))
    m = re.search(r"Tests:\s+(\d+)\s+failed.*?(\d+)\s+passed", text)
    if m:
        tests_f, tests_p = int(m.group(1)), int(m.group(2))
    m = re.search(r"Tests:.*?(\d+)\s+skipped", text)
    if m:
        tests_s = int(m.group(1))
    totals = (
        f"passed={tests_p} failed={tests_f} skipped={tests_s} "
        f"suites_failed={suites_f} fail_files={len(set(fail_files))}"
    )
    return blocks[:MAX_JEST_FAIL], totals, extra


def summarize_jenkins(text: str) -> tuple[list[str], str]:
    markers = (
        r"FAILED:",
        r"\[ERROR\]",
        r"error CS",
        r"Tests failed",
        r"npm ERR!",
        r"FAILURE",
        r"Build step .* marked build as failure",
    )
    idx = None
    for pat in markers:
        m = re.search(pat, text, re.I)
        if m:
            idx = m.start()
            break
    if idx is None:
        tail = text[-4000:]
        return [tail], f"no failure marker; tail_chars={len(tail)}"
    start = max(0, idx - 2500)
    end = min(len(text), idx + 6000)
    return text[start:end].splitlines()[:120], f"window_chars={end - start} from_offset={start}"


def render(mode: str, text: str, logfile: Path) -> str:
    sanitized = sanitize(text)
    text = sanitized.text
    extra = 0
    if mode == "dotnet-build":
        hits, totals = summarize_dotnet_build(text)
        body = "\n".join(hits) if hits else "(no errors/warnings parsed)"
    elif mode == "dotnet-test":
        hits, totals, extra = summarize_dotnet_test(text)
        body = "\n\n".join(hits) if hits else "(no failing tests parsed)"
        if extra:
            body += f"\n… {extra} more failures (see {logfile})"
    elif mode == "jest":
        hits, totals, extra = summarize_jest(text)
        body = "\n\n".join(hits) if hits else "(no failing tests parsed)"
        if extra:
            body += f"\n… {extra} more failures (see {logfile})"
    elif mode == "jenkins":
        hits, totals = summarize_jenkins(text)
        body = "\n".join(hits)
    else:
        raise SystemExit(f"unknown mode {mode}")
    rendered = body.rstrip() + f"\ntotals: {totals}  log={logfile}"
    warning = ""
    if sanitized.flags:
        warning = (
            "UNTRUSTED_INPUT_CONFIRMATION_REQUIRED: injection-shaped steering was detected "
            "in this external log.\n"
        )
    return warning + wrap_data(rendered, f"{mode} log summary") + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize red build/test/Jenkins logs for models")
    ap.add_argument("--mode", required=True, choices=("dotnet-build", "dotnet-test", "jest", "jenkins"))
    ap.add_argument("logfile", nargs="?", help="path to full log (stdin if omitted)")
    ap.add_argument("--stdin", action="store_true")
    args = ap.parse_args()
    if args.stdin or not args.logfile:
        text = sys.stdin.read()
        logfile = Path("<stdin>")
    else:
        logfile = Path(args.logfile)
        text = logfile.read_text(encoding="utf-8", errors="replace")
    sys.stdout.write(render(args.mode, text, logfile))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
