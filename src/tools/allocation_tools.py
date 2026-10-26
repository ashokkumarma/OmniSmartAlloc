"""OmniSmartAlloc tools: compute_allocation, set_channel_allocation, create_alert, log_decision.

Writes go to JSONL files in a store directory (simulated execution; never to Zetaris).
The 25% change guardrail, sellable cap and lock/stale checks are enforced here in code.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Annotated, Any, Callable

from pydantic import AfterValidator, BaseModel, Field

from src.allocation import agent_log, allocate, step_toward
from src.allocation.snapshot import build_snapshot, check_sku
from src.data_connectors.base import SqlConnector
from src.tools.registry import Tool

SkuId = Annotated[str, AfterValidator(check_sku)]


class SkuArgs(BaseModel):
    sku: SkuId = Field(description="SKU to allocate, e.g. MUG-001")


class SetAllocArgs(BaseModel):
    sku: SkuId = Field(description="SKU whose computed allocation should be applied")
    reason: str = Field(default="", description="Short note stored with the decision")


class AlertArgs(BaseModel):
    sku: SkuId
    problem: str
    recommended_action: str
    risk_of_inaction: str
    deadline: str


class LogArgs(BaseModel):
    sku: SkuId
    record: dict = Field(description="The full per-SKU JSON record you are returning")


class AllocationService:
    def __init__(self, db: SqlConnector, store_dir: Path, used_fn: Callable[[str, str], dict[str, int]] | None = None):
        self.db, self.dir, self.used_fn = db, store_dir, used_fn
        self.computed: dict[str, dict[str, Any]] = {}

    def _append(self, name: str, entry: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **entry}
        with (self.dir / name).open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def _last(self, sku: str) -> dict[str, Any] | None:
        p = self.dir / "allocations.jsonl"
        rows = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []
        return next((r for r in reversed(rows) if r["sku"] == sku), None)

    def _held(self, sku: str, sellable: int) -> dict[str, Any] | None:
        """The last written record, with `allocation` replaced by what each channel holds right now:
        written count minus units its orders consumed since, trimmed to the sellable pool."""
        last = self._last(sku)
        if not last:
            return None
        used = self.used_fn(sku, last["ts"]) if self.used_fn else {}
        held = {ch: max(0, n - used.get(ch, 0)) for ch, n in last["allocation"].items()}
        over = sum(held.values()) - sellable
        while over > 0:
            held[max(held, key=held.get)] -= 1
            over -= 1
        return {**last, "allocation": held, "written_allocation": last["allocation"]}

    @staticmethod
    def _context(res: dict[str, Any], last: dict[str, Any] | None) -> dict[str, Any]:
        return {"previous": last["allocation"] if last else None,
                "previous_written": last.get("written_allocation", last["allocation"]) if last else None, "previous_state": last["state"] if last else None,
                "days_of_cover": res["days_of_cover"], "reasoning": res["reasoning"],
                "uncredited_pos": [s["po"] for s in res["shipments"] if not s["credited"]],
                "uncredited_shipments": [{"po": s["po"], "qty": s["qty"], "eta": s["adjusted_eta_days"]}
                                         for s in res["shipments"] if not s["credited"]],
                "shipments_detail": [{"po": s["po"], "qty": s["qty"], "eta": s["adjusted_eta_days"], "credited": s["credited"]}
                                     for s in res["shipments"]],
                "channel_context": {c["name"]: {k: c[k] for k in ("unit_margin", "demand_confidence", "score", "forecast_per_day", "v7", "v90")}
                                    for c in res["channels"]}}

    def _net(self, res: dict[str, Any], last: dict[str, Any] | None, proposed: dict[str, int]) -> float:
        if not last:
            return 0.0
        ctx = {c["name"]: c for c in res["channels"]}
        return agent_log.projected_net_savings(last["allocation"], proposed, ctx, res["days_of_cover"])

    def _decline(self, a: "SetAllocArgs", res: dict[str, Any], last: dict[str, Any] | None,
                 proposed: dict[str, int], net: float) -> dict[str, Any]:
        """Non-positive projected savings: never applied and never offered for approval. Recorded only so
        compute_allocation can tell the agent not to re-propose it (never rendered as a card)."""
        reason = (f"Projected savings is negative (-${abs(net):.0f}); a losing move is never applied "
                  "or offered — auto-declined by the guardrails" if net < 0 else
                  "No projected savings from this change — the agent does not redistribute caps "
                  "without a benefit; skipped")
        for old in agent_log.pending(self.dir, a.sku):
            agent_log.mark(self.dir, old["id"], "superseded")
        aid = uuid.uuid4().hex[:8]
        self._append("approvals.jsonl", {"id": aid, "status": "auto-declined", "sku": a.sku, "state": res["state"],
                                         "allocation": proposed, "target": res["allocation"],
                                         "sellable_units": res["sellable_units"], "reason": a.reason,
                                         "deny_reason": reason, "approval_reasons": [reason],
                                         **self._context(res, last)})
        return {"written": False, "declined": True, "approval_id": aid, "reasons": [reason], "would_have_allocated": proposed}

    def _stage(self, a: "SetAllocArgs", res: dict[str, Any], last: dict[str, Any] | None,
               proposed: dict[str, int], reasons: list[str]) -> dict[str, Any]:
        net = self._net(res, last, proposed)
        if last and net <= 0:
            return self._decline(a, res, last, proposed, net)
        for old in agent_log.pending(self.dir, a.sku):
            agent_log.mark(self.dir, old["id"], "superseded")
        aid = uuid.uuid4().hex[:8]
        self._append("approvals.jsonl", {"id": aid, "status": "pending", "sku": a.sku, "state": res["state"], "allocation": proposed,
                                         "target": res["allocation"], "sellable_units": res["sellable_units"], "reason": a.reason,
                                         "approval_reasons": reasons, **self._context(res, last)})
        return {"written": False, "pending_approval": True, "approval_id": aid, "reasons": reasons + ["staged for human approval; allocation unchanged"],
                "would_have_allocated": proposed}

    def compute(self, a: SkuArgs) -> dict[str, Any]:
        res = allocate(build_snapshot(self.db, a.sku))
        res["recent_denied_proposals"] = agent_log.denied(self.dir, a.sku)
        # Orders/inventory may have changed since any pending proposal was staged. If today's
        # recommendation no longer matches what was proposed, that card no longer reflects the
        # current state of records -- retire it now instead of leaving a stale "needs approval".
        for p in agent_log.pending(self.dir, a.sku):
            if p.get("target") != res["allocation"]:
                agent_log.mark(self.dir, p["id"], "superseded")
        self.computed[a.sku] = res
        return res

    def set_allocation(self, a: SetAllocArgs) -> dict[str, Any]:
        res = self.computed.get(a.sku)
        if res is None:
            raise ValueError("call compute_allocation for this SKU first")
        if not res["write_allowed"]:
            return {"written": False, "reasons": res["write_blocked_reasons"], "would_have_allocated": res["allocation"]}
        target, last = res["allocation"], self._held(a.sku, res["sellable_units"])
        applied, stepped = target, False
        if last and last["state"] == res["state"]:
            held = last["allocation"]
            big = {ch: (held[ch], target.get(ch, 0)) for ch in {*held, *target}
                   if held.get(ch, 0) > 0 and abs(target.get(ch, 0) - held[ch]) > 0.25 * held[ch]}
            if big:
                reasons = [f"{ch} would move {abs(n - o)} of its {o} units ({round(abs(n - o) / o * 100)}% — over the 25% limit): human approval needed"
                           for ch, (o, n) in big.items()]
                return self._stage(a, res, last, target, reasons)
            applied = step_toward(last["allocation"], target, res["sellable_units"],
                                  floor_base=res["sellable_units"] / max(1, len(target)))
            if applied is None:
                return self._stage(a, res, last, target, ["25% change limit cannot be met within sellable stock; human approval needed"])
            stepped = applied != target
        if last:
            applied = {**{ch: 0 for ch in last["allocation"] if ch not in applied}, **applied}
        pauses = [ch for ch, v in applied.items() if v == 0 and ch in target and last and last["allocation"].get(ch, 0) > 0]
        if pauses:
            return self._stage(a, res, last, applied, [f"{', '.join(pauses)} paused (cap to 0): human sign-off required"])
        net = self._net(res, last, applied)
        if last and net <= 0:
            return self._decline(a, res, last, applied, net)
        assert sum(applied.values()) <= res["sellable_units"]
        self._append("allocations.jsonl", {"sku": a.sku, "state": res["state"], "allocation": applied, "target": target,
                                           "sellable_units": res["sellable_units"], "shared_pool": res["shared_pool"], "reason": a.reason,
                                           **self._context(res, last)})
        self._append("decisions.jsonl", {"sku": a.sku, "record": {k: res[k] for k in res if k not in ("shipments", "channels")}})
        return {"written": True, "applied": applied, "target": target, "stepped_by_25pct_limit": stepped, "state": res["state"]}

    def alert(self, a: AlertArgs) -> dict[str, Any]:
        self._append("alerts.jsonl", a.model_dump())
        return {"alert_created": True, "sku": a.sku}

    def log(self, a: LogArgs) -> dict[str, Any]:
        self._append("decisions.jsonl", {"sku": a.sku, "record": a.record})
        return {"logged": True, "sku": a.sku}


def build_allocation_tools(db: SqlConnector, store_dir: Path, used_fn: Callable[[str, str], dict[str, int]] | None = None) -> list[Tool]:
    s = AllocationService(db, store_dir, used_fn)
    return [
        Tool("compute_allocation",
             "Pull fresh data for a SKU from Zetaris and run the full allocation logic (committed units, inbound credit, state, allocation, guardrails). Returns the per-SKU record. Do not do this math yourself.",
             SkuArgs, s.compute),
        Tool("set_channel_allocation",
             "Apply the computed allocation for a SKU (call compute_allocation first). Enforces guardrails: sellable cap, locked and stale-data blocks, and staged approval when a channel's target is 0 (pause) or moves more than 25% of its held units. A change whose projected savings is not positive is never applied or offered for approval — the agent does not redistribute without a benefit.",
             SetAllocArgs, s.set_allocation),
        Tool("create_alert", "Notify a human. State SKU, problem, recommended action, risk of doing nothing, and deadline.", AlertArgs, s.alert),
        Tool("log_decision", "Store the full reasoning record for a SKU decision.", LogArgs, s.log),
    ]
