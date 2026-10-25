"""Serve the demo's fragmented systems as independent JSON APIs (stdlib only).

  /api/wms/inventory  /api/wms/inbound  /api/suppliers/reliability  /api/channels/economics  /api/rules/skus
  /api/amazon/orders  (Amazon seller orders - written by demo/server.py)  /health

Run: python demo/mock_apis.py [port]   (default 8901; containers reach it at host.docker.internal)
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
ROUTES = {
    "/api/wms/inventory": "wms_inventory.json",
    "/api/wms/inbound": "wms_inbound.json",
    "/api/suppliers/reliability": "supplier_reliability.json",
    "/api/channels/economics": "channel_economics.json",
    "/api/rules/skus": "sku_rules.json",
    "/api/amazon/orders": "amazon_orders.json",
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            return self._send(200, {"status": "ok", "apis": sorted(ROUTES)})
        if name := ROUTES.get(self.path):
            return self._send(200, json.loads((DATA / name).read_text()))
        self._send(404, {"error": f"unknown endpoint {self.path}"})

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8901
    print(f"mock channel APIs on http://0.0.0.0:{port}")
    for route in sorted(ROUTES):
        print(f"  {route}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
