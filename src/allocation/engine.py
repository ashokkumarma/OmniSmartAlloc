"""Deterministic OmniSmartAlloc engine: Steps 1-4 and guardrails from the agent system prompt.

Pure functions, no I/O. The LLM never does this arithmetic; it calls compute_allocation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


FLOOR_PCT, P80_FACTOR, DEFAULT_HORIZON, FLEX = 0.15, 1.2, 14, 0.20
NO_DEMAND_DOC = 9999.0
STATES = ("Abundant", "Balanced", "Tight", "Critical")


def _ceil(x: float) -> int:
    return math.ceil(round(x, 6))


def _floor(x: float) -> int:
    return math.floor(round(x, 6))


def base_confidence(status: str, eta_days: float) -> float:
    s = status.strip().lower()
    if s in ("in_transit", "shipped"):
        return 0.90 if eta_days <= 7 else 0.75 if eta_days <= 21 else 0.50
    return {"confirmed": 0.50, "po_placed": 0.25}.get(s, 0.0)


@dataclass
class Inbound:
    po: str
    qty: float
    eta_days: float
    status: str
    on_time_rate: float = 0.70
    delay_days: float = 7.0


@dataclass
class Channel:
    name: str
    unit_margin: float
    demand_confidence: float
    v7: float
    v30: float
    v90: float
    trend: float = 1.0
    uplift: float = 1.0
    floor_units: int = 0

    @property
    def forecast_daily(self) -> float:
        return (0.5 * self.v7 + 0.3 * self.v30 + 0.2 * self.v90) * self.trend * self.uplift

    @property
    def score(self) -> float:
        return self.unit_margin * self.demand_confidence


@dataclass
class SkuInput:
    sku: str
    on_hand: float
    committed: float
    inbound: list[Inbound]
    channels: list[Channel]
    promo_multiplier: float = 1.0
    clearance: bool = False
    locked: bool = False
    stock_age_hours: float = 0.0
    margin_age_hours: float = 0.0
    fallbacks: list[str] = field(default_factory=list)
    committed_missing: bool = False


def _share_alloc(chs: list[Channel], sellable: int) -> dict[str, int]:
    total = sum(c.forecast_daily for c in chs)
    w = {c.name: (c.forecast_daily / total if total > 0 else 1 / len(chs)) for c in chs}
    alloc = {n: _floor(sellable * x) for n, x in w.items()}
    for n in sorted(w, key=lambda k: (-w[k], k))[: sellable - sum(alloc.values())]:
        alloc[n] += 1
    return alloc


def _fund(ranked: list[Channel], sellable: int, horizon: float, critical: bool) -> dict[str, int]:
    p50 = {c.name: _ceil(c.forecast_daily * horizon) for c in ranked}
    p80 = {c.name: _ceil(c.forecast_daily * horizon * P80_FACTOR) for c in ranked}
    paused = ranked[-1].name if critical and len(ranked) > 1 else None
    alloc = {c.name: 0 for c in ranked}
    remaining = sellable
    for c in ranked:
        if c.name == paused:
            continue
        fl = min(remaining, max(c.floor_units, _ceil(FLOOR_PCT * p50[c.name])))
        alloc[c.name] += fl
        remaining -= fl
    top = _ceil(len(ranked) / 2)
    for i, c in enumerate(ranked):
        if c.name == paused:
            continue
        add = max(0, min(remaining, (p80 if i < top else p50)[c.name] - alloc[c.name]))
        alloc[c.name] += add
        remaining -= add
    return alloc


def allocate(inp: SkuInput) -> dict[str, Any]:
    reasoning: list[str] = []
    risks: list[str] = []
    human: list[str] = []
    alerts: list[dict[str, Any]] = []

    buffer = 0
    sellable = max(0, _floor(inp.on_hand - inp.committed))
    reasoning.append(f"Sellable = {inp.on_hand:g} on hand - {inp.committed:g} committed = {sellable}")

    total_demand = sum(c.forecast_daily for c in inp.channels)
    stockout_days = sellable / total_demand if total_demand > 0 else NO_DEMAND_DOC

    shipments, credit = [], 0.0
    ttr: float | None = None
    for s in inp.inbound:
        adj_eta = s.eta_days + s.delay_days
        conf = base_confidence(s.status, s.eta_days) * s.on_time_rate
        credited = conf > 0 and adj_eta <= stockout_days
        credit += s.qty * conf if credited else 0.0
        if conf >= 0.5:
            ttr = adj_eta if ttr is None else min(ttr, adj_eta)
        shipments.append({"po": s.po, "qty": s.qty, "adjusted_eta_days": round(adj_eta, 1),
                          "confidence": round(conf, 3), "credited": credited})
        if not credited and conf > 0:
            reasoning.append(f"{s.po}: adjusted ETA {adj_eta:g}d is after projected stock-out ({stockout_days:.1f}d) or low confidence; no credit")
    credit_units = _floor(credit)
    doc = (sellable + credit) / total_demand if total_demand > 0 else NO_DEMAND_DOC

    if doc < 10 and ttr is None:
        state = "Critical"
    elif doc >= 60 or (ttr is not None and doc - ttr >= 14):
        state = "Abundant"
    elif doc >= 30 and (ttr is None or doc >= ttr):
        state = "Balanced"
    else:
        state = "Tight"
    horizon = ttr if ttr is not None else DEFAULT_HORIZON
    reasoning.append(f"Days of cover {doc:.1f}, time to replenish {ttr if ttr is not None else 'none'} -> {state}")

    dead = doc > 120 or all(c.v30 == 0 for c in inp.channels)
    eligible = [c for c in inp.channels if c.unit_margin > 0 or inp.clearance]
    excluded = [c.name for c in inp.channels if c not in eligible]
    if excluded:
        reasoning.append(f"Zero/negative margin, no sales allowed: {', '.join(excluded)}")
    ranked = sorted(eligible, key=lambda c: (-c.score, c.name))

    shared_pool, flex = False, {}
    if not eligible:
        allocation = {c.name: 0 for c in inp.channels}
        risks.append("No channel has positive margin")
    elif state == "Abundant" or dead:
        allocation = _share_alloc(eligible, sellable)
        shared_pool = True
        reasoning.append("Single shared pool; allocation shown is the demand-share view" +
                         ("; dead-inventory sell-through overrides margin" if dead else ""))
    elif state == "Balanced":
        allocation = _share_alloc(eligible, sellable)
        flex = {n: [_floor(v * (1 - FLEX)), _ceil(v * (1 + FLEX))] for n, v in allocation.items()}
        reasoning.append("Soft targets = forecast demand share, +/-20% flexibility; margin only breaks ties")
    else:
        allocation = _fund(ranked, sellable, horizon, state == "Critical")
        reasoning.append("Ranked by margin-adjusted score: " + " > ".join(c.name for c in ranked))
        if state == "Critical" and len(ranked) > 1:
            reasoning.append(f"Critical: {ranked[-1].name} paused (needs human sign-off)")
    allocation = {c.name: allocation.get(c.name, 0) for c in inp.channels}

    gap_days = (ttr - doc) if ttr is not None else None
    if state == "Critical" or (gap_days is not None and gap_days > 0):
        gap_txt = f"projected gap of about {gap_days:.0f} days (~{_ceil(gap_days * total_demand)} units)" if gap_days and gap_days > 0 else "no credible inbound"
        risks.append(gap_txt[0].upper() + gap_txt[1:])
        action = "Expedite inbound PO" if ttr is not None else "Place or confirm an inbound PO"
        human.append(action)
        alerts.append({"sku": inp.sku, "problem": f"{state} supply state: {gap_txt}", "recommended_action": action,
                       "risk_of_inaction": f"Stock-out in about {stockout_days:.1f} days; lost sales on underfunded channels",
                       "deadline": f"within {max(1, _floor(stockout_days))} days"})
    if dead:
        human.append("Recommend markdown, bundle, promotion or liquidation channel")
        risks.append("Dead inventory: DOC above 120 or no sales for 30 days")

    write_allowed, blocked = True, []
    if inp.locked:
        write_allowed = False
        blocked.append("SKU is locked/protected/manually overridden: report only")
    if inp.stock_age_hours > 1 or inp.margin_age_hours > 24:
        write_allowed = False
        blocked.append("Stale data (stock >1h or margins >24h): keep last safe allocation")
        alerts.append({"sku": inp.sku, "problem": "Stale input data", "recommended_action": "Refresh WMS/margin feeds",
                       "risk_of_inaction": "Allocation frozen at last safe value", "deadline": "next run"})
    assert sum(allocation.values()) <= sellable, "guardrail: allocation exceeds sellable"

    confidence = "low" if inp.committed_missing or not write_allowed else "medium" if inp.fallbacks or state in ("Tight", "Critical") else "high"
    return {
        "sku": inp.sku, "state": state, "sellable_units": sellable, "buffer_units": buffer,
        "days_of_cover": round(doc, 1), "time_to_replenish_days": None if ttr is None else round(ttr, 1),
        "inbound_credit_units": credit_units, "allocation": allocation, "shared_pool": shared_pool,
        "flex_range": flex, "confidence": confidence, "reasoning": reasoning, "risks": risks,
        "recommended_human_actions": human, "guardrails_checked": True,
        "write_allowed": write_allowed, "write_blocked_reasons": blocked, "fallbacks_used": inp.fallbacks,
        "alerts": alerts, "horizon_days": round(horizon, 1), "shipments": shipments,
        "channels": [{"name": c.name, "unit_margin": c.unit_margin, "demand_confidence": c.demand_confidence,
                      "score": round(c.score, 2), "forecast_per_day": round(c.forecast_daily, 2),
                      "v7": round(c.v7, 3), "v90": round(c.v90, 3),
                      "demand_p50": _ceil(c.forecast_daily * horizon),
                      "demand_p80": _ceil(c.forecast_daily * horizon * P80_FACTOR)} for c in inp.channels],
    }


def step_toward(current: dict[str, int], target: dict[str, int], sellable: int, limit: float = 0.25,
                floor_base: float = 0) -> dict[str, int] | None:
    """Limit each channel to +/-25% of what it holds; a channel holding less than `floor_base` is treated
    as holding that much for the upward limit only (so a nearly-dry channel can be refilled); an empty channel is re-funded freely.
    None if sellable cannot be respected."""
    new = {}
    for ch, t in target.items():
        c = current.get(ch, 0)
        base = max(c, floor_base)
        new[ch] = t if c == 0 else min(max(t, _floor(c * (1 - limit))), _ceil(base * (1 + limit)))
    over = sum(new.values()) - sellable
    for ch in sorted((k for k in new if new[k] > current.get(k, 0)), key=lambda k: -(new[k] - current.get(k, 0))):
        if over <= 0:
            break
        cut = min(over, new[ch] - current.get(ch, 0))
        new[ch] -= cut
        over -= cut
    return new if over <= 0 else None
