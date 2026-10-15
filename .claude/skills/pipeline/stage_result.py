#!/usr/bin/env python3
"""Classify one headless pipeline stage result for implement-pipeline.

Reads the engine's JSON output, the extracted result text, and stderr, then writes
shell-sourceable `P_*` assignments.

Outcomes (priority order): blocked > skipped > continue > transient > error > ok.
See ../references/pipeline-autonomy.md for what each one makes the runner do.

Usage: stage_result.py <out.json> <out.txt> <stderr|-> <out.env>
"""
from __future__ import annotations

import json
import re
import sys

PERMANENT_PROVIDER = re.compile(
    r"(you(?:'|’)ve hit your individual spend limit|individual spend limit|"
    r"usage[- ]credits?[^.\n]{0,80}(?:admin|higher limit)|insufficient (?:quota|credits?)|"
    r"credit balance is too low|billing hard limit|account[^.\n]{0,40}(?:suspended|disabled)|"
    r"invalid api key|authentication failed|failed to authenticate|"
    r"oauth session expired|could not be refreshed|unauthenticated|"
    r"unauthorized[^.\n]{0,40}(?:api|provider)|"
    r"unknown model|invalid model|"
    r"(?:model|deployment)[^.\n]{0,80}?(?:not found|does not exist|is unavailable))",
    re.I,
)

PROVIDER_STALL = re.compile(
    r"(repeated resume attempts made no progress|agent turn stopped.*no progress|"
    r"reconnect(?:ion)? loop|stream repeatedly disconnected)",
    re.I,
)

TRANSIENT = re.compile(
    r"(overloaded|rate[_ -]?limit|too many requests|"
    r"\bHTTP(?:/\d(?:\.\d)?)?\s+(?:429|500|502|503|529)\b|"
    r"\b(?:429|500|502|503|529)\b\s+(?:too many requests|internal server error|bad gateway|service unavailable)|"
    r"\b(?:status|error)(?:\s+code)?\s*[:=]?\s*(?:429|500|502|503|529)\b|"
    r"api_error_status[\"']?\s*[:=]\s*(?:429|500|502|503|529)\b|"
    r"service unavailable|internal server error|econnreset|etimedout|eai_again|"
    r"socket hang up|connection (?:error|reset|closed)|stream (?:error|closed|disconnected)|"
    r"premature close|network error|usage limit reached|"
    r"upstream connect error|fetch failed|model overloaded|please try again)",
    re.I,
)


def classify_failure(haystack: str) -> tuple[str, str]:
    """Return provider failure class and a concise matching reason.

    permanent_provider opens a run-level circuit and is never retried.  Stall
    and transient failures may be retried once in a fresh session.  Semantic
    means the agent completed but the stage contract was not met.
    """
    match = PERMANENT_PROVIDER.search(haystack)
    if match:
        return "permanent_provider", match.group(0)[:240]
    match = PROVIDER_STALL.search(haystack)
    if match:
        return "provider_stall", match.group(0)[:240]
    match = TRANSIENT.search(haystack)
    if match:
        return "transient_provider", match.group(0)[:240]
    return "semantic", ""


def health_failure_reason(raw: str, matched: str, returncode: int) -> str:
    """Prefer a structured provider error over a mid-JSON tail slice."""
    data = load_json(raw)
    result = data.get("result")
    if isinstance(result, str) and result.strip() and "ready" not in result.strip().lower():
        return result.strip()[:400]
    if matched:
        return matched[:400]
    blob = raw.strip()
    if blob:
        return blob[-400:]
    return f"exit {returncode}"


