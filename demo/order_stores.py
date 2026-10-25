"""Per-channel order storage: each channel lives in its own system.

  DTC, Etsy, Walmart -> separate tables in the channel Postgres DB (registered in Zetaris via JDBC)
  Amazon             -> Amazon seller REST API (demo/data/amazon_orders.json served by mock_apis.py)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg

DATA = Path(__file__).resolve().parent / "data"
AMAZON_FILE = DATA / "amazon_orders.json"
DB_URL = os.environ.get("CHANNELS_DB_URL",
                        f"postgresql://omni:{os.environ.get('CHANNELS_DB_PASSWORD', 'omni_demo_pw')}@127.0.0.1:5433/channels")
PG_TABLES = {"DTC": "dtc_orders", "Etsy": "etsy_orders", "Walmart": "walmart_orders"}
SOURCES = {**{ch: {"type": "Postgres (JDBC)", "location": f"CHANNEL_DB.{t}"} for ch, t in PG_TABLES.items()},
           "Amazon": {"type": "REST API", "location": "AMAZON_API.orders_raw (/api/amazon/orders)"}}
FIELDS = ("id", "ts", "sku", "qty", "fulfilled_qty", "status", "partial_shipments")


def _amazon_read() -> list[dict]:
    return json.loads(AMAZON_FILE.read_text())["orders"] if AMAZON_FILE.exists() else []


def _amazon_write(orders: list[dict]) -> None:
    AMAZON_FILE.write_text(json.dumps({"orders": orders}, indent=2))


def load_all() -> list[dict]:
    orders: list[dict] = []
    with psycopg.connect(DB_URL) as conn:
        for ch, table in PG_TABLES.items():
            for row in conn.execute(f"SELECT {', '.join(FIELDS)} FROM {table}"):
                o = dict(zip(FIELDS, row))
                o["partial_shipments"] = json.loads(o["partial_shipments"] or "[]")
                orders.append({**o, "channel": ch})
    orders += [{**o, "channel": "Amazon"} for o in _amazon_read()]
    for o in orders:
        o["source"] = SOURCES[o["channel"]]
    return sorted(orders, key=lambda o: o["ts"])


def save(order: dict) -> None:
    """Insert or update one order in its channel's own system."""
    rec = {k: order.get(k) for k in FIELDS}
    rec["fulfilled_qty"] = rec["fulfilled_qty"] or 0
    rec["partial_shipments"] = rec["partial_shipments"] or []
    if order["channel"] == "Amazon":
        orders = [o for o in _amazon_read() if o["id"] != rec["id"]] + [rec]
        _amazon_write(sorted(orders, key=lambda o: o["ts"]))
        return
    table = PG_TABLES[order["channel"]]
    with psycopg.connect(DB_URL) as conn:
        conn.execute(
            f"INSERT INTO {table} ({', '.join(FIELDS)}) VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET qty = EXCLUDED.qty, fulfilled_qty = EXCLUDED.fulfilled_qty, "
            "status = EXCLUDED.status, partial_shipments = EXCLUDED.partial_shipments",
            (rec["id"], rec["ts"], rec["sku"], rec["qty"], rec["fulfilled_qty"], rec["status"],
             json.dumps(rec["partial_shipments"])))
