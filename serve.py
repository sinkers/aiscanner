#!/usr/bin/env python3
"""
Simple HTTP server to view the infrastructure provider map web UI
"""

import http.server
import socketserver
import webbrowser
import os

PORT = 8000

os.chdir(os.path.dirname(os.path.abspath(__file__)))

Handler = http.server.SimpleHTTPRequestHandler
Handler.extensions_map.update({
    '.js': 'application/javascript',
    '.json': 'application/json',
})

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print("="*80)
    print("🌐 OpenRouter Infrastructure Provider Map - Web Server")
    print("="*80)
    print(f"\n✅ Server running at: http://localhost:{PORT}")
    print(f"📊 Open this URL in your browser: http://localhost:{PORT}/index.html")
    print("\n💡 Press Ctrl+C to stop the server\n")
    print("="*80)

    # Try to open browser automatically
    try:
        webbrowser.open(f'http://localhost:{PORT}/index.html')
        print("✅ Browser opened automatically")
    except:
        print("⚠️  Could not open browser automatically - please open the URL manually")

    print("\n🔄 Server is running...\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped")
