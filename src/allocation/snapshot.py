"""Load one SKU's fragmented inputs from Zetaris views and apply the prompt's documented fallbacks."""
from __future__ import annotations

import re
from typing import Any

from src.allocation.engine import Channel, Inbound, SkuInput
from src.data_connectors.base import SqlConnector

SCHEMA = "omnismart"
_SKU = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
DEFAULT_ON_TIME, DEFAULT_DELAY = 0.70, 7.0


class MissingInput(RuntimeError):
    pass


def check_sku(sku: str) -> str:
    if not _SKU.match(sku):
        raise ValueError(f"invalid sku '{sku}'")
    return sku


def _f(v: Any) -> float | None:
    try:
        return None if v is None or str(v).strip() == "" else float(v)
    except (TypeError, ValueError):
        return None


def _b(v: Any) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def _rows(db: SqlConnector, sql: str) -> list[dict[str, Any]]:
    return [{k.lower(): v for k, v in r.items()} for r in db.query(sql, 200)]


def build_snapshot(db: SqlConnector, sku: str) -> SkuInput:
    check_sku(sku)
    fb: list[str] = []
    inv = _rows(db, f"SELECT sku, on_hand, committed, unputaway, age_hours FROM {SCHEMA}.wms_inventory WHERE sku = '{sku}'")
    on_hand = _f(inv[0].get("on_hand")) if inv else None
    if on_hand is None:
        raise MissingInput(f"{sku}: on-hand stock missing. Do not allocate without it.")
    committed = _f(inv[0].get("committed"))
    committed_missing = committed is None
    if committed_missing:
        committed = 0.0
        fb.append("committed units missing: treated as zero (low confidence)")

    sup = {r["supplier"]: r for r in _rows(db, f"SELECT supplier, on_time_rate, typical_delay_days FROM {SCHEMA}.supplier_reliability")}
    inbound: list[Inbound] = []
    for r in _rows(db, f"SELECT po, sku, qty, eta_days, status, supplier FROM {SCHEMA}.wms_inbound WHERE sku = '{sku}'"):
        s = sup.get(r.get("supplier"), {})
        rate, delay = _f(s.get("on_time_rate")), _f(s.get("typical_delay_days"))
        if rate is None or delay is None:
            fb.append(f"{r.get('po')}: supplier reliability missing, assumed {DEFAULT_ON_TIME:.0%} on-time and {DEFAULT_DELAY:g}-day delay")
        inbound.append(Inbound(str(r.get("po")), _f(r.get("qty")) or 0.0, _f(r.get("eta_days")) or 0.0, str(r.get("status")),
                               DEFAULT_ON_TIME if rate is None else rate, DEFAULT_DELAY if delay is None else delay))
    unputaway = _f(inv[0].get("unputaway")) or 0.0
    if unputaway > 0:
        inbound.append(Inbound("UNPUTAWAY", unputaway, 1.0, "in_transit", 1.0, 0.0))

    channels: list[Channel] = []
    margin_age = 0.0
    for r in _rows(db, f"SELECT sku, channel, unit_margin, demand_confidence, v7, v30, v90, trend, floor_units, margin_age_hours "
                       f"FROM {SCHEMA}.channel_economics WHERE sku = '{sku}'"):
        name, margin = str(r.get("channel")), _f(r.get("unit_margin"))
        if margin is None:
            raise MissingInput(f"{sku}/{name}: unit margin missing")
        v30 = _f(r.get("v30"))
        if v30 is None:
            v30 = 0.0
            fb.append(f"{name}: velocity missing, treated as zero")
        v7, v90 = _f(r.get("v7")), _f(r.get("v90"))
        if v7 is None or v90 is None:
            fb.append(f"{name}: 7/90-day velocity missing, using 30-day only")
        channels.append(Channel(name, margin, _f(r.get("demand_confidence")) or 0.4, v30 if v7 is None else v7, v30,
                                v30 if v90 is None else v90, _f(r.get("trend")) or 1.0, 1.0, int(_f(r.get("floor_units")) or 0)))
        margin_age = max(margin_age, _f(r.get("margin_age_hours")) or 0.0)
    if not channels:
        raise MissingInput(f"{sku}: no channel economics found")

    rules = _rows(db, f"SELECT sku, locked, manual_override, clearance, promo_multiplier FROM {SCHEMA}.sku_rules WHERE sku = '{sku}'")
    if not rules:
        fb.append("no business rules row: defaults used")
    r0 = rules[0] if rules else {}
    return SkuInput(sku, on_hand, committed, inbound, channels,
                    promo_multiplier=_f(r0.get("promo_multiplier")) or 1.0, clearance=_b(r0.get("clearance")),
                    locked=_b(r0.get("locked")) or _b(r0.get("manual_override")),
                    stock_age_hours=_f(inv[0].get("age_hours")) or 0.0, margin_age_hours=margin_age,
                    fallbacks=fb, committed_missing=committed_missing)
