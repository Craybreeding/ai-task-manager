#!/usr/bin/env python3
"""
AI Captain Server
- Serves static files from dist/
- /api/sync — runs auto_sync_projects.py to pull latest from GitHub
"""
import json
import subprocess
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
DATA_FILE = ROOT / "public" / "data.json"
SYNC_SCRIPT = ROOT / "scripts" / "auto_sync_projects.py"

PORT = 4174


class CaptainHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/sync":
            self._handle_sync()
        else:
            self.send_error(404)

    def do_GET(self):
        path = urlparse(self.path).path

        # API routes
        if path == "/api/sync":
            self._handle_sync()
            return

        # SPA fallback: serve index.html for non-file paths
        file_path = DIST / path.lstrip("/")
        if not file_path.exists() or file_path.is_dir():
            if not path.startswith("/api") and "." not in path.split("/")[-1]:
                self.path = "/index.html"

        super().do_GET()

    def _handle_sync(self):
        """Run auto_sync_projects.py and return updated data."""
        self.send_header_cors()

        try:
            # Run sync: --write --with-issues
            cmd = [
                sys.executable, str(SYNC_SCRIPT),
                "--write", "--with-issues",
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                cwd=str(ROOT),
            )

            if result.returncode != 0:
                self._json_response(500, {
                    "ok": False,
                    "error": result.stderr[-500:] if result.stderr else "sync failed",
                })
                return

            # Read the updated data.json
            if DATA_FILE.exists():
                data = json.loads(DATA_FILE.read_text())
                # Also copy to dist/ for static serving
                (DIST / "data.json").write_text(DATA_FILE.read_text())
                self._json_response(200, {
                    "ok": True,
                    "projects": len(data.get("projects", [])),
                    "tasks": len(data.get("tasks", [])),
                    "conditions": len(data.get("conditions", [])),
                    "log": result.stdout[-1000:] if result.stdout else "",
                    "data": data,
                })
            else:
                self._json_response(500, {"ok": False, "error": "data.json not found after sync"})

        except subprocess.TimeoutExpired:
            self._json_response(504, {"ok": False, "error": "sync timed out (120s)"})
        except Exception as e:
            self._json_response(500, {"ok": False, "error": str(e)})

    def send_header_cors(self):
        """Allow CORS for dev."""
        pass  # Headers set in _json_response

    def _json_response(self, code: int, body: dict):
        payload = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(payload))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        # Quieter logging
        if "/api/" in str(args[0]) if args else False:
            super().log_message(format, *args)


def main():
    if not DIST.exists():
        print(f"Error: {DIST} not found. Run 'npm run build' first.")
        sys.exit(1)

    server = HTTPServer(("0.0.0.0", PORT), CaptainHandler)
    print(f"🚀 AI Captain serving on http://localhost:{PORT}")
    print(f"   Static: {DIST}")
    print(f"   Sync:   POST /api/sync")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")


if __name__ == "__main__":
    main()
