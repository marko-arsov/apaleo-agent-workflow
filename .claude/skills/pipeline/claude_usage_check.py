#!/usr/bin/env python3
"""Check Claude Code OAuth usage / extra-usage credit headroom.

Uses the same undocumented endpoint Claude Code's /usage command hits:
  GET https://api.anthropic.com/api/oauth/usage

Auth: macOS Keychain "Claude Code-credentials" or ~/.claude/.credentials.json

Exit codes:
  0  enough headroom for a judgment stage on Claude
  1  not enough — caller should fall back to Cursor agent (Grok)
  2  check failed / unavailable (auth, network, parse)

Stdout: one JSON object (machine-readable). Logs go to stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
DEFAULT_MIN_REMAINING_USD = 5.0
DEFAULT_MAX_WINDOW_UTIL = 95.0
CACHE_TTL_SEC = 120


def _eprint(*a: object) -> None:
    print(*a, file=sys.stderr)


def _extract_token(oauth: object) -> tuple[str | None, bool]:
    """Pull the access token out of a `claudeAiOauth` block.

    Returns `(token, saw_blank_field)`. A *present but empty* token field is not the
    same as an absent store: Claude Code blanks both token strings when an OAuth
    session expires and cannot be refreshed, leaving the metadata (`subscriptionType`,
    `scopes`, `refreshTokenExpiresAt`) behind. Reporting that as "no credential store"
    hides the actual state, which `_expiry_note` can usually date precisely.
    """
    if not isinstance(oauth, dict):
        return None, False

    saw_blank = False
    for key in ("accessToken", "access_token"):
        if key not in oauth:
            continue
        value = oauth.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip(), False
        saw_blank = True

    return None, saw_blank


def _expiry_note(oauth: object) -> str:
    """Human-readable expiry suffix for a blanked credential store, or ''.

    Timestamps are epoch milliseconds in practice; tolerate seconds. A blanked store
    whose `refreshTokenExpiresAt` is in the past is the signature of the session that
    the CLI reports as "OAuth session expired and could not be refreshed".
    """
    if not isinstance(oauth, dict):
        return ""

    raw = oauth.get("refreshTokenExpiresAt")
    if not isinstance(raw, (int, float)) or raw <= 0:
        return ""

    seconds = raw / 1000 if raw > 1e11 else float(raw)
    stamp = time.strftime("%Y-%m-%d", time.gmtime(seconds))
    return (
        f" (refresh token expired {stamp})"
        if seconds < time.time()
        else f" (refresh token valid until {stamp})"
    )


def load_oauth_token() -> tuple[str | None, list[str]]:
    """Return `(token, blank_sources)`.

    `blank_sources` names every store that held a `claudeAiOauth` block whose token
    field was present but empty, so the caller can tell "no credential store" apart
    from "session expired and was cleared".
    """
    blank_sources: list[str] = []

    # 1) credentials file (Linux / some installs)
    cred_path = Path.home() / ".claude" / ".credentials.json"
    if cred_path.is_file():
        try:
            data = json.loads(cred_path.read_text(encoding="utf-8"))
            tok, blank = _extract_token(data.get("claudeAiOauth"))
            if tok:
                return tok, blank_sources
            if blank:
                blank_sources.append(
                    f"{cred_path}{_expiry_note(data.get('claudeAiOauth'))}"
                )
        except Exception as exc:  # noqa: BLE001
            _eprint(f"credentials.json read failed: {exc}")

    # 2) macOS keychain (Claude Code default on Darwin)
    if sys.platform == "darwin":
        try:
            user = subprocess.check_output(["whoami"], text=True).strip()
            raw = subprocess.check_output(
                [
                    "security",
                    "find-generic-password",
                    "-a",
                    user,
                    "-s",
                    "Claude Code-credentials",
                    "-w",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            data = json.loads(raw)
            tok, blank = _extract_token(data.get("claudeAiOauth"))
            if tok:
                return tok, blank_sources
            if blank:
                blank_sources.append(
                    "macOS keychain: Claude Code-credentials"
                    + _expiry_note(data.get("claudeAiOauth"))
                )
        except Exception as exc:  # noqa: BLE001
            _eprint(f"keychain read failed: {exc}")

    # 3) env override for CI/testing
    env_tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or os.environ.get(
        "ANTHROPIC_AUTH_TOKEN"
    )
    if env_tok and env_tok.strip():
        return env_tok.strip(), blank_sources

    return None, blank_sources


def fetch_usage(token: str, timeout: float = 20.0) -> dict[str, Any]:
    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "apaleo-claude-usage-check/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _money_from_extra(extra: dict[str, Any] | None) -> tuple[float | None, float | None, float | None]:
    """Return (limit_usd, used_usd, remaining_usd) from extra_usage block."""
    if not extra:
        return None, None, None
    dec = int(extra.get("decimal_places") or 2)
    scale = 10**dec
    limit_raw = extra.get("monthly_limit")
    used_raw = extra.get("used_credits")
    if limit_raw is None or used_raw is None:
        return None, None, None
    # Observed shape: monthly_limit=10000 (cents), used_credits=6956.0 (cents)
    # Also tolerate already-dollar values if limit looks small (< 500 and util matches).
    limit_f = float(limit_raw)
    used_f = float(used_raw)
    util = extra.get("utilization")
    if limit_f >= 500:  # almost certainly minor units (cents)
        limit_usd = limit_f / scale
        used_usd = used_f / scale
    else:
        limit_usd = limit_f
        used_usd = used_f
        # If utilization says ~70% but dollars look like cents already handled above
        if util is not None and limit_usd > 0:
            expected = (used_usd / limit_usd) * 100
            if abs(expected - float(util)) > 5 and limit_f * scale >= 500:
                limit_usd = limit_f / scale
                used_usd = used_f / scale
    return limit_usd, used_usd, max(0.0, limit_usd - used_usd)


def _money_from_spend(spend: dict[str, Any] | None) -> tuple[float | None, float | None, float | None]:
    if not spend:
        return None, None, None
    used = spend.get("used") or {}
    limit = spend.get("limit") or {}
    try:
        used_usd = float(used["amount_minor"]) / (10 ** int(used.get("exponent") or 2))
        limit_usd = float(limit["amount_minor"]) / (10 ** int(limit.get("exponent") or 2))
        return limit_usd, used_usd, max(0.0, limit_usd - used_usd)
    except Exception:  # noqa: BLE001
        return None, None, None


def window_hot(data: dict[str, Any], max_util: float) -> list[str]:
    """Named rate-limit windows that are at/above max_util (%)."""
    hot: list[str] = []
    for key, val in data.items():
        if key in ("extra_usage", "spend", "limits") or not isinstance(val, dict):
            continue
        util = val.get("utilization")
        if util is None:
            continue
        try:
            if float(util) >= max_util:
                hot.append(f"{key}={util}%")
        except (TypeError, ValueError):
            continue
    return hot


def evaluate(
    data: dict[str, Any],
    *,
    min_remaining_usd: float,
    max_window_util: float,
) -> dict[str, Any]:
    extra = data.get("extra_usage") if isinstance(data.get("extra_usage"), dict) else None
    spend = data.get("spend") if isinstance(data.get("spend"), dict) else None

    limit_usd, used_usd, remaining_usd = _money_from_extra(extra)
    if remaining_usd is None:
        limit_usd, used_usd, remaining_usd = _money_from_spend(spend)

    spend_limit_reached = bool(
        (extra or {}).get("spend_limit_reached")
        or (spend or {}).get("severity") == "blocked"
    )
    extra_enabled = True if extra is None else bool(extra.get("is_enabled", True))
    hot = window_hot(data, max_window_util)

    reasons: list[str] = []
    enough = True

    if spend_limit_reached:
        enough = False
        reasons.append("spend_limit_reached")

    if remaining_usd is not None and remaining_usd < min_remaining_usd:
        enough = False
        reasons.append(
            f"remaining_usd={remaining_usd:.2f} < min={min_remaining_usd:.2f}"
        )

    # If plan windows are nearly exhausted and there is no usable extra-usage pool,
    # treat as not enough even when dollar fields are missing.
    if hot:
        if remaining_usd is None or remaining_usd < min_remaining_usd or not extra_enabled:
            enough = False
            reasons.append("rate_windows_hot:" + ",".join(hot))

    if remaining_usd is None and not hot and not spend_limit_reached:
        # Unknown dollar headroom and windows OK/null — allow Claude but flag.
        reasons.append("dollar_headroom_unknown_allowing")

    def _r(x):
        return None if x is None else round(float(x), 2)

    return {
        "enough": enough,
        "remaining_usd": _r(remaining_usd),
        "limit_usd": _r(limit_usd),
        "used_usd": _r(used_usd),
        "min_remaining_usd": min_remaining_usd,
        "extra_usage_enabled": extra_enabled,
        "spend_limit_reached": spend_limit_reached,
        "hot_windows": hot,
        "reasons": reasons,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def read_cache(path: Path, ttl: float) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - float(raw.get("cached_at", 0)) <= ttl:
            return raw.get("result")
    except Exception:  # noqa: BLE001
        return None
    return None


def write_cache(path: Path, result: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"cached_at": time.time(), "result": result}, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        _eprint(f"cache write failed: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--min-remaining-usd",
        type=float,
        default=float(
            os.environ.get(
                "PIPELINE_CLAUDE_MIN_REMAINING_USD", DEFAULT_MIN_REMAINING_USD
            )
        ),
        help="Minimum remaining extra-usage USD to run a judgment stage on Claude",
    )
    ap.add_argument(
        "--max-window-util",
        type=float,
        default=float(
            os.environ.get("PIPELINE_CLAUDE_MAX_WINDOW_UTIL", DEFAULT_MAX_WINDOW_UTIL)
        ),
        help="Treat rate-limit windows at/above this %% as hot",
    )
    ap.add_argument(
        "--cache",
        default=os.environ.get("PIPELINE_CLAUDE_USAGE_CACHE", ""),
        help="Optional cache file path (TTL 120s)",
    )
    ap.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore cache",
    )
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Only print JSON (no human stderr summary)",
    )
    args = ap.parse_args()

    cache_path = Path(args.cache) if args.cache else None
    if cache_path and not args.refresh:
        cached = read_cache(cache_path, CACHE_TTL_SEC)
        if cached is not None:
            print(json.dumps(cached, indent=2))
            if not args.quiet:
                rem = cached.get("remaining_usd")
                rem_s = f"${rem:.2f}" if isinstance(rem, (int, float)) else "?"
                _eprint(
                    f"[claude-usage] cache hit enough={cached.get('enough')} remaining={rem_s}"
                )
            return 0 if cached.get("enough") else 1

    token, blank_sources = load_oauth_token()
    if not token:
        if blank_sources:
            out = {
                "enough": False,
                "error": "empty_oauth_token",
                "blank_sources": blank_sources,
                "hint": (
                    "A credential store was found but its tokens are empty: the OAuth "
                    "session expired and could not be refreshed. Run `claude auth login` "
                    "to restore Claude Code as a usable route, or set "
                    "CLAUDE_CODE_OAUTH_TOKEN. Cursor and Codex routes are unaffected."
                ),
                "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        else:
            out = {
                "enough": False,
                "error": "no_oauth_token",
                "hint": "Sign in with `claude auth login` (subscription OAuth).",
                "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        print(json.dumps(out, indent=2))
        if not args.quiet:
            _eprint(f"[claude-usage] {out['error']}: {out['hint']}")
        return 2

    try:
        data = fetch_usage(token)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        out = {
            "enough": False,
            "error": f"http_{exc.code}",
            "body": body,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        print(json.dumps(out, indent=2))
        return 2
    except Exception as exc:  # noqa: BLE001
        out = {
            "enough": False,
            "error": type(exc).__name__,
            "message": str(exc),
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        print(json.dumps(out, indent=2))
        return 2

    result = evaluate(
        data,
        min_remaining_usd=args.min_remaining_usd,
        max_window_util=args.max_window_util,
    )
    if cache_path:
        write_cache(cache_path, result)

    print(json.dumps(result, indent=2))
    if not args.quiet:
        rem = result.get("remaining_usd")
        rem_s = f"${rem:.2f}" if isinstance(rem, (int, float)) else "?"
        lim = result.get("limit_usd")
        lim_s = f"${lim:.2f}" if isinstance(lim, (int, float)) else "?"
        _eprint(
            f"[claude-usage] enough={result['enough']} remaining={rem_s}/{lim_s} "
            f"reasons={result.get('reasons')}"
        )
    return 0 if result["enough"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
