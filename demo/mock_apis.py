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

# Decimal fields, always sent as JSON floats. Zetaris fixes a REST table's column types when the source is
# registered; a whole number in a decimal column (e.g. "v7": 3 next to "v7": 2.5) then fails the whole query
# with "ClassCastException: java.lang.Long cannot be cast to java.lang.Double".
FLOAT_FIELDS = {
    "/api/wms/inventory": ("age_hours",),
    "/api/suppliers/reliability": ("on_time_rate",),
    "/api/channels/economics": ("unit_margin", "demand_confidence", "v7", "v30", "v90", "trend"),
    "/api/rules/skus": ("promo_multiplier",),
}


def _floats(payload: dict, fields: tuple[str, ...]) -> dict:
    for rows in payload.values():
        for row in rows if isinstance(rows, list) else ():
            for f in fields:
                if isinstance(row.get(f), int) and not isinstance(row.get(f), bool):
                    row[f] = float(row[f])
    return payload



def _nested_as_text(payload: dict) -> dict:
    """Send each order's partial_shipments entries as JSON text. Zetaris types the column from the data it saw
    when the source was registered (an empty list becomes array<string>); objects in it later fail every query
    on the table with "GenericRowWithSchema cannot be converted to the string type". The SQL views never read it."""
    for o in payload.get("orders", []):
        o["partial_shipments"] = [x if isinstance(x, str) else json.dumps(x) for x in o.get("partial_shipments") or []]
    return payload

class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            return self._send(200, {"status": "ok", "apis": sorted(ROUTES)})
        if name := ROUTES.get(self.path):
            payload = _floats(json.loads((DATA / name).read_text()), FLOAT_FIELDS.get(self.path, ()))
            return self._send(200, _nested_as_text(payload) if self.path == "/api/amazon/orders" else payload)
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
