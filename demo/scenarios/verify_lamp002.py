"""Verify the Scenario 1 starting state for LAMP-002 and preview what the agent will do.

    python demo/scenarios/verify_lamp002.py        # prints PASS/FAIL per check, exit 1 on any FAIL
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "demo"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import order_stores  # noqa: E402
from scenarios import seed_lamp002 as seed  # noqa: E402

SKU, CHANNELS = seed.SKU, seed.CHANNELS
EXPECT_UNITS = {
    7: {"DTC": 24, "Amazon": 12, "Etsy": 7, "Walmart": 7},
    30: {"DTC": 70, "Amazon": 81, "Etsy": 30, "Walmart": 30},
    90: {"DTC": 190, "Amazon": 261, "Etsy": 90, "Walmart": 90},
}
EXPECT_VELOCITY = {"DTC": 2.84, "Amazon": 2.25, "Etsy": 1.00, "Walmart": 1.00}
EXPECT_REMAINING = {"DTC": 10, "Amazon": 34, "Etsy": 10, "Walmart": 10}


def _doc(name: str, key: str) -> list[dict]:
    return json.loads((seed.DATA / name).read_text())[key]


def _check(name: str, ok: bool | None, detail: str = "") -> dict:
    return {"name": name, "ok": ok, "detail": detail}


def _federated_counts(db) -> dict[str, int]:
    sql = {ch: f"SELECT COUNT(*) AS n FROM CHANNEL_DB.{t} WHERE sku = '{SKU}'" for ch, t in
           ((c, order_stores.PG_TABLES[c]) for c in ("DTC", "Etsy", "Walmart"))}
    sql["Amazon"] = f"SELECT COUNT(*) AS n FROM omnismart.amazon_orders WHERE sku = '{SKU}'"
    return {ch: int(next(iter(db.query(q)[0].values()))) for ch, q in sql.items()}


def _preview(db, last_alloc: dict) -> list[dict]:
    from src.tools import ToolRegistry, build_discovery_tools
    from src.tools.allocation_tools import build_allocation_tools
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "allocations.jsonl").write_text(json.dumps(last_alloc) + "\n")
        reg = ToolRegistry(build_discovery_tools(db, extra=build_allocation_tools(db, Path(tmp))))
        for run in (1, 2):
            ok, comp = reg.call("compute_allocation", {"sku": SKU})
            r = json.loads(comp)
            if not ok:
                msg = ("Zetaris cannot read omnismart.channel_economics: unit_margin is registered as a whole number but the "
                       "data has fractional dollars (ClassCastException); the live agent cannot run until this is fixed"
                       if "ClassCast" in comp else comp[:200])
                out.append(_check(f"engine preview run {run}", None, msg))
                break
            ok, setr = reg.call("set_channel_allocation", {"sku": SKU, "reason": f"preview run {run}"})
            w = json.loads(setr)
            out.append(_check(f"engine preview run {run}", None,
                              f"state {r['state']}, buffer {r['buffer_units']}, sellable {r['sellable_units']}, inbound credit "
                              f"{r['inbound_credit_units']}, cover {r['days_of_cover']}d -> applied {w.get('applied')} "
                              f"(stepped by 25% rule: {w.get('stepped_by_25pct_limit')})"))
    return out


def run_checks(db=None, with_zetaris: bool = True) -> list[dict]:
    now = seed.saved_now()
    if now is None:
        return [_check("scenario seeded", False, "run seed_lamp002.py first (no demo clock found)")]
    checks: list[dict] = []
    orders = [o for o in order_stores.load_all() if o["sku"] == SKU]

    for days, exp in EXPECT_UNITS.items():
        got = {ch: seed.window_units(orders, now, ch, days) for ch in CHANNELS}
        checks.append(_check(f"units sold, last {days} days", got == exp, f"got {got}" + ("" if got == exp else f" expected {exp}")))

    vel = {}
    for ch in CHANNELS:
        u = {d: seed.window_units(orders, now, ch, d) for d in (7, 30, 90)}
        vel[ch] = round(0.5 * u[7] / 7 + 0.3 * u[30] / 30 + 0.2 * u[90] / 90, 2)
    checks.append(_check("blended velocity per day (0.5*v7 + 0.3*v30 + 0.2*v90)", vel == EXPECT_VELOCITY,
                         f"got {vel}" + ("" if vel == EXPECT_VELOCITY else f" expected {EXPECT_VELOCITY}")))

    inv = next((r for r in _doc("wms_inventory.json", "inventory") if r["sku"] == SKU), None)
    sellable = None if inv is None else inv["on_hand"] - inv["committed"]
    checks.append(_check("sellable = on_hand - committed = 64", sellable == 64,
                         f"{inv and inv['on_hand']} - {inv and inv['committed']} = {sellable}"))

    stamp = next((r for r in reversed([json.loads(ln) for ln in (seed.OUTBOX / "allocations.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()])
                  if r.get("sku") == SKU and r.get("note") == seed.SEED_NOTE), None)
    caps_ok = stamp is not None and stamp["allocation"] == seed.CAPS
    checks.append(_check("starting caps stamped (DTC 30, Amazon 40, Etsy 15, Walmart 15)", caps_ok,
                         f"stamp {stamp and stamp['allocation']}"))
    remaining = {ch: seed.CAPS[ch] - seed.window_units(orders, now, ch, 5) for ch in CHANNELS}
    checks.append(_check("remaining caps sum to sellable (64)", sum(remaining.values()) == 64 and remaining == EXPECT_REMAINING,
                         f"remaining {remaining} sum {sum(remaining.values())}"))
    open_n = sum(1 for o in orders if o["status"] in ("open", "partial"))
    checks.append(_check("open orders = 0", open_n == 0, f"{open_n} open"))

    econ = {r["channel"]: r for r in _doc("channel_economics.json", "economics") if r["sku"] == SKU}
    econ_ok = all(ch in econ and econ[ch]["unit_margin"] == seed.MARGINS[ch] and econ[ch]["floor_units"] == 0 and
                  all(abs(econ[ch][k] - v) < 1e-3 for k, v in seed.velocities(orders, now, ch).items()) for ch in CHANNELS)
    checks.append(_check("margins (14/6/11/5) and velocities match order history, no floors", econ_ok,
                         {ch: econ.get(ch, {}).get("unit_margin") for ch in CHANNELS}))
    po = next((r for r in _doc("wms_inbound.json", "inbound") if r["sku"] == SKU), None)
    sup = next((r for r in _doc("supplier_reliability.json", "suppliers") if po and r["supplier"] == po["supplier"]), {})
    po_ok = bool(po) and po["po"] == "PO-7001" and po["qty"] == 200 and po["eta_days"] == 4 and po["status"] == "in_transit" \
        and sup.get("on_time_rate") == 0.90 and sup.get("typical_delay_days") == 1
    checks.append(_check("inbound PO-7001: 200 units in transit, ETA +4d, supplier 90% on-time / 1-day delay", po_ok, f"{po} {sup}"))

    if not with_zetaris:
        return checks
    own = db is None
    try:
        if own:
            from src.config import get_settings
            from src.data_connectors.zetaris_jdbc import ZetarisJdbcConnector
            db = ZetarisJdbcConnector(get_settings())
        src_counts = {ch: sum(1 for o in orders if o["channel"] == ch) for ch in CHANNELS}
        fed = _federated_counts(db)
        checks.append(_check("Zetaris federation returns the same order counts as the sources (Postgres x3 + Amazon REST)",
                             fed == src_counts, f"zetaris {fed} sources {src_counts}"))
        if stamp:
            checks += _preview(db, stamp)
    except Exception as e:
        checks.append(_check("Zetaris federation", False, f"{type(e).__name__}: {str(e)[:300]}"))
    finally:
        if own and db is not None:
            db.close()
    return checks


if __name__ == "__main__":
    results = run_checks()
    for c in results:
        tag = {True: "PASS", False: "FAIL", None: "INFO"}[c["ok"]]
        print(f"[{tag}] {c['name']}" + (f"\n        {c['detail']}" if c["detail"] != "" else ""))
    fails = sum(1 for c in results if c["ok"] is False)
    print(f"\n{sum(1 for c in results if c['ok'] is True)} passed, {fails} failed")
    sys.exit(1 if fails else 0)
