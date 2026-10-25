"""OmniSmartAlloc demo UI server (port 8902).

Pages:   /channels  order creation across DTC, Amazon, Etsy, Walmart
         /ops       centralized inventory + agent activity
APIs:    /api/state /api/order /api/order/<id>/(fulfill|partial|cancel) /api/federated
         /api/agent/run /api/agent/status

Each channel's orders live in their own system (see demo/order_stores.py): DTC/Etsy/Walmart in
separate Postgres tables, Amazon behind its REST API. Orders also mutate
demo/data/wms_inventory.json (committed units) so the agent sees the change on the next run.

Run: docker compose -f demo/docker-compose.channels.yml up -d   (channel order DB)
     python demo/mock_apis.py 8901                             (source REST APIs)
     python demo/server.py                                     (this UI on http://localhost:8902)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "demo"))
import order_stores  # noqa: E402

DATA = ROOT / "demo" / "data"
OUTBOX = ROOT / "demo" / "outbox"
WEB = ROOT / "demo" / "web"
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
CHANNELS = {"DTC": "#7C3AED", "Amazon": "#FF9900", "Etsy": "#F1641E", "Walmart": "#0071CE"}
STATE_COLORS = {"Abundant": "#22C55E", "Balanced": "#38BDF8", "Tight": "#F59E0B", "Critical": "#EF4444"}

_LOCK = threading.Lock()
_AGENT_JOB: dict = {"running": False, "tail": ""}


def _load(name: str) -> dict:
    return json.loads((DATA / name).read_text())


def _save(name: str, obj: dict) -> None:
    (DATA / name).write_text(json.dumps(obj, indent=2))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()] if path.exists() else []


OPEN_STATUSES = ("open", "partial")


def _orders() -> list[dict]:
    orders = order_stores.load_all()
    for o in orders:
        o["remaining"] = o["qty"] - o["fulfilled_qty"] if o["status"] in OPEN_STATUSES else 0
    return orders


FEDERATED_SQL = """SELECT channel, source_system, COUNT(*) AS orders, SUM(qty) AS units_ordered,
       SUM(fulfilled_qty) AS units_shipped,
       SUM(CASE WHEN status IN ('open', 'partial') THEN qty - fulfilled_qty ELSE 0 END) AS units_open
