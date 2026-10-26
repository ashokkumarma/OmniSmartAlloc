"""Agent log: turns the agent's outbox records into per-channel events and handles human approvals.

Approval classes:
  Auto-apply and log     the channel cap went up (written, recorded here)
  Auto-apply and notify  the channel cap went down but stays above zero (written, flagged here)
  Needs approval         a channel pause (cap to 0) or a 25%-rule conflict: staged in approvals.jsonl,
                         not written until a human approves
Est. savings = units gained x the receiving channel's unit margin. On a held proposal the primary row
carries the total ("up to $X if approved") and the other rows say where it is included.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

PACE_HIGH, PACE_LOW = 1.25, 0.75


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()] if path.exists() else []


def approvals(store: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in read_jsonl(store / "approvals.jsonl"):
        if r["id"] not in out:
            out[r["id"]] = dict(r)
        else:
            r = {**out[r["id"]], **r, "ts": out[r["id"]]["ts"], "decided_ts": r.get("ts")}
            out[r["id"]] = r
    return out


def pending(store: Path, sku: str | None = None) -> list[dict[str, Any]]:
    return [a for a in approvals(store).values() if a["status"] == "pending" and (sku is None or a["sku"] == sku)]


def mark(store: Path, approval_id: str, status: str, deny_reason: str | None = None) -> None:
    rec = {"id": approval_id, "status": status, "ts": now_iso()}
    if deny_reason:
        rec["deny_reason"] = deny_reason
    with (store / "approvals.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def deny(store: Path, approval_id: str, reason: str) -> tuple[int, dict[str, Any]]:
    a = approvals(store).get(approval_id)
    if a is None:
        return 404, {"error": "approval not found"}
    if a["status"] != "pending":
        return 409, {"error": f"already {a['status']}"}
    if not reason:
        return 400, {"error": "a reason is required so the agent can learn from the denial"}
    mark(store, approval_id, "denied", reason)
    return 200, {"denied": approval_id, "sku": a["sku"], "reason": reason}


def denied(store: Path, sku: str, limit: int = 3) -> list[dict[str, Any]]:
    """Recent human denials and guardrail auto-declines for a SKU, fed back into
    compute_allocation so the agent does not re-propose losing moves."""
    return [{"ts": a["ts"], "deny_reason": a.get("deny_reason"), "would_have_allocated": a["allocation"]}
            for a in approvals(store).values() if a["sku"] == sku and a["status"] in ("denied", "auto-declined")][-limit:]


def last_allocation(store: Path, sku: str) -> dict[str, Any] | None:
    return next((r for r in reversed(read_jsonl(store / "allocations.jsonl")) if r.get("sku") == sku), None)


def approve(store: Path, approval_id: str) -> tuple[int, dict[str, Any]]:
    a = approvals(store).get(approval_id)
    if a is None:
        return 404, {"error": "approval not found"}
    if a["status"] != "pending":
        return 409, {"error": f"already {a['status']}"}
    last = last_allocation(store, a["sku"])
    if last and a.get("previous") is not None and last["allocation"] != a["previous"]:
        mark(store, approval_id, "superseded")
        return 409, {"error": "the allocation changed since this proposal was made; run the allocation cycle again"}
    record = {"ts": now_iso(), "sku": a["sku"], "state": a["state"], "allocation": a["allocation"], "target": a["target"],
              "sellable_units": a["sellable_units"], "shared_pool": False, "stepped_by_25pct_limit": False,
              "reason": "approved by a human", "note": "human-approved", "approval_id": approval_id,
              "previous": a["previous"], "previous_state": a["previous_state"]}
    with (store / "allocations.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    mark(store, approval_id, "approved")
    return 200, {"approved": approval_id, "sku": a["sku"], "allocation": a["allocation"]}


def _trigger(ch: str, c: dict, rec: dict, pace: float | None, is_pause: bool) -> str:
    pos, changed = rec.get("uncredited_pos") or [], rec.get("previous_state") != rec["state"]
    if is_pause and pos:
        return f"{', '.join(pos)} won't arrive before stock runs out"
    if is_pause and changed:
        return f"Stock dropped to {rec['state']} (was {rec.get('previous_state')})"
    if pace is not None and (pace >= PACE_HIGH or pace <= PACE_LOW):
        return f"{ch} selling at {round(pace * 100)}% of its usual pace"
    if pos:
        return f"{', '.join(pos)} won't arrive before stock runs out"
    if changed:
        return f"Stock level changed: {rec.get('previous_state')} \u2192 {rec['state']}"
    return "Rebalancing across channels by profit and demand"


def projected_net_savings(prev: dict, new: dict, ctx: dict, doc: float | None) -> float:
    """Demand-capped net margin gain of a reallocation: receiver gains minus donor losses,
    each capped at the units a channel can realistically sell (forecast/day x days of cover)."""
    net = 0.0
    for ch, n in new.items():
        o = prev.get(ch, 0)
        if n == o or ch not in ctx:
            continue
        c = ctx[ch]
        cap = c["forecast_per_day"] * doc if doc else None
        if n > o:
            net += max(0.0, min(n - o, cap - o) if cap is not None else n - o) * c["unit_margin"]
        else:
            net -= max(0.0, min(o - n, cap - n) if cap is not None else o - n) * c["unit_margin"]
    return net


def _why(rec: dict, channels: list, ctx: dict, donors_all: dict, receivers_all: dict,
         losses: dict, doc: float | None, status: str, realized) -> list[str]:
    """Reader-friendly bullets: trigger, why each reduced channel doesn't lose real sales,
    and how many extra sales each added channel gains. Facts only, no dollars."""
    bullets = []
    tot = sum(c["forecast_per_day"] for c in ctx.values())
    sellable = rec.get("sellable_units") or sum(rec["allocation"].values())
    ships = rec.get("uncredited_shipments") or []
    pos = rec.get("uncredited_pos") or []
    all_ships = rec.get("shipments_detail") or []
    nxt = min(all_ships, key=lambda s: s["eta"]) if all_ships else None
    if ships:
        trigger = ("Next inbound purchase order "
                   + ", ".join(f"{s['po']} ({s['qty']:g} units, expected in ~{s['eta']:g} days)" for s in ships)
                   + " — too late to help, so it gets zero supply credit. Until it lands, units are concentrated on "
                     "higher-scoring channels. That's why only this ~{doc}-day window matters.")
        trigger = trigger.format(doc=f"{doc:g}")
    elif pos:
        trigger = (f"Inbound purchase order {', '.join(pos)} won't arrive before stock runs out, so it gets zero "
                   "supply credit — until it lands, units are concentrated on higher-scoring channels.")
    elif nxt:
        trigger = (f"Next inbound purchase order {nxt['po']} ({nxt['qty']:g} units) is expected in ~{nxt['eta']:g} days"
                   + (" and is counted toward supply." if nxt.get("credited") else
                      " — too late to help, so it gets zero supply credit. Until it lands, units are concentrated on "
                      "higher-scoring channels."))
    elif rec.get("previous_state") and rec["previous_state"] != rec["state"]:
        trigger = f"Stock level moved from {rec['previous_state']} to {rec['state']}."
    else:
        trigger = "Rebalancing stock across channels by demand and margin."
    bullets.append(f"Trigger: {sellable:g} sellable units on hand vs ~{tot:g} units/day total demand — "
                   f"the stock lasts about {doc:g} days at today's demand, and that's the window this plan covers. {trigger}")
    for d, (o, n) in donors_all.items():
        fpd = ctx[d]["forecast_per_day"]
        need = fpd * doc if doc else 0
        if losses.get(d, 0) == 0:
            bullets.append(f"{d} sells ~{fpd:g}/day — it needs only ~{need:.0f} units over the next {doc:g} days, "
                           f"so cutting its limit {o} → {n} gives up no real sales.")
        else:
            covered = max(0.0, need - (o - n)) if doc else 0
            bullets.append(f"{d} sells ~{fpd:g}/day (~{need:.0f} units over the window) — its new limit of {n} "
                           f"still covers roughly all of that demand; the cut costs at most ~{realized(d, n, o - n):g} sales.")
    for r, (o, n) in receivers_all.items():
        c = ctx[r]
        extra = realized(r, o, n - o)
        bullets.append(f"{r} sells ~{c['forecast_per_day']:g}/day — the {n - o} units moved here "
                       f"enable up to ~{extra:g} more sales.")
    if status == "pending":
        bullets.append("Nothing is written until a human approves.")
    return bullets or [channels[0]["reason"]]


def _event(rec: dict, status: str, aid: str | None = None, approved_ts: str | None = None) -> dict[str, Any] | None:
    """One event card per agent decision: all channel cap changes of a single write/proposal together."""
    prev, new, ctx = rec.get("previous"), rec["allocation"], rec["channel_context"]
    if not prev:
        return None
    changes = {ch: (prev.get(ch, 0), new[ch]) for ch in new if prev.get(ch, 0) != new[ch] and ch in ctx}
    if not changes:
        return None
    held = status in ("pending", "approved", "denied")
    doc = rec.get("days_of_cover")
    # Demand ceiling per channel = forecast units/day x days of cover: units above this would not have
    # sold regardless of the cap, so they do not count as real gain (receiver) or real loss (donor).
    capacity = {ch: ctx[ch]["forecast_per_day"] * doc for ch in ctx} if doc else {}

    def realized(ch: str, at: float, delta: float) -> float:
        cap = capacity.get(ch)
        return delta if cap is None else max(0.0, min(delta, cap - at))

    donors_all = {ch: (o, n) for ch, (o, n) in changes.items() if n < o}
    receivers_all = {ch: (o, n) for ch, (o, n) in changes.items() if n > o}
    gains = {ch: realized(ch, o, n - o) * ctx[ch]["unit_margin"] for ch, (o, n) in receivers_all.items()}
    losses = {ch: realized(ch, n, o - n) * ctx[ch]["unit_margin"] for ch, (o, n) in donors_all.items()}
    best_rx = max(gains, key=lambda ch: ctx[ch]["unit_margin"]) if gains else None
    donors = sorted(donors_all, key=lambda c: -(donors_all[c][0] - donors_all[c][1]))
    receivers = sorted(receivers_all, key=lambda c: -(receivers_all[c][1] - receivers_all[c][0]))
    moves = {"reduce": [{"channel": d, "units": donors_all[d][0] - donors_all[d][1]} for d in donors],
             "add": [{"channel": r, "units": receivers_all[r][1] - receivers_all[r][0]} for r in receivers]}
    pauses = [ch for ch, (o, n) in changes.items() if n == 0]
    primary = (pauses or sorted(changes, key=lambda ch: -abs(changes[ch][1] - changes[ch][0])))[0]
    total = sum(gains.values())
    lines = rec.get("reasoning") or []
    channels = []
    for ch, (o, n) in changes.items():
        c = ctx[ch]
        pace = c["v7"] / c["v90"] if c.get("v90") else None
        inc, is_pause = n > o, n == 0
        m = f"${c['unit_margin']:g}"
        if is_pause:
            reason = (f"Stock is projected to run out in about {doc} days and no delivery arrives in time. "
                      f"{ch} earns the least per unit ({m}), so its sales limit drops to 0 and its units go to "
                      f"channels that make more per sale. A human must approve before this takes effect.")
        elif inc and pace is not None and pace >= PACE_HIGH:
            reason = (f"{ch} is selling {c['v7']:.1f} units/day, vs its usual {c['v90']:.1f}/day. "
                      f"Units are moved here so the faster-selling channel does not run out.")
        elif inc:
            reason = (f"{ch} earns more per unit ({m}) for its demand than the other channels, "
                      f"so it gets a bigger share of the ~{doc} days of stock left.")
        elif pace is not None and pace <= PACE_LOW:
            reason = (f"{ch} is only selling {c['v7']:.1f}/day ({round(pace * 100)}% of its usual pace), "
                      f"so the {o - n} units it likely won't sell move to {best_rx or 'a more profitable channel'}.")
        else:
            to = f"{best_rx}, which earns more per unit" if best_rx else "higher-earning channels"
            reason = (f"With stock tighter, {ch} gives up {o - n} unit{'s' if o - n != 1 else ''} to {to}.")
        if held and ch == primary and rec.get("approval_reasons") and not any(w in reason.lower() for w in ("approv", "paus")):
            reason += " " + "; ".join(rec["approval_reasons"]) + "."
        if inc:
            r_units = realized(ch, o, n - o)
            label = f"${gains[ch]:.0f}"
            calc = [f"{n - o} unit{'s' if n - o != 1 else ''} added to {ch}, of which {r_units:g} are within its demand "
                    f"({c['forecast_per_day']:g}/day \u00d7 {doc}d cover) \u00d7 ${c['unit_margin']:g}/unit \u2248 ${gains[ch]:.0f}",
                    "assumes the realistically sellable units actually sell"]
        else:
            best_m = ctx[best_rx]["unit_margin"] if best_rx else 0
            r_units = realized(ch, n, o - n)
            label = f"frees {o - n} unit{'s' if o - n != 1 else ''}"
            calc = [f"{o - n} unit{'s' if o - n != 1 else ''} cut from {ch}; only {r_units:g} were within its demand "
                    f"({c['forecast_per_day']:g}/day \u00d7 {doc}d cover), so that is the real loss here",
                    f"moved to {', '.join(receivers) or 'no channel'} (up to ${best_m:g}/unit there)",
                    "counted once in the receiving channels' savings"]
        if held:
            if ch == primary:
                label = {"pending": f"up to ${total:.0f} if approved", "approved": f"${total:.0f}", "denied": f"${total:.0f} declined"}[status]
                calc = [f"{r} +{receivers_all[r][1] - receivers_all[r][0]} units \u00d7 ${ctx[r]['unit_margin']:g}/unit (demand-capped) = ${gains[r]:.0f}" for r in receivers]
                calc += [f"proposal total \u2248 ${total:.0f}", "estimate caps gains/losses at each channel's demand (forecast/day \u00d7 days of cover)"]
            else:
                calc = calc + [f"part of this proposal's total (\u2248${total:.0f}), shown on the {primary} card"]
            amount = total if ch == primary else gains.get(ch)
        else:
            amount = gains.get(ch)
        row_approval = "Auto-apply and log" if inc else "Auto-apply and notify"
        channels.append({"channel": ch, "cap_from": o, "cap_to": n,
                         "kind": "pause" if is_pause else ("increase" if inc else "decrease"),
                         "trigger": _trigger(ch, c, rec, pace, is_pause), "reason": reason,
                         "score": round(c["score"], 1), "conf": round(c.get("demand_confidence") or (c["score"] / c["unit_margin"] if c["unit_margin"] else 0), 2),
                         "margin": c["unit_margin"], "savings": label, "savings_amount": amount, "calc": calc,
                         "row_approval": row_approval, "primary": held and ch == primary})
    baseline = sum(losses.values())
    total, baseline = round(total), round(baseline)
    net = total - baseline
    with_lines = [f"{r} +{receivers_all[r][1] - receivers_all[r][0]} units \u00d7 ${ctx[r]['unit_margin']:g}/unit (demand-capped) = ${gains[r]:.0f}" for r in receivers] or ["no units moved to other channels"]
    without_lines = [f"{d} keeps {donors_all[d][0] - donors_all[d][1]} units \u00d7 ${ctx[d]['unit_margin']:g}/unit, but only "
                     f"{realized(d, donors_all[d][1], donors_all[d][0] - donors_all[d][1]):g} were sellable at its demand "
                     f"({ctx[d]['forecast_per_day']:g}/day \u00d7 {doc}d) = ${losses[d]:.0f}" for d in donors] or ["nothing changes for the other channels"]
    ev_approval = {"pending": "Needs approval", "approved": "Approved", "denied": "Denied"}.get(status, "Auto-apply")
    return {"id": aid or f"{rec['ts']}-{rec['sku']}", "ts": rec["ts"], "sku": rec["sku"], "status": status,
            "without_change": {"lines": without_lines, "total": round(baseline)},
            "with_change": {"lines": with_lines, "total": round(total)},
            "baseline_savings": round(baseline), "net_savings": round(net),
            "approval": ev_approval,
            "action": {"auto": "Written", "pending": "Needs approval", "approved": "Written (approved)", "denied": "Denied"}
                      ["auto" if not held else status],
            "state_from": rec.get("previous_state"), "state_to": rec["state"], "channels": channels, "moves": moves,
            "trigger": " · ".join(dict.fromkeys(c["trigger"] for c in channels)),
            "why": _why(rec, channels, ctx, donors_all, receivers_all, losses, doc, status, realized),
            "total_savings": round(total), "primary_channel": primary, "approval_id": aid,
            "deny_reason": rec.get("deny_reason"), "approved_ts": approved_ts,
            "reason": rec.get("reason") or ""}


def events(store: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in read_jsonl(store / "allocations.jsonl"):
        if "channel_context" in r and not r.get("approval_id"):
            if e := _event(r, "auto"):
                out.append(e)
    for aid, a in approvals(store).items():
        if a["status"] in ("pending", "approved", "denied") and "channel_context" in a:
            if e := _event(a, a["status"], aid, a.get("decided_ts")):
                out.append(e)
    return sorted(out, key=lambda e: e["ts"], reverse=True)
