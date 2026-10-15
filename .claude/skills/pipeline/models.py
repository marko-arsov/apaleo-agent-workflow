#!/usr/bin/env python3
"""Small provider-output helpers used by the implementation pipeline."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path


CHEAP_DEFAULT = os.environ.get("PIPELINE_CHEAP_MODEL", "composer-2.5-fast")


def parse_stream_json(path: Path) -> dict[str, str]:
    """Extract common model/session/result fields from Cursor or Claude NDJSON."""
    out = {
        "model_actual": "",
        "input_tokens": "",
        "cached_input_tokens": "",
        "output_tokens": "",
        "turns": "",
        "cost_usd": "",
        "session_id": "",
        "result_text": "",
    }
    if not path.is_file():
        return out
    text = path.read_text(encoding="utf-8", errors="replace")
    events: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    if not events:
        try:
            value = json.loads(text)
            events = [value] if isinstance(value, dict) else [v for v in value if isinstance(v, dict)]
        except (json.JSONDecodeError, TypeError):
            pass

    def usage(event: dict) -> None:
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        values = event.get("usage") or message.get("usage") or {}
        if not isinstance(values, dict):
            return
        mapping = {
            "input_tokens": ("input_tokens", "prompt_tokens", "inputTokens"),
            "cached_input_tokens": (
                "cache_read_input_tokens",
                "cached_input_tokens",
                "cacheReadInputTokens",
            ),
            "output_tokens": ("output_tokens", "completion_tokens", "outputTokens"),
        }
        for target, sources in mapping.items():
            for source in sources:
                if values.get(source) is not None:
                    out[target] = str(values[source])
                    break
        cost = event.get("total_cost_usd") or event.get("cost_usd") or values.get("cost_usd")
        if cost is not None:
            out["cost_usd"] = str(cost)

    for event in events:
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        model = event.get("model") or event.get("model_id") or message.get("model")
        if model:
            out["model_actual"] = out["model_actual"] or str(model)
        session = event.get("session_id") or event.get("sessionId") or event.get("thread_id")
        if not session and isinstance(event.get("thread"), dict):
            session = event["thread"].get("id")
        if session:
            out["session_id"] = str(session)
        event_type = str(event.get("type") or event.get("event") or "")
        subtype = str(event.get("subtype") or event.get("subType") or "")
        if event_type == "result" or subtype == "result":
            result = event.get("result")
            if isinstance(result, str):
                out["result_text"] = result
            turns = event.get("num_turns") or event.get("turns") or event.get("duration_turns")
            if turns is not None:
                out["turns"] = str(turns)
        usage(event)

    if not out["result_text"]:
        for event in reversed(events):
            message = event.get("message") or event.get("result")
            if isinstance(message, str) and message.strip():
                out["result_text"] = message
                break
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                out["result_text"] = content
                break
            if isinstance(content, list):
                parts = [str(item["text"]) for item in content if isinstance(item, dict) and item.get("text")]
                if parts:
                    out["result_text"] = "\n".join(parts)
                    break
    return out


_NOISE_TOKEN = re.compile(r"^(?:thinking|\d+[km])$", re.I)


def _canon_model(name: str) -> str:
    value = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", name)
    value = re.sub(r"[\s_]+", "-", value.strip().lower())
    # Cursor ids spell versions with dashes (claude-opus-5-5-high); display names use dots (Opus 5.5).
    value = re.sub(r"(?<=\d)\.(?=\d)", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    tokens = [token for token in value.split("-") if token and not _NOISE_TOKEN.match(token)]
    return "-".join(tokens)


def models_match(expected: str, actual: str) -> bool:
    """Compare route slugs with provider display names and aliases.

    Cursor CLI ids keep ``thinking`` and omit the context window, while stream
    initialization reports display names such as ``Claude Sonnet 5 300K High``
    or ``GPT-5.6 Sol 272K High``. Those extra tokens are not a different model.
    Zero-width characters in a display name are ignored. Effort/tier tokens such as
    ``high`` and ``medium`` are still compared.
    """
    expected_c = _canon_model(expected)
    actual_c = _canon_model(actual)
    if not expected_c or not actual_c:
        return False
    variants = {
        expected_c,
        expected_c.removeprefix("cursor-"),
        expected_c.removeprefix("claude-"),
    }
    actual_variants = {
        actual_c,
        actual_c.removeprefix("cursor-"),
        actual_c.removeprefix("claude-"),
    }
    return any(
        left == right or left in right or right.startswith(left)
        for left in variants
        for right in actual_variants
        if left and right
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stream", type=Path)
    args = parser.parse_args()
    print(json.dumps(parse_stream_json(args.stream)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
