"""Scenario 1 seed: "DTC is selling ahead of forecast while Amazon lags" on LAMP-002.

Touches LAMP-002 only (other SKUs, and all application code, are left alone). Idempotent: every run
deletes all LAMP-002 orders and outbox records, then reinserts the exact same data.

Assumptions (schema inspected before writing):
- Orders live in the per-channel stores: Postgres CHANNEL_DB.dtc_orders/etsy_orders/walmart_orders and the
  Amazon REST source (demo/data/amazon_orders.json served at /api/amazon/orders -> AMAZON_API.orders_raw).
  Columns: id, ts, sku, qty, fulfilled_qty, status, partial_shipments. One row = one unit, status "fulfilled".
- All pre-existing LAMP-002 orders (including generated history) are removed so the scenario numbers are exact.
- DEMO_NOW (env, ISO-8601) defaults to today 00:00 UTC and is persisted in demo/data/scenario1_state.json so
  verify uses the same clock. "Now" = start of day 5; the current window = days 0..4 (DEMO_NOW-5d .. DEMO_NOW).
- Margins are dollars per unit and velocities are units/day, both for LAMP-002 rows of CHANNEL_ANALYTICS
  (channel_economics.json); velocities are derived from the seeded orders so the sources agree.
- Supplier BRIGHT (only LAMP-002 uses it) is set to 90% on-time / 1-day delay. PO-7001 replaces PO-9002.
- There is no safety buffer: Sellable = OnHand - Committed and the starting caps sum to the full on-hand stock.
- The starting caps are stamped as the agent's last allocation run (state Balanced) at DEMO_NOW - 5 days.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "demo"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import psycopg  # noqa: E402

import order_stores  # noqa: E402

SKU = "LAMP-002"
DATA, OUTBOX = ROOT / "demo" / "data", ROOT / "demo" / "outbox"
STATE_FILE = DATA / "scenario1_state.json"
CHANNELS = ["DTC", "Amazon", "Etsy", "Walmart"]
PRIOR_PER_DAY = {"DTC": 2, "Amazon": 3, "Etsy": 1, "Walmart": 1}
CURRENT_PER_DAY = {"DTC": [4] * 5, "Amazon": [2, 1, 1, 1, 1], "Etsy": [1] * 5, "Walmart": [1] * 5}
CAPS = {"DTC": 30, "Amazon": 40, "Etsy": 15, "Walmart": 15}
MARGINS = {"DTC": 14, "Etsy": 11, "Amazon": 6, "Walmart": 5}
START_ON_HAND = 100
SEED_NOTE = "scenario1 seed"


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def seed_now() -> datetime:
    raw = os.environ.get("DEMO_NOW")
    return parse(raw) if raw else datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def saved_now() -> datetime | None:
    raw = os.environ.get("DEMO_NOW")
    if raw:
        return parse(raw)
    return parse(json.loads(STATE_FILE.read_text())["demo_now"]) if STATE_FILE.exists() else None


def build_orders(now: datetime) -> list[dict]:
    start = now - timedelta(days=5)
    orders = []
    for ch in CHANNELS:
        for day in range(-85, 5):
            n = PRIOR_PER_DAY[ch] if day < 0 else CURRENT_PER_DAY[ch][day]
            for k in range(n):
                ts = start + timedelta(days=day + (k + 0.5) / n)
                orders.append({"id": hashlib.md5(f"{SKU}-{ch}-{day}-{k}".encode()).hexdigest()[:8], "channel": ch,
                               "sku": SKU, "ts": iso(ts), "qty": 1, "fulfilled_qty": 1, "status": "fulfilled",
                               "partial_shipments": []})
    return orders


def window_units(orders: list[dict], now: datetime, channel: str, days: int) -> int:
    lo, hi = iso(now - timedelta(days=days)), iso(now)
    return sum(o["fulfilled_qty"] for o in orders if o["channel"] == channel and o["sku"] == SKU and lo <= o["ts"] < hi)


def velocities(orders: list[dict], now: datetime, channel: str) -> dict[str, float]:
    return {f"v{d}": window_units(orders, now, channel, d) / d for d in (7, 30, 90)}


def _edit(name: str, key: str, fn) -> int:
    doc = json.loads((DATA / name).read_text())
    n = fn(doc[key])
    (DATA / name).write_text(json.dumps(doc, indent=2))
    return n


def _purge_outbox() -> None:
    for name in ("allocations.jsonl", "decisions.jsonl", "alerts.jsonl"):
        p = OUTBOX / name
        if p.exists():
            rows = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip() and json.loads(ln).get("sku") != SKU]
            p.write_text("".join(ln + "\n" for ln in rows), encoding="utf-8")


def _wipe_orders() -> None:
    with psycopg.connect(order_stores.DB_URL) as conn:
        for table in order_stores.PG_TABLES.values():
            conn.execute(f"DELETE FROM {table} WHERE sku = %s", (SKU,))
    order_stores._amazon_write([o for o in order_stores._amazon_read() if o["sku"] != SKU])


def run() -> dict:
    now = seed_now()
    orders = build_orders(now)
    _wipe_orders()
    order_stores.save_many(orders)
    STATE_FILE.write_text(json.dumps({"demo_now": iso(now), "sku": SKU}, indent=2))

    sold_current = {ch: window_units(orders, now, ch, 5) for ch in CHANNELS}
    on_hand = START_ON_HAND - sum(sold_current.values())

    def inv(rows):
        rows[:] = [r for r in rows if r["sku"] != SKU] + [
            {"sku": SKU, "on_hand": on_hand, "committed": 0, "unputaway": 0, "age_hours": 0.2}]
        return 1
    _edit("wms_inventory.json", "inventory", inv)

    def inbound(rows):
        rows[:] = [r for r in rows if r["sku"] != SKU] + [
            {"po": "PO-7001", "sku": SKU, "qty": 200, "eta_days": 4, "status": "in_transit", "supplier": "BRIGHT"}]
        return 1
    _edit("wms_inbound.json", "inbound", inbound)

    def suppliers(rows):
        for r in rows:
            if r["supplier"] == "BRIGHT":
                r.update(on_time_rate=0.90, typical_delay_days=1)
        return 1
    _edit("supplier_reliability.json", "suppliers", suppliers)

    def econ(rows):
        by_ch = {r["channel"]: r for r in rows if r["sku"] == SKU}
        for ch in CHANNELS:
            base = by_ch.get(ch, {"sku": SKU, "channel": ch, "demand_confidence": 0.9, "trend": 1.0, "margin_age_hours": 3})
            base.update(unit_margin=MARGINS[ch], floor_units=0, **{k: round(v, 6) for k, v in velocities(orders, now, ch).items()})
            if ch not in by_ch:
                rows.append(base)
        return len(CHANNELS)
    _edit("channel_economics.json", "economics", econ)

    def rules(rows):
        rows[:] = [r for r in rows if r["sku"] != SKU] + [
            {"sku": SKU, "locked": False, "manual_override": False, "clearance": False, "promo_multiplier": 1.0}]
        return 1
    _edit("sku_rules.json", "rules", rules)

    _purge_outbox()
    remaining = {ch: CAPS[ch] - sold_current[ch] for ch in CHANNELS}
    stamp = {"ts": iso(now - timedelta(days=5)), "sku": SKU, "state": "Balanced", "allocation": dict(CAPS), "target": dict(CAPS),
             "sellable_units": sum(CAPS.values()), "shared_pool": False, "stepped_by_25pct_limit": False,
             "sold_in_window": sold_current, "remaining": remaining, "note": SEED_NOTE,
             "reason": "Window-start allocation for the 14-day planning window"}
    with (OUTBOX / "allocations.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(stamp) + "\n")

    counts = {ch: sum(1 for o in orders if o["channel"] == ch) for ch in CHANNELS}
    return {"demo_now": iso(now), "orders_by_channel": counts, "orders_total": len(orders), "on_hand": on_hand,
            "committed": 0, "sellable": on_hand, "caps": dict(CAPS), "remaining": remaining,
            "rows": {"orders (4 channel stores)": len(orders), "wms_inventory": 1, "wms_inbound": 1, "supplier_reliability": 1,
                     "channel_economics": len(CHANNELS), "sku_rules": 1, "allocations (outbox)": 1}}


if __name__ == "__main__":
    out = run()
    print(f"Scenario 1 seeded for {SKU} at DEMO_NOW={out['demo_now']}")
    print(f"  files: demo/scenarios/seed_lamp002.py (this), reset_lamp002.py, verify_lamp002.py")
    for k, v in out["rows"].items():
        print(f"  {k}: {v} row(s)")
    print(f"  orders by channel: {out['orders_by_channel']}  | on_hand {out['on_hand']}, sellable {out['sellable']}, remaining caps {out['remaining']}")
    print("Run: python demo/scenarios/verify_lamp002.py")
