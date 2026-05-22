"""Local dev server that mirrors the S3/CloudFront layout.

In production, HTML sits at the bucket root and assets at data/ and rollups/.
To replicate this locally we serve webapp/ as root, then fall back to repo
root for any path not found there (covers data/, rollups/, snapshots/).

  http://localhost:8000/llm.html          → webapp/llm.html
  http://localhost:8000/data/infra.json   → data/infrastructure_provider_map.json
  http://localhost:8000/rollups/...       → (404 expected unless you have a local rollup)
"""

import http.server
import socketserver
import urllib.parse
import webbrowser
from pathlib import Path

from llm_providers import config

PORT = 8000
REPO_ROOT = config.REPO_ROOT
WEBAPP_DIR = config.WEBAPP_DIR


class _Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "application/javascript",
        ".json": "application/json",
    }

    def translate_path(self, path: str) -> str:
        path = urllib.parse.unquote(path.split("?", 1)[0].split("#", 1)[0])
        rel = path.lstrip("/") or "index.html"

        # 1. Try webapp/ first (HTML, JS, CSS)
        candidate = WEBAPP_DIR / rel
        if candidate.exists():
            return str(candidate)

        # 2. Fall back to repo root (data/, rollups/, snapshots/, etc.)
        return str(REPO_ROOT / rel)

    def log_message(self, fmt: str, *args) -> None:
        # Suppress expected 404s for rollups (not present locally)
        if args and str(args[1]) == "404" and "/rollups/" in str(args[0]):
            return
        super().log_message(fmt, *args)


def main() -> None:
    print("=" * 70)
    print("OpenRouter Infrastructure Provider Map — Dev Server")
    print("=" * 70)
    print(f"\nServer:  http://localhost:{PORT}")
    print(f"Open:    http://localhost:{PORT}/llm.html")
    print("\nPress Ctrl+C to stop\n" + "=" * 70)

    try:
        webbrowser.open(f"http://localhost:{PORT}/llm.html")
    except Exception:
        pass

    with socketserver.TCPServer(("", PORT), _Handler) as httpd:
        httpd.allow_reuse_address = True
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\nServer stopped")


if __name__ == "__main__":
    main()
