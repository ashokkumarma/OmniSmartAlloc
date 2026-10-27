"""Hand-coded equivalent of the OmniSmartAlloc USL: no Zetaris, just Postgres + the five REST APIs directly.

Produces the same outputs as demo/zetaris/usl_queries.sql and the DQ checks in usl_create.sql, so the two
approaches can be compared for code size, run time and agreement. Reads CHANNELS_DB_URL from .env and the
mock API base from MOCK_API_BASE (default http://127.0.0.1:8901). Nothing secret is printed.

    python demo/zetaris/handcoded_equivalent.py
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from src.config import get_settings  # noqa: E402  (loads .env into the environment)

API = os.environ.get("MOCK_API_BASE", "http://127.0.0.1:8901")
PG_TABLES = {"DTC": "dtc_orders", "Etsy": "etsy_orders", "Walmart": "walmart_orders"}


# ---- extract: one connector per source system -------------------------------------------------------------
def rest(path: str, key: str) -> list[dict]:
    with urllib.request.urlopen(f"{API}{path}", timeout=10) as r:
        return json.loads(r.read())[key]


def pg_orders() -> list[dict]:
    import psycopg

    url = os.environ["CHANNELS_DB_URL"]
    out = []
    with psycopg.connect(url) as conn:
        for channel, table in PG_TABLES.items():
            for oid, ts, sku, qty, fq, status in conn.execute(
                    f"SELECT id, ts, sku, qty, fulfilled_qty, status FROM {table}"):
                out.append({"channel": channel, "order_id": oid, "ts": ts, "sku": sku, "qty": int(qty),
                            "fulfilled_qty": int(fq), "status": status})
    return out


def load() -> dict[str, list[dict]]:
    orders = pg_orders() + [{"channel": "Amazon", "order_id": o["id"], "ts": o["ts"], "sku": o["sku"],
                             "qty": int(o["qty"]), "fulfilled_qty": int(o["fulfilled_qty"]), "status": o["status"]}
                            for o in rest("/api/amazon/orders", "orders")]
    return {"sku": rest("/api/rules/skus", "rules"),
            "supplier": rest("/api/suppliers/reliability", "suppliers"),
            "inventory": rest("/api/wms/inventory", "inventory"),
            "inbound_po": rest("/api/wms/inbound", "inbound"),
            "channel_economics": rest("/api/channels/economics", "economics"),
            "channel_order": orders}


# ---- transform: the same three answers as usl_queries.sql -------------------------------------------------
def score(e: dict, promo: float) -> float:
    return float(e["unit_margin"]) * float(e["v30"]) * float(e["demand_confidence"]) * promo


def sellable(d: dict) -> list[dict]:
    rules = {r["sku"]: r for r in d["sku"]}
    sup = {s["supplier"]: s for s in d["supplier"]}
    inbound, expected = defaultdict(float), defaultdict(float)
    for b in d["inbound_po"]:
        s = sup.get(b["supplier"])
        if s is None:  # inner join, as in the SQL
            continue
        inbound[b["sku"]] += b["qty"]
        if b["eta_days"] + (1 - s["on_time_rate"]) * s["typical_delay_days"] <= 7:
            expected[b["sku"]] += b["qty"] * s["on_time_rate"]
    out = []
    for i in sorted(d["inventory"], key=lambda r: r["sku"]):
        r = rules.get(i["sku"])
        if r is None:
            continue
        blocked = bool(r["locked"] or r["manual_override"])
        free = i["on_hand"] - i["committed"]
        exp = round(expected[i["sku"]], 1)
        out.append({"sku": i["sku"], "free_now": free, "inbound_units": inbound[i["sku"]],
                    "expected_inbound_7d": exp, "sellable_7d": 0 if blocked else free + exp, "blocked": blocked})
    return out


def channel_scores(d: dict) -> list[dict]:
    promo = {r["sku"]: float(r["promo_multiplier"] or 1.0) for r in d["sku"]}
    demand = defaultdict(lambda: [0, 0])
    for o in d["channel_order"]:
        demand[(o["sku"], o["channel"])][0] += 1
        demand[(o["sku"], o["channel"])][1] += o["qty"] - o["fulfilled_qty"]
    rows = [{"sku": e["sku"], "channel": e["channel"], "channel_score": round(score(e, promo.get(e["sku"], 1.0)), 1),
             "orders_seen": demand[(e["sku"], e["channel"])][0], "open_units": demand[(e["sku"], e["channel"])][1]}
            for e in d["channel_economics"]]
    return sorted(rows, key=lambda r: (r["sku"], -r["channel_score"]))


def proposed_split(d: dict) -> list[dict]:
    rules = {r["sku"]: r for r in d["sku"]}
    inv = {i["sku"]: i for i in d["inventory"]}
    total = defaultdict(float)
    for e in d["channel_economics"]:
        if e["sku"] in inv and e["sku"] in rules:
            total[e["sku"]] += score(e, 1.0)
    out = []
    for e in d["channel_economics"]:
        i, r = inv.get(e["sku"]), rules.get(e["sku"])
        if i is None or r is None:
            continue
        free = i["on_hand"] - i["committed"]
        units = 0 if (r["locked"] or r["manual_override"]) else math.floor(free * score(e, 1.0) / total[e["sku"]])
        out.append({"sku": e["sku"], "channel": e["channel"], "proposed_units": units})
    return sorted(out, key=lambda r: (r["sku"], -r["proposed_units"]))


# ---- data quality: the same rules registered in the USL ---------------------------------------------------
def dq(d: dict) -> dict:
    skus = {r["sku"] for r in d["sku"]}
    checks = {
        "committed_within_on_hand": (d["inventory"], lambda r: r["on_hand"] is not None and r["committed"] is not None
                                     and 0 <= r["committed"] <= r["on_hand"]),
        "margin_and_confidence_sane": (d["channel_economics"], lambda r: r["unit_margin"] >= 0
                                       and 0 <= r["demand_confidence"] <= 1),
        "fulfilled_within_ordered": (d["channel_order"], lambda r: 0 <= r["fulfilled_qty"] <= r["qty"]),
        "channel_order.sku FK": (d["channel_order"], lambda r: r["sku"] in skus),
    }
    return {name: {"total": len(rows), "valid": sum(map(ok, rows)), "invalid": len(rows) - sum(map(ok, rows))}
            for name, (rows, ok) in checks.items()}


def main() -> int:
    get_settings()
    t0 = time.perf_counter()
    data = load()
    t1 = time.perf_counter()
    result = {"row_counts": {k: len(v) for k, v in data.items()}, "sellable": sellable(data),
              "channel_scores": channel_scores(data), "proposed_split": proposed_split(data), "dq": dq(data)}
    t2 = time.perf_counter()
    result["seconds"] = {"extract": round(t1 - t0, 3), "transform": round(t2 - t1, 3), "total": round(t2 - t0, 3)}

    usl = HERE / "results" / "usl_queries.json"
    if usl.exists():  # agreement check against the captured USL results
        q = json.loads(usl.read_text())
        usl_sellable = {r[0]: float(r[6]) for r in q[1]["rows"]}
        usl_split = {(r[0], r[1]): int(r[4]) for r in q[3]["rows"]}
        result["agrees_with_usl"] = {
            "sellable_7d": all(abs(usl_sellable.get(r["sku"], -1) - r["sellable_7d"]) < 0.05 for r in result["sellable"]),
            "proposed_units": all(usl_split.get((r["sku"], r["channel"])) == r["proposed_units"]
                                  for r in result["proposed_split"]),
        }
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "handcoded_equivalent.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("row_counts", "sellable", "dq", "seconds")}, indent=2))
    print("agrees_with_usl:", result.get("agrees_with_usl"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