FROM (
  SELECT 'DTC' AS channel, 'Postgres CHANNEL_DB.dtc_orders' AS source_system, qty, fulfilled_qty, status FROM CHANNEL_DB.dtc_orders
  UNION ALL
  SELECT 'Etsy', 'Postgres CHANNEL_DB.etsy_orders', qty, fulfilled_qty, status FROM CHANNEL_DB.etsy_orders
  UNION ALL
  SELECT 'Walmart', 'Postgres CHANNEL_DB.walmart_orders', qty, fulfilled_qty, status FROM CHANNEL_DB.walmart_orders
  UNION ALL
  SELECT 'Amazon', 'REST AMAZON_API -> omnismart.amazon_orders', qty, fulfilled_qty, status FROM omnismart.amazon_orders
) all_channels
GROUP BY channel, source_system
ORDER BY channel"""
_FED: dict = {"db": None, "at": 0.0, "result": None}
_FED_LOCK = threading.Lock()


def _federated() -> dict:
    """Run one live Lightning SQL query that unions all four channel sources through Zetaris."""
    with _FED_LOCK:
        if _FED["result"] and time.time() - _FED["at"] < 10:
            return _FED["result"]
        from src.config import get_settings
        from src.data_connectors.zetaris_jdbc import ZetarisJdbcConnector
        t0 = time.time()
        try:
            if _FED["db"] is None:
                _FED["db"] = ZetarisJdbcConnector(get_settings())
            rows = _FED["db"].query(FEDERATED_SQL, 50)
            result = {"ok": True, "sql": FEDERATED_SQL, "rows": rows, "ms": int((time.time() - t0) * 1000)}
        except Exception as e:
            if _FED["db"] is not None:
                try:
                    _FED["db"].close()
                except Exception:
                    pass
            _FED["db"] = None
            result = {"ok": False, "sql": FEDERATED_SQL, "error": f"{type(e).__name__}: {str(e)[:300]}"}
        _FED.update(at=time.time(), result=result)
        return result


def _state() -> dict:
    inv = _load("wms_inventory.json")["inventory"]
    econ = _load("channel_economics.json")["economics"]
    rules = _load("sku_rules.json")["rules"]
    catalog = {p["sku"]: p for p in _load("catalog.json")["products"]}
    orders = _orders()
    allocs = _jsonl(OUTBOX / "allocations.jsonl")
    latest_alloc = {r["sku"]: r for r in allocs}  # last write wins (jsonl order)
    decisions = _jsonl(OUTBOX / "decisions.jsonl")
    latest_decision = {r["sku"]: r["record"] for r in decisions}
    open_by_channel: dict[tuple[str, str], int] = {}
    for o in orders:
        if o["status"] in OPEN_STATUSES:
            open_by_channel[(o["sku"], o["channel"])] = open_by_channel.get((o["sku"], o["channel"]), 0) + o["remaining"]
    skus = []
    for row in inv:
        sku = row["sku"]
        rec = latest_decision.get(sku, {})
        skus.append({
            "sku": sku, **{k: row.get(k) for k in ("on_hand", "committed", "unputaway")},
            "title": catalog.get(sku, {}).get("title", sku), "price": catalog.get(sku, {}).get("price"),
            "state": rec.get("state"), "state_color": STATE_COLORS.get(rec.get("state"), "#94A3B8"),
            "sellable_units": rec.get("sellable_units"), "buffer_units": rec.get("buffer_units"),
            "days_of_cover": rec.get("days_of_cover"),
            "allocation": (latest_alloc.get(sku) or {}).get("allocation"),
            "open_by_channel": {ch: open_by_channel.get((sku, ch), 0) for ch in CHANNELS},
            "locked": next((r["locked"] for r in rules if r["sku"] == sku), False),
        })
    suppliers = {s["supplier"]: s for s in _load("supplier_reliability.json")["suppliers"]}
    inbound = []
    for sh in _load("wms_inbound.json")["inbound"]:
        rel = suppliers.get(sh["supplier"], {})
        eta, delay = sh.get("eta_days") or 0, rel.get("typical_delay_days") or 0
        inbound.append({**sh,
                        "arrival_date": time.strftime("%Y-%m-%d", time.gmtime(time.time() + eta * 86400)),
                        "projected_date": time.strftime("%Y-%m-%d", time.gmtime(time.time() + (eta + delay) * 86400)),
                        "on_time_rate": rel.get("on_time_rate")})
    return {"skus": skus, "channels": [{"name": n, "color": c, "source": order_stores.SOURCES[n]} for n, c in CHANNELS.items()],
            "economics": econ, "inbound": inbound, "orders": list(reversed(orders))[:200],
            "alerts": list(reversed(_jsonl(OUTBOX / "alerts.jsonl")))[:100],
            "decisions": list(reversed(decisions[-50:])),
            "agent": _AGENT_JOB}


def _create_order(body: dict) -> tuple[int, dict]:
    channel, sku, qty = body.get("channel"), str(body.get("sku", "")), body.get("qty")
    if channel not in CHANNELS:
        return 400, {"error": f"channel must be one of {sorted(CHANNELS)}"}
    if not isinstance(qty, int) or qty <= 0 or qty > 999:
        return 400, {"error": "qty must be a positive integer"}
    with _LOCK:
        inv = _load("wms_inventory.json")["inventory"]
        row = next((r for r in inv if r["sku"] == sku), None)
        if row is None:
            return 404, {"error": f"unknown sku {sku}"}
        available = (row.get("on_hand") or 0) - (row.get("committed") or 0)
        if qty > available:
            return 409, {"error": f"only {available} units available (agent buffer + committed protect the rest)"}
        allocs = _jsonl(OUTBOX / "allocations.jsonl")
        latest = next((r for r in reversed(allocs) if r["sku"] == sku), None)
        open_ch = sum(o["remaining"] for o in _orders() if o["sku"] == sku and o["channel"] == channel and o["status"] in OPEN_STATUSES)
        if latest and (open_ch + qty) > latest["allocation"].get(channel, 0):
            return 409, {"error": f"exceeds the agent's {channel} allocation ({latest['allocation'].get(channel, 0)} units; {open_ch} already open). Run the allocation cycle again."}
        order = {"id": uuid.uuid4().hex[:8], "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "channel": channel, "sku": sku, "qty": qty, "fulfilled_qty": 0, "status": "open"}
        order_stores.save(order)
        row["committed"] = (row.get("committed") or 0) + qty
        _save("wms_inventory.json", {"inventory": inv})
        return 201, {"order": order, "available_after": available - qty, "stored_in": order_stores.SOURCES[channel]}


def _settle_order(order_id: str, action: str, qty: int | None = None, reason: str = "") -> tuple[int, dict]:
    """fulfill = ship all remaining; partial = ship `qty` (< remaining); cancel = release unshipped units."""
    with _LOCK:
        orders = _orders()
        order = next((o for o in orders if o["id"] == order_id), None)
        if order is None:
            return 404, {"error": "order not found"}
        if order["status"] not in OPEN_STATUSES:
            return 409, {"error": f"order is already {order['status']}"}
        remaining = order["remaining"]
        if action == "partial" and not (isinstance(qty, int) and 0 < qty < remaining):
            return 400, {"error": f"partial quantity must be between 1 and {remaining - 1}"}
        inv = _load("wms_inventory.json")["inventory"]
        row = next(r for r in inv if r["sku"] == order["sku"])
        if action in ("fulfill", "partial"):
            ship = remaining if action == "fulfill" else qty
            row["on_hand"] -= ship
            row["committed"] -= ship
            order["fulfilled_qty"] += ship
            order["status"] = "fulfilled" if order["fulfilled_qty"] == order["qty"] else "partial"
            if action == "partial":
                order.setdefault("partial_shipments", []).append(
                    {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "qty": ship, "reason": reason[:300]})
        elif action == "cancel":
            row["committed"] -= remaining
            order["status"] = "cancelled"
        else:
            return 400, {"error": "action must be fulfill, partial or cancel"}
        order_stores.save(order)
        _save("wms_inventory.json", {"inventory": inv})
        order["remaining"] = order["qty"] - order["fulfilled_qty"] if order["status"] in OPEN_STATUSES else 0
        return 200, {"order": order}


def _run_agent(scope: str) -> None:
    q = ("Run the allocation cycle for every SKU in the catalog: MUG-001, LAMP-002, KBD-003 and LOCK-004."
         if scope == "all" else f"Run the allocation cycle for SKU {scope}.")
    _AGENT_JOB.update(running=True, tail="")
    try:
        res = subprocess.run([str(VENV_PY), "-m", "src.main", q, "--max-steps", "25"],
                             cwd=ROOT, capture_output=True, text=True, timeout=600)
        _AGENT_JOB["tail"] = (res.stdout + res.stderr)[-4000:]
    except subprocess.TimeoutExpired:
        _AGENT_JOB["tail"] = "agent timed out after 600 s"
    finally:
        _AGENT_JOB["running"] = False


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/channels"):
            return self._send(200, (WEB / "channels.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/ops":
            return self._send(200, (WEB / "ops.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/state":
            return self._json(200, _state())
        if path == "/api/agent/status":
            return self._json(200, _AGENT_JOB)
        if path == "/api/federated":
            return self._json(200, _federated())
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid json"})
        if path == "/api/order":
            return self._json(*_create_order(body))
        if m := re.match(r"^/api/order/([0-9a-f]+)/(fulfill|partial|cancel)$", path):
            return self._json(*_settle_order(m.group(1), m.group(2), body.get("qty"), str(body.get("reason") or "").strip()))
        if path == "/api/agent/run":
            if _AGENT_JOB["running"]:
                return self._json(409, {"error": "agent already running"})
            scope = str(body.get("scope", "all"))
            threading.Thread(target=_run_agent, args=(scope,), daemon=True).start()
            return self._json(202, {"started": scope})
        self._json(404, {"error": "not found"})

    def log_message(self, *_args) -> None:
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8902
    print(f"OmniSmartAlloc demo UI on http://localhost:{port}  (/channels and /ops)")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
