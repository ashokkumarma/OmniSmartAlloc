"""OmniSmartAlloc demo UI server (port 8902).

Pages:   /oms       order management (OMS): order creation across DTC, Amazon, Etsy, Walmart
         /ims       inventory management (IMS): centralized inventory + agent activity
         /, /app, /ops, /channels, ...  the React app (demo/app), when it is built
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
import os
import re
import shutil
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
from src.allocation import agent_log  # noqa: E402
from src.main import EVENT_PREFIX  # noqa: E402

DATA = ROOT / "demo" / "data"
OUTBOX = ROOT / "demo" / "outbox"
WEB = ROOT / "demo" / "web"
APP_DIST = ROOT / "demo" / "app" / "dist"  # built by `npm run build` in demo/app (scripts/start_demo.py does it)
APP_ROUTES = {"/", "/app", "/channels", "/ops", "/orders", "/inventory", "/agent", "/storefronts", "/sources",
              "/instructions", "/context", "/dashboard", "/smart-allocation"}
APP_TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
             ".woff2": "font/woff2", ".png": "image/png", ".json": "application/json"}
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
CHANNELS = {"DTC": "#7C3AED", "Amazon": "#FF9900", "Etsy": "#F1641E", "Walmart": "#0071CE"}
STATE_COLORS = {"Abundant": "#22C55E", "Balanced": "#38BDF8", "Tight": "#F59E0B", "Critical": "#EF4444"}

_LOCK = threading.Lock()
_AGENT_JOB: dict = {"running": False, "tail": "", "ok": None, "steps": []}
_AUTO_AGENT = {"enabled": True}
_AGENT_TIMER: threading.Timer | None = None
_AGENT_PENDING_SKUS: set[str] = set()
_AGENT_PENDING_ALL = False
_AGENT_QUEUE_LOCK = threading.Lock()


def _schedule_agent_run(scope: str = "all", delay: float = 5.0) -> None:
    """Debounce changes; SKU-specific updates only run that SKU, while full-cycle triggers run all."""
    global _AGENT_TIMER, _AGENT_PENDING_ALL
    if not _AUTO_AGENT["enabled"]:
        return
    with _AGENT_QUEUE_LOCK:
        if scope == "all":
            _AGENT_PENDING_ALL = True
            _AGENT_PENDING_SKUS.clear()
        elif not _AGENT_PENDING_ALL:
            _AGENT_PENDING_SKUS.add(scope)
        if _AGENT_TIMER and _AGENT_TIMER.is_alive():
            _AGENT_TIMER.cancel()
        _AGENT_TIMER = threading.Timer(delay, _kick_scheduled_agent)
        _AGENT_TIMER.daemon = True
        _AGENT_TIMER.start()


def _kick_scheduled_agent() -> None:
    global _AGENT_TIMER, _AGENT_PENDING_ALL
    with _AGENT_QUEUE_LOCK:
        if not _AUTO_AGENT["enabled"]:
            return
        if _AGENT_JOB["running"]:
            _AGENT_TIMER = threading.Timer(5.0, _kick_scheduled_agent)
            _AGENT_TIMER.daemon = True
            _AGENT_TIMER.start()
            return
        scopes = ["all"] if _AGENT_PENDING_ALL else sorted(_AGENT_PENDING_SKUS)
        if not scopes:
            return
        _AGENT_PENDING_ALL = False
        _AGENT_PENDING_SKUS.clear()
    threading.Thread(target=_run_agent, args=(scopes,), daemon=True).start()


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


def _totals(orders: list[dict]) -> dict:
    """KPI and chart totals over every order. The page only receives the latest 200 orders, so it must not count them."""
    status_counts = {s: 0 for s in ("open", "partial", "fulfilled", "cancelled")}
    closed_units: dict[str, dict[str, int]] = {ch: {} for ch in CHANNELS}
    for o in orders:
        status_counts[o["status"]] = status_counts.get(o["status"], 0) + 1
        if o["status"] not in OPEN_STATUSES:
            units = o["qty"] if o["status"] == "fulfilled" else o["fulfilled_qty"]
            per_sku = closed_units.setdefault(o["channel"], {})
            per_sku[o["sku"]] = per_sku.get(o["sku"], 0) + units
    return {
        "orders": len(orders),
        "units_ordered": sum(o["qty"] for o in orders),
        "units_awaiting": sum(o["remaining"] for o in orders if o["status"] in OPEN_STATUSES),
        "units_shipped": sum(o["fulfilled_qty"] or 0 for o in orders),
        "units_cancelled": sum(o["qty"] - (o["fulfilled_qty"] or 0) for o in orders if o["status"] == "cancelled"),
        "skus": len({o["sku"] for o in orders}),
        "status_counts": status_counts,
        "closed_units": closed_units,
    }


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
    used_by_channel: dict[tuple[str, str], int] = {}
    for o in orders:
        if o["status"] in OPEN_STATUSES:
            open_by_channel[(o["sku"], o["channel"])] = open_by_channel.get((o["sku"], o["channel"]), 0) + o["remaining"]
        # Units ordered after the channel's current allocation was set draw down its allowance --
        # fulfilled or still open, they consumed stock either way. Only cancelled orders give it back.
        alloc_ts = (latest_alloc.get(o["sku"]) or {}).get("ts", "")
        if o["status"] != "cancelled" and o["ts"] >= alloc_ts:
            used_by_channel[(o["sku"], o["channel"])] = used_by_channel.get((o["sku"], o["channel"]), 0) + o["qty"]
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
            "used_by_channel": {ch: used_by_channel.get((sku, ch), 0) for ch in CHANNELS},
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
            "economics": econ, "inbound": inbound, "orders": list(reversed(orders))[:200], "totals": _totals(orders),
            "alerts": list(reversed(_jsonl(OUTBOX / "alerts.jsonl")))[:100],
            "decisions": list(reversed(decisions[-50:])),
            "alloc_log": [{"ts": r["ts"], "sku": r["sku"], "allocation": r["allocation"], "reason": r.get("reason", "")}
                          for r in allocs[-200:]],
            "agent": _AGENT_JOB, "agent_auto": _AUTO_AGENT["enabled"]}


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
            return 409, {"error": f"only {available} units available (committed orders protect the rest)"}
        allocs = _jsonl(OUTBOX / "allocations.jsonl")
        latest = next((r for r in reversed(allocs) if r["sku"] == sku), None)
        alloc_ts = latest["ts"] if latest else ""
        used_ch = sum(o["qty"] for o in _orders()
                      if o["sku"] == sku and o["channel"] == channel and o["status"] != "cancelled" and o["ts"] >= alloc_ts)
        if latest and (used_ch + qty) > latest["allocation"].get(channel, 0):
            return 409, {"error": f"exceeds the agent's {channel} allocation ({latest['allocation'].get(channel, 0)} units; "
                                  f"{used_ch} already used). Run the allocation cycle again."}
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


BASELINE = Path(__file__).resolve().parent / "baseline"


def _reset() -> dict:
    """Restore the demo to the saved baseline state (see demo/baseline/save_baseline.py)."""
    with _LOCK:
        if not (BASELINE / "orders.json").exists():
            return {"reset": False, "error": "no baseline saved — run demo/baseline/save_baseline.py"}
        for f in (BASELINE / "data").glob("*.json"):
            shutil.copy2(f, DATA / f.name)
        order_stores.clear_all()
        orders = json.loads((BASELINE / "orders.json").read_text(encoding="utf-8"))
        if orders:
            order_stores.save_many(orders)
        OUTBOX.mkdir(parents=True, exist_ok=True)  # gitignored, so absent on a fresh clone
        for f in (BASELINE / "outbox").glob("*.jsonl"):
            (OUTBOX / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
        return {"reset": True, "skus": len(_load("wms_inventory.json")["inventory"]),
                "orders_restored": len(orders), "baseline": str(BASELINE)}


def _gen_history(days: int = 90, seed: int = 42) -> dict:
    """Simulate `days` of orders across channels, weighted by demand_confidence and velocity.
    Older orders arrive fulfilled/cancelled; the last 3 days leave open+partial orders (which
    also bump committed so WMS stays consistent)."""
    import random
    rng = random.Random(seed)
    econ = [e for e in _load("channel_economics.json")["economics"] if e["channel"] in CHANNELS]
    now = time.time()
    orders: list[dict] = []
    for e in econ:
        conf, v7 = e.get("demand_confidence") or 1.0, max(e.get("v7") or 0.5, 0.5)
        n = max(2, min(60, round(days * v7 * conf / 10)))
        for _ in range(n):
            ts = now - rng.uniform(0, days * 86400)
            qty = rng.choices([1, 2, 3, 4, 5], weights=[50, 25, 12, 8, 5])[0]
            if ts > now - 3 * 86400:  # last 3 days -> some still open/partial
                roll, status, fqty = rng.random(), "open", 0
                if roll > 0.5: status, fqty = "fulfilled", qty
                elif roll > 0.3:
                    status = "partial"; fqty = rng.randint(1, qty - 1) if qty > 1 else 0
                    if fqty == 0: status = "open"
            else:
                roll = rng.random()
                status, fqty = ("cancelled", 0) if roll < 0.1 else ("fulfilled", qty)
            orders.append({"id": uuid.uuid4().hex[:8], "channel": e["channel"], "sku": e["sku"],
                           "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)), "qty": qty,
                           "fulfilled_qty": fqty, "status": status,
                           "partial_shipments": [{"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
                                                  "qty": fqty, "reason": "split shipment (generated)"}] if status == "partial" else []})
    with _LOCK:
        order_stores.save_many(orders)
        inv = _load("wms_inventory.json")
        for o in orders:
            if o["status"] == "open":
                adj = o["qty"]
            elif o["status"] == "partial":
                adj = o["qty"] - o["fulfilled_qty"]
            else:
                continue
            for r in inv["inventory"]:
                if r["sku"] == o["sku"]:
                    r["committed"] = (r.get("committed") or 0) + adj
        _save("wms_inventory.json", inv)
    counts = {ch: sum(1 for o in orders if o["channel"] == ch) for ch in CHANNELS}
    return {"generated": len(orders), "by_channel": counts}


def _scenario1() -> dict:
    """Scenario 1 (LAMP-002: DTC ahead of forecast, Amazon lagging): load the starting data, then verify it."""
    from scenarios import seed_lamp002, verify_lamp002
    with _LOCK:
        summary = seed_lamp002.run()
    _FED["result"] = None
    checks = verify_lamp002.run_checks()
    return {"summary": summary, "checks": checks,
            "passed": sum(1 for c in checks if c["ok"] is True), "failed": sum(1 for c in checks if c["ok"] is False)}


def _run_one(question: str, steps: list[dict], out: list[str]) -> bool:
    """Run the agent once, streaming its "@@step {json}" lines into `steps` (the live trace on /ops)."""
    proc = subprocess.Popen([str(VENV_PY), "-m", "src.main", question, "--max-steps", "25", "--events"], cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    timed_out = threading.Event()

    def _kill() -> None:
        timed_out.set()
        proc.kill()

    timer = threading.Timer(600, _kill)
    timer.start()
    try:
        for line in proc.stdout:
            if line.startswith(EVENT_PREFIX):
                try:
                    steps.append(json.loads(line[len(EVENT_PREFIX):]))
                    continue
                except json.JSONDecodeError:
                    pass
            out.append(line)
        proc.wait()
    finally:
        timer.cancel()
    if timed_out.is_set():
        out.append(f"agent timed out after 600 s: {question}\n")
    return proc.returncode == 0 and not timed_out.is_set()


def _run_agent(scope: str | list[str]) -> None:
    """Run the allocation cycle for each queued scope ("all" or one SKU), one after another."""
    scopes = [scope] if isinstance(scope, str) else scope
    steps: list[dict] = []
    out: list[str] = []
    _AGENT_JOB.update(running=True, scope=", ".join(scopes), tail="", ok=None, steps=steps)
    ok = True
    try:
        for item in scopes:
            q = ("Run the allocation cycle for every SKU in the catalog: MUG-001, LAMP-002, RUG-003 and LOCK-004."
                 if item == "all" else f"Run the allocation cycle for SKU {item}.")
            if not _run_one(q, steps, out):
                ok = False
                break
    except OSError as e:  # the agent could not be started (no venv, bad interpreter path)
        ok = False
        out.append(f"could not start the agent: {e}\n")
    finally:
        _AGENT_JOB["tail"] = "".join(out)[-4000:]
        _AGENT_JOB["ok"] = ok
        _AGENT_JOB["running"] = False


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        built = (APP_DIST / "index.html").is_file()
        if built and (path in APP_ROUTES or re.fullmatch(r"/inventory/[A-Za-z0-9-]{1,32}", path)):  # the React app (demo/app) handles its own routing
            return self._send(200, (APP_DIST / "index.html").read_bytes(), "text/html; charset=utf-8")
        if built and (m := re.fullmatch(r"/(assets/\w[\w.-]*|favicon\.svg)", path)) and (APP_DIST / m.group(1)).is_file():
            f = APP_DIST / m.group(1)
            return self._send(200, f.read_bytes(), APP_TYPES.get(f.suffix, "application/octet-stream"))
        # The original pages: always at /classic/..., and at / /channels /ops when the app is not built.
        if path in ("/oms", "/classic/channels") or (not built and path in ("/", "/channels")):
            return self._send(200, (WEB / "channels.html").read_bytes(), "text/html; charset=utf-8")
        if path in ("/ims", "/classic/ops") or (not built and path == "/ops"):
            return self._send(200, (WEB / "ops.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/vendor/chart.umd.js":  # served locally so charts work without internet
            return self._send(200, (WEB / "vendor" / "chart.umd.js").read_bytes(), "text/javascript; charset=utf-8")
        if path == "/api/state":
            return self._json(200, _state())
        if path == "/api/agent/status":
            return self._json(200, _AGENT_JOB)
        if path == "/api/federated":
            return self._json(200, _federated())
        if path == "/api/agent-log":
            return self._json(200, {"events": agent_log.events(OUTBOX), "savings": agent_log.savings_summary(OUTBOX)})
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid json"})
        if path == "/api/order":
            code, out = _create_order(body)
            return self._json(code, out)
        if m := re.match(r"^/api/order/([0-9a-f]+)/(fulfill|partial|cancel)$", path):
            code, out = _settle_order(m.group(1), m.group(2), body.get("qty"), str(body.get("reason") or "").strip())
            if code in (200, 201) and m.group(2) in ("fulfill", "partial"):
                _schedule_agent_run(out["order"]["sku"])
            return self._json(code, out)
        if m := re.match(r"^/api/approvals/([0-9a-f]+)/approve$", path):
            with _LOCK:
                code, out = agent_log.approve(OUTBOX, m.group(1))
            if code == 200:
                _schedule_agent_run()
            return self._json(code, out)
        if m := re.match(r"^/api/approvals/([0-9a-f]+)/deny$", path):
            with _LOCK:
                code, out = agent_log.deny(OUTBOX, m.group(1), str(body.get("reason") or "").strip())
            if code == 200:
                _schedule_agent_run()
            return self._json(code, out)
        if path == "/api/scenario/1":
            out = _scenario1()
            _schedule_agent_run()
            return self._json(200, out)
        if path == "/api/history":
            out = _gen_history(int(body.get("days") or 90))
            _schedule_agent_run()
            return self._json(200, out)
        if path == "/api/agent/auto":
            _AUTO_AGENT["enabled"] = bool(body.get("enabled", True))
            return self._json(200, {"agent_auto": _AUTO_AGENT["enabled"]})
        if path == "/api/reset":
            return self._json(200, _reset())
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
    # Localhost only: the pages can reset the demo and start paid agent runs, so they must not be reachable
    # from the network. Set OMNI_UI_HOST=0.0.0.0 to share it deliberately.
    host = os.environ.get("OMNI_UI_HOST", "127.0.0.1")
    print(f"OmniSmartAlloc demo UI on http://localhost:{port}  (app: /  OMS: /oms  IMS: /ims)")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
