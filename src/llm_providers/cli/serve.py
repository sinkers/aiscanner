"""Simple HTTP server for the webapp, serving from repo root so data/ is reachable."""

import http.server
import socketserver
import webbrowser

from llm_providers import config

PORT = 8000


def main() -> None:
    # Serve from repo root so that both webapp/ and data/ are accessible
    import os
    os.chdir(config.REPO_ROOT)

    handler = http.server.SimpleHTTPRequestHandler
    handler.extensions_map.update({
        ".js": "application/javascript",
        ".json": "application/json",
    })

    print("=" * 70)
    print("OpenRouter Infrastructure Provider Map — Dev Server")
    print("=" * 70)
    print(f"\nServer:    http://localhost:{PORT}")
    print(f"Open:      http://localhost:{PORT}/webapp/index.html")
    print("\nPress Ctrl+C to stop\n" + "=" * 70)

    try:
        webbrowser.open(f"http://localhost:{PORT}/webapp/index.html")
    except Exception:
        pass

    with socketserver.TCPServer(("", PORT), handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\nServer stopped")


if __name__ == "__main__":
    main()
