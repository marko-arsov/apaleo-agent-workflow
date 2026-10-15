"""Read-only host discovery. Listing is evidence, never proof of entitlement."""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from .core import PROVIDERS, EFFORTS, fingerprint, validate_route

LIMIT = 2_000_000


def capture(argv, cwd):
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(argv, cwd=cwd, stdout=out, stderr=err)
        try:
            process.wait(timeout=25)
            if process.returncode:
                raise ValueError("Host discovery failed; check sign-in/network and retry")
            if out.tell() > LIMIT:
                raise ValueError("Host discovery output exceeds limit")
            out.seek(0)
            return out.read().decode("utf-8", errors="replace")
        finally:
            if process.poll() is None:
                process.kill(); process.wait()


def cursor_models(text):
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    rows = []
    for line in text.splitlines():
        match = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._:+/-]*)\s+(?:-|–|—)\s+\S", line)
        if match and match[1] not in {"auto", "default"}:
            rows.append({"model": match[1], "status": "advertised"})
    if not rows:
        raise ValueError("Unrecognised Cursor model listing; preserve the previous catalogue")
    return list({r["model"]: r for r in rows}.values())


def codex_models(binary, cwd):
    process = subprocess.Popen([binary, "app-server", "--listen", "stdio://"], cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    messages = queue.Queue(maxsize=128)
    def consume():
        total = 0
        while True:
            line = process.stdout.readline(LIMIT + 1)
            if not line:
                return
            total += len(line)
            if total > LIMIT:
                messages.put({"error": "Discovery output exceeds limit"}); return
            try:
                messages.put(json.loads(line), timeout=1)
            except (ValueError, queue.Full):
                return
    threading.Thread(target=consume, daemon=True).start()
    deadline = time.monotonic() + 25
    def request(ident, method, params):
        process.stdin.write(json.dumps({"id": ident, "method": method, "params": params}) + "\n"); process.stdin.flush()
        while True:
            row = messages.get(timeout=max(.01, deadline - time.monotonic()))
            if row.get("error"):
                raise ValueError("Codex catalogue request failed")
            if row.get("id") == ident:
                return row["result"]
    try:
        request(1, "initialize", {"clientInfo": {"name": "model-policy-discovery", "version": "1.0.0"}})
        process.stdin.write('{"method":"initialized"}\n'); process.stdin.flush()
        result, cursor = [], None
        for ident in range(2, 52):
            params = {"limit": 100, "includeHidden": False}
            if cursor:
                params["cursor"] = cursor
            page = request(ident, "model/list", params)
            for row in page["data"]:
                result.append({"model": row["model"], "status": "advertised", "efforts": [e["reasoningEffort"] for e in row.get("supportedReasoningEfforts", []) if e["reasoningEffort"] in EFFORTS], "default_effort": row.get("defaultReasoningEffort")})
            cursor = page.get("nextCursor")
            if not cursor:
                return result
        raise ValueError("Codex catalogue pagination exceeds limit")
    finally:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
        process.stdin.close(); process.stdout.close()


def claude_models(cwd):
    # Aliases remain unconfirmed: backend, managed policies and subscription access vary.
    aliases = {"opus": "ANTHROPIC_DEFAULT_OPUS_MODEL", "sonnet": "ANTHROPIC_DEFAULT_SONNET_MODEL", "haiku": "ANTHROPIC_DEFAULT_HAIKU_MODEL"}
    paths = [Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))) / "settings.json", Path(cwd) / ".claude/settings.json", Path(cwd) / ".claude/settings.local.json"]
    mapped = {}
    restrictions = []
    for path in paths:
        if path.is_file():
            value = json.loads(path.read_text())
            mapped.update({k: v for k, v in value.get("env", {}).items() if k in aliases.values() and isinstance(v, str)})
            if "availableModels" in value:
                restrictions.append(value["availableModels"])
    mapped.update({key: os.environ[key] for key in aliases.values() if key in os.environ})
    rows = []
    for alias, env in aliases.items():
        model = mapped.get(env, alias)
        validate_route({"provider": "claude", "model": model})
        rows.append({"model": model, "status": "needs-confirmation", "alias": alias, "efforts": ["low", "medium", "high"]})
    return rows, bool(restrictions)


def discover(providers, cwd, previous=None, confirmations=()):
    if not set(providers) <= PROVIDERS:
        raise ValueError("Unsupported providers")
    previous = previous or {}
    result = {"schema_version": 1, "fetched_at": datetime.now(timezone.utc).isoformat(), "providers": {}}
    errors = []
    for provider in sorted(providers):
        binary = shutil.which({"codex": "codex", "cursor": "agent", "claude": "claude"}[provider])
        row = {"installed": bool(binary), "models": []}
        if binary:
            try:
                row["version"] = capture([binary, "--version"], cwd).strip()[:120]
                if provider == "codex":
                    row["models"] = codex_models(binary, cwd)
                elif provider == "cursor":
                    row["models"] = cursor_models(capture([binary, "--list-models"], cwd))
                else:
                    row["models"], row["local_restrictions_present"] = claude_models(cwd)
                    row["notice"] = "Confirm backend, managed restrictions and account access; aliases may change"
                row["observed_at"] = result["fetched_at"]
            except (OSError, ValueError, KeyError, queue.Empty, subprocess.SubprocessError):
                row = previous.get("providers", {}).get(provider, row).copy()
                row["refresh_failed"] = True
                errors.append(provider + ": discovery failed; retained previous evidence")
        row["context_fingerprint"] = fingerprint({"provider": provider, "version": row.get("version"), "models": row.get("models", [])})
        result["providers"][provider] = row
    for confirmation in confirmations:
        provider, sep, model = confirmation.partition(":")
        if not sep or provider not in result["providers"] or not result["providers"][provider]["installed"]:
            raise ValueError("Confirm a model from an installed selected provider")
        validate_route({"provider": provider, "model": model})
        rows = result["providers"][provider]["models"]
        match = next((r for r in rows if r["model"] == model), None)
        if match is None:
            raise ValueError("Refresh must advertise the model before confirming it")
        match["status"] = "confirmed"
    result["errors"] = errors
    return result