def read(path: str) -> str:
    if not path or path == "-":
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def load_json(raw: str) -> dict:
    raw = raw.strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        data = {}
        for line in reversed(raw.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                break
            except ValueError:
                continue
    return data if isinstance(data, dict) else {}


def sh_quote(value) -> str:
    return "'" + str(value).replace("'", "'\\''") + "'"


VALID_OUTCOMES = {"ok", "skipped", "blocked", "error", "continue"}


def last_terminal_line(blob: str, marker: str) -> re.Match[str] | None:
    """Return the stage-contract marker, not a mention of its name.

    A marker counts when it starts a line, or when it is the final token of the
    blob after the previous sentence. A quoted example with trailing text does not.
    """
    match = None
    pattern = re.compile(rf"(?m)^\s*{re.escape(marker)}\b.*$")
    for match in pattern.finditer(blob):
        pass
    if match:
        return match
    return re.search(
        rf"(?:^|\n|[.!?]\s*|\s){re.escape(marker)}\b[^\n`]*$",
        blob.rstrip(),
    )


def provider_diagnostic_text(data: dict, err: str, watchdog: str = "") -> str:
    """Return provider-error text, excluding prompts and assistant transcripts.

    Transcripts quote application HTTP 500s and instruction text such as
    "model names". Those are not provider outages.
    """
    parts = [err or "", watchdog or ""]
    failed = (
        bool(data.get("is_error"))
        or data.get("subtype") == "error"
        or bool(data.get("api_error_status"))
    )
    if failed:
        parts.append(str(data.get("result") or ""))
        status = data.get("api_error_status")
        if status:
            parts.append(f"api_error_status={status}")
    return "\n".join(part for part in parts if part)


def blocked_questions(blob: str, marker: re.Match[str]) -> str:
    """Extract numbered questions whether emitted before or after the marker."""
    candidates: list[str] = []
    after = blob[marker.end():]
    before = blob[: marker.start()]
    for section in (after, "\n".join(before.splitlines()[-12:])):
        questions = [
            line.strip()
            for line in section.splitlines()
            if re.match(r"^\d+[.)]\s+", line.strip())
        ]
        if questions:
            candidates = questions[:6]
            break
    inline = marker.group(0).split(":", 1)[1].strip() if ":" in marker.group(0) else ""
    if candidates:
        return "; ".join(candidates)[:800]
    return inline[:800] or "agent emitted PIPELINE_BLOCKED without a concrete question"


def structured_outcome(blob: str) -> tuple[str, str] | None:
    """Honor an explicit `PIPELINE_RESULT {json}` tail when the stage emits one."""
    match = None
    for match in re.finditer(r"PIPELINE_RESULT\s*(\{.*?\})\s*$", blob, re.M | re.S):
        pass  # keep the last one
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    outcome = str(payload.get("outcome") or "").strip().lower()
    if outcome not in VALID_OUTCOMES:
        return None
    reason = str(payload.get("reason") or payload.get("notes") or "")
    return outcome, reason[:400]


def classify(data: dict, blob: str, err: str) -> tuple[str, str]:
    is_err = (
        bool(data.get("is_error"))
        or data.get("subtype") == "error"
        or bool(data.get("api_error_status"))
    )
    blocked = last_terminal_line(blob, "PIPELINE_INPUT_REQUIRED")
    if not blocked:
        blocked = last_terminal_line(blob, "PIPELINE_BLOCKED")
    if blocked:
        return "blocked", blocked_questions(blob, blocked)
    structured = structured_outcome(blob)
    if structured:
        return structured
    skipped = last_terminal_line(blob, "PIPELINE_STAGE_SKIPPED")
    if skipped:
        match = re.search(r"PIPELINE_STAGE_SKIPPED:\s*\S*\s*(?:reason=)?(.*)", skipped.group(0))
        reason = (match.group(1).strip() if match else "")[:400]
        return "skipped", reason or "agent emitted PIPELINE_STAGE_SKIPPED"
    cont = last_terminal_line(blob, "PIPELINE_BUGBOT_CONTINUE")
    if cont:
        match = re.search(r"PIPELINE_BUGBOT_CONTINUE:\s*(.*)", cont.group(0))
        reason = (match.group(1).strip() if match else "")[:400]
        return "continue", reason or "agent emitted PIPELINE_BUGBOT_CONTINUE"
    if not blob.strip():
        return "transient", "engine produced no output"
    if last_terminal_line(blob, "PIPELINE_STAGE_OK"):
        return "ok", ""
    haystack = blob + "\n" + err
    try:
        haystack += "\n" + json.dumps(data, default=str)
    except (TypeError, ValueError):
        pass
    failure_class, failure_reason = classify_failure(haystack)
    if failure_class in {"transient_provider", "provider_stall"}:
        return "transient", failure_reason
    if failure_class == "permanent_provider":
        return "error", failure_reason
    if is_err:
        detail = data.get("api_error_status") or data.get("subtype") or "engine reported error"
        return "error", str(detail)[:200]
    return "error", "no PIPELINE_STAGE_OK terminal line"


def main() -> int:
    if len(sys.argv) < 5:
        print(__doc__, file=sys.stderr)
        return 64
    json_file, text_file, err_file, out_file = sys.argv[1:5]
    data = load_json(read(json_file))
    result = str(data.get("result") or "")
    blob = read(text_file) + "\n" + result
    err = read(err_file)

    outcome, reason = classify(data, blob, err)
    haystack = blob + "\n" + err
    try:
        haystack += "\n" + json.dumps(data, default=str)
    except (TypeError, ValueError):
        pass
    failure_class, matched_reason = classify_failure(haystack)
    if outcome in {"ok", "blocked", "skipped", "continue"}:
        failure_class = "stage_contract"
    elif failure_class == "semantic" and outcome == "transient":
        failure_class = "transient_provider"
    fields = {
        "P_OUTCOME": outcome,
        "P_REASON": reason.replace("\n", " ").strip(),
        "P_FAILURE_CLASS": failure_class,
        # blob repeats the result text (file + JSON), so count distinct lines
        "P_DECISIONS": len({m.strip() for m in re.findall(r"^\s*PIPELINE_DECISION:.*$", blob, re.M)}),
        "P_COST_USD": data.get("total_cost_usd") or data.get("cost_usd") or "",
        "P_DURATION_MS": data.get("duration_ms") or "",
        "P_TURNS": data.get("num_turns") or "",
    }
    with open(out_file, "w", encoding="utf-8") as fh:
        for key, value in fields.items():
            fh.write(f"{key}={sh_quote(value)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
