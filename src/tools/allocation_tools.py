"""OmniSmartAlloc tools: compute_allocation, set_channel_allocation, create_alert, log_decision.

Writes go to JSONL files in a store directory (simulated execution; never to Zetaris).
The 25% change guardrail, sellable cap and lock/stale checks are enforced here in code.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, Field

from src.allocation import allocate, step_toward
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
    def __init__(self, db: SqlConnector, store_dir: Path):
        self.db, self.dir = db, store_dir
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

    def compute(self, a: SkuArgs) -> dict[str, Any]:
        res = allocate(build_snapshot(self.db, a.sku))
        self.computed[a.sku] = res
        return res

    def set_allocation(self, a: SetAllocArgs) -> dict[str, Any]:
        res = self.computed.get(a.sku)
        if res is None:
            raise ValueError("call compute_allocation for this SKU first")
        if not res["write_allowed"]:
            return {"written": False, "reasons": res["write_blocked_reasons"], "would_have_allocated": res["allocation"]}
        target, last = res["allocation"], self._last(a.sku)
        applied, stepped = target, False
        if last and last["state"] == res["state"]:
            applied = step_toward(last["allocation"], target, res["sellable_units"])
            if applied is None:
                return {"written": False, "reasons": ["25% change limit cannot be met within sellable stock; human approval needed"],
                        "would_have_allocated": target}
            stepped = applied != target
        assert sum(applied.values()) <= res["sellable_units"]
        self._append("allocations.jsonl", {"sku": a.sku, "state": res["state"], "allocation": applied, "target": target,
                                           "sellable_units": res["sellable_units"], "shared_pool": res["shared_pool"], "reason": a.reason})
        self._append("decisions.jsonl", {"sku": a.sku, "record": {k: res[k] for k in res if k not in ("shipments", "channels")}})
        return {"written": True, "applied": applied, "target": target, "stepped_by_25pct_limit": stepped, "state": res["state"]}

    def alert(self, a: AlertArgs) -> dict[str, Any]:
        self._append("alerts.jsonl", a.model_dump())
        return {"alert_created": True, "sku": a.sku}

    def log(self, a: LogArgs) -> dict[str, Any]:
        self._append("decisions.jsonl", {"sku": a.sku, "record": a.record})
        return {"logged": True, "sku": a.sku}


def build_allocation_tools(db: SqlConnector, store_dir: Path) -> list[Tool]:
    s = AllocationService(db, store_dir)
    return [
        Tool("compute_allocation",
             "Pull fresh data for a SKU from Zetaris and run the full allocation logic (buffer, inbound credit, state, allocation, guardrails). Returns the per-SKU record. Do not do this math yourself.",
             SkuArgs, s.compute),
        Tool("set_channel_allocation",
             "Apply the computed allocation for a SKU (call compute_allocation first). Enforces guardrails: sellable cap, 25% per-run change limit, locked and stale-data blocks.",
             SetAllocArgs, s.set_allocation),
        Tool("create_alert", "Notify a human. State SKU, problem, recommended action, risk of doing nothing, and deadline.", AlertArgs, s.alert),
        Tool("log_decision", "Store the full reasoning record for a SKU decision.", LogArgs, s.log),
    ]
