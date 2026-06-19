"""
api.py — a tiny zero-dependency HTTP server for the analytics page.

Serves:
  GET /                      → the static analytics page (web/index.html)
  GET /api/analyze?coin=...  → JSON analytics for the coin
        optional: &symbol=BTC &defillama=<slug> &leverage=10

⛔ Read-only. No execution. No keys required to run. Educational only.

Run:
    python -m crypto_analytics.api            # http://localhost:8787
    PORT=9000 python -m crypto_analytics.api
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .analyzer import analyze, resolve_asset

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet by default
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            index = WEB_DIR / "index.html"
            if index.exists():
                self._send(200, index.read_bytes(), "text/html; charset=utf-8")
            else:
                self._send(404, b"index.html not found", "text/plain")
            return

        if parsed.path == "/api/analyze":
            q = parse_qs(parsed.query)
            coin = (q.get("coin", [""])[0]).strip()
            if not coin:
                self._send(400, json.dumps({"error": "missing 'coin'"}).encode(),
                           "application/json")
                return
            symbol = (q.get("symbol", [None])[0] or None)
            defillama = (q.get("defillama", [None])[0] or None)
            lev = q.get("leverage", [None])[0]
            leverage = float(lev) if lev else None
            try:
                asset = resolve_asset(coin, symbol, defillama)
                state = analyze(asset, intended_leverage=leverage)
                self._send(200, json.dumps(state).encode(), "application/json")
            except Exception as e:  # noqa: BLE001
                self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")
            return

        self._send(404, b"not found", "text/plain")


def main():
    port = int(os.getenv("PORT", "8787"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"crypto-analytics-oss serving on http://localhost:{port}  (EDUCATIONAL ONLY)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
