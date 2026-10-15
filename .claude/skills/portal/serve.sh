#!/usr/bin/env bash
# Local portal server with refresh endpoint (regenerates index.html).
#   ./serve.sh          # http://127.0.0.1:8765/
# Refresh button calls POST /api/refresh
set -euo pipefail
PORT="${PORTAL_PORT:-8765}"
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
exec python3 - "$PORT" <<'PY'
import json, subprocess, sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(sys.argv[1])
ROOT = Path.cwd()
GEN = ROOT / "generate.py"

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):
        if self.path.rstrip("/") == "/api/refresh":
            try:
                r = subprocess.run(
                    [sys.executable, str(GEN)],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                body = json.dumps({
                    "ok": r.returncode == 0,
                    "stdout": (r.stdout or "").strip(),
                    "stderr": (r.stderr or "").strip(),
                }).encode()
                self.send_response(200 if r.returncode == 0 else 500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                body = json.dumps({"ok": False, "error": str(e)}).encode()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, fmt, *args):
        sys.stderr.write("[portal] " + (fmt % args) + "\n")

print(f"Apaleo Pipeline Portal  http://127.0.0.1:{PORT}/", flush=True)
print("Refresh button regenerates from skills + ai-plans + pipeline-state", flush=True)
ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
PY
