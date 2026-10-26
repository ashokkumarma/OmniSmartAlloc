"""Snapshot -> engine -> tools -> agent, offline, using the demo data files through a fake connector."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent import ReActAgent
from src.allocation import agent_log
from src.allocation.snapshot import MissingInput
from src.data_connectors.readonly import ensure_read_only
from src.prompts import OMNISMARTALLOC_SYSTEM_PROMPT
from src.tools import ToolRegistry, build_discovery_tools
from src.tools.allocation_tools import build_allocation_tools
from tests.conftest import ScriptedClient, completion, tool_call

DATA = Path(__file__).resolve().parent.parent / "demo" / "data"


def _load(name: str, key: str) -> list[dict[str, Any]]:
    return json.loads((DATA / name).read_text())[key]


BASE_INVENTORY = [  # frozen: demo/data/wms_inventory.json changes as orders are placed in the UI
    {"sku": "MUG-001", "on_hand": 400, "committed": 60, "unputaway": 0, "age_hours": 0.2},
    {"sku": "LAMP-002", "on_hand": 400, "committed": 20, "unputaway": 0, "age_hours": 0.2},
    {"sku": "RUG-003", "on_hand": 30, "committed": 4, "unputaway": 0, "age_hours": 0.2},
    {"sku": "LOCK-004", "on_hand": 80, "committed": 5, "unputaway": 0, "age_hours": 0.2},
]


class DemoConnector:
    """Answers the snapshot's SELECTs from demo/data, filtering on `sku = '...'` like Zetaris would."""

    def __init__(self, drop: set[str] | None = None, patch: dict[str, dict] | None = None):
        self.tables = {
            "wms_inventory": [dict(r) for r in BASE_INVENTORY], "wms_inbound": _load("wms_inbound.json", "inbound"),
            "supplier_reliability": _load("supplier_reliability.json", "suppliers"),
            "channel_economics": _load("channel_economics.json", "economics"), "sku_rules": _load("sku_rules.json", "rules"),
        }
        for k, v in (patch or {}).items():
            self.tables[k] = v
        self.drop = drop or set()
        self.executed: list[str] = []

    def query(self, sql: str, max_rows: int = 50) -> list[dict[str, Any]]:
        stmt = ensure_read_only(sql)
        self.executed.append(stmt)
        table = stmt.split("omnismart.")[1].split()[0]
        rows = [] if table in self.drop else self.tables[table]
        if "sku = '" in stmt:
            sku = stmt.split("sku = '")[1].split("'")[0]
            rows = [r for r in rows if r.get("sku") == sku]
        return rows[:max_rows]


def tools(db, tmp_path):
    reg = ToolRegistry(build_discovery_tools(db, extra=build_allocation_tools(db, tmp_path)))
    return reg


def call(reg, name, args):
    ok, out = reg.call(name, args)
    return ok, json.loads(out)


BASE_ECON = [  # reset-baseline economics for MUG-001 (75/50/40/30% margins, user-tuned confidence)
    {"sku": "MUG-001", "channel": "DTC", "unit_margin": 24.0, "demand_confidence": 0.9, "v7": 6, "v30": 6, "v90": 6, "trend": 1.0, "floor_units": 0, "margin_age_hours": 3},
    {"sku": "MUG-001", "channel": "Amazon", "unit_margin": 16.0, "demand_confidence": 1.0, "v7": 14, "v30": 14, "v90": 14, "trend": 1.0, "floor_units": 0, "margin_age_hours": 3},
    {"sku": "MUG-001", "channel": "Etsy", "unit_margin": 12.8, "demand_confidence": 0.8, "v7": 3, "v30": 3, "v90": 3, "trend": 1.0, "floor_units": 0, "margin_age_hours": 3},
    {"sku": "MUG-001", "channel": "Walmart", "unit_margin": 9.6, "demand_confidence": 0.9, "v7": 7, "v30": 7, "v90": 7, "trend": 1.0, "floor_units": 0, "margin_age_hours": 3},
]
BASE_STOCK = [{"sku": "MUG-001", "on_hand": 100, "committed": 0, "unputaway": 0, "age_hours": 0.2}]


def test_demo_data_reproduces_the_baseline_example(tmp_path):
    """Current baseline: MUG-001 at 100/0 with 75/50/40/30% margins -> Tight, Amazon-first allocation."""
    db = DemoConnector(patch={"channel_economics": BASE_ECON, "wms_inventory": BASE_STOCK})
    ok, r = call(tools(db, tmp_path), "compute_allocation", {"sku": "MUG-001"})
    assert ok and r["state"] == "Tight" and r["sellable_units"] == 100
    assert r["allocation"] == {"DTC": 65, "Amazon": 20, "Etsy": 5, "Walmart": 10}


def test_demo_skus_cover_critical_and_all_demo_skus_are_unlocked(tmp_path):
    reg = tools(DemoConnector(patch={"wms_inbound": []}), tmp_path)
    assert call(reg, "compute_allocation", {"sku": "RUG-003"})[1]["state"] == "Critical"
    unlocked = call(reg, "compute_allocation", {"sku": "LOCK-004"})[1]
    assert unlocked["write_allowed"]
    ok, w = call(reg, "set_channel_allocation", {"sku": "LOCK-004"})
    assert ok and w["written"] is True
    assert (tmp_path / "allocations.jsonl").exists()


def test_set_requires_compute_first(tmp_path):
    ok, out = call(tools(DemoConnector(), tmp_path), "set_channel_allocation", {"sku": "MUG-001"})
    assert not ok and "compute_allocation" in out["error"]


def test_missing_on_hand_stops_allocation(tmp_path):
    ok, out = call(tools(DemoConnector(drop={"wms_inventory"}), tmp_path), "compute_allocation", {"sku": "MUG-001"})
    assert not ok and "on-hand" in out["error"]


def test_missing_supplier_reliability_uses_documented_defaults(tmp_path):
    ok, r = call(tools(DemoConnector(drop={"supplier_reliability"}), tmp_path), "compute_allocation", {"sku": "MUG-001"})
    assert ok and any("70%" in f and "7-day" in f for f in r["fallbacks_used"])
    assert r["time_to_replenish_days"] == 12.0


def test_missing_committed_is_low_confidence(tmp_path):
    inv = [{"sku": "MUG-001", "on_hand": 400, "committed": None, "unputaway": 0, "age_hours": 0.1}]
    ok, r = call(tools(DemoConnector(patch={"wms_inventory": inv}), tmp_path), "compute_allocation", {"sku": "MUG-001"})
    assert ok and r["confidence"] == "low"


def test_move_over_25_percent_of_held_stock_stages_approval(tmp_path):
    reg = tools(DemoConnector(), tmp_path)
    call(reg, "compute_allocation", {"sku": "MUG-001"})
    first = call(reg, "set_channel_allocation", {"sku": "MUG-001"})[1]
    assert first["written"] and not first["stepped_by_25pct_limit"]
    store = tmp_path / "allocations.jsonl"
    seed = json.loads(store.read_text().splitlines()[0])
    seed["allocation"] = {"DTC": 60, "Amazon": 114, "Etsy": 65, "Walmart": 19}
    store.write_text(json.dumps(seed) + "\n")
    call(reg, "compute_allocation", {"sku": "MUG-001"})
    second = call(reg, "set_channel_allocation", {"sku": "MUG-001"})[1]
    assert second["written"] is False and second["pending_approval"]
    assert any("25%" in r for r in second["reasons"])
    # Caps are untouched until a human approves
    last = json.loads((tmp_path / "allocations.jsonl").read_text().splitlines()[-1])
    assert last["allocation"] == {"DTC": 60, "Amazon": 114, "Etsy": 65, "Walmart": 19}


def test_negative_savings_proposal_is_never_applied_or_offered(tmp_path, monkeypatch):
    """Negative projected savings: not written, not staged for approval, no card - on every path."""
    reg = tools(DemoConnector(), tmp_path)
    call(reg, "compute_allocation", {"sku": "MUG-001"})
    call(reg, "set_channel_allocation", {"sku": "MUG-001"})
    monkeypatch.setattr(agent_log, "projected_net_savings", lambda *a, **k: -50.0)
    reg2 = tools(DemoConnector(patch={"wms_inventory": [{"sku": "MUG-001", "on_hand": 300, "committed": 0}]}), tmp_path)
    call(reg2, "compute_allocation", {"sku": "MUG-001"})
    ok, w = call(reg2, "set_channel_allocation", {"sku": "MUG-001"})
    assert ok and w["written"] is False and w["declined"] and not w.get("pending_approval")
    assert "negative" in w["reasons"][0]
    assert len((tmp_path / "allocations.jsonl").read_text().splitlines()) == 1  # nothing applied
    assert not agent_log.events(tmp_path)  # never rendered as a card
    assert not agent_log.pending(tmp_path, "MUG-001")  # never offered for approval
    assert agent_log.denied(tmp_path, "MUG-001")  # fed back so the agent won't re-propose it


def test_zero_savings_change_is_never_written(tmp_path, monkeypatch):
    """A no-benefit change (net savings = 0) is not written, not staged, and shows no card."""
    reg = tools(DemoConnector(), tmp_path)
    call(reg, "compute_allocation", {"sku": "MUG-001"})
    call(reg, "set_channel_allocation", {"sku": "MUG-001"})
    monkeypatch.setattr(agent_log, "projected_net_savings", lambda *a, **k: 0.0)
    reg2 = tools(DemoConnector(patch={"wms_inventory": [{"sku": "MUG-001", "on_hand": 300, "committed": 0}]}), tmp_path)
    call(reg2, "compute_allocation", {"sku": "MUG-001"})
    ok, w = call(reg2, "set_channel_allocation", {"sku": "MUG-001"})
    assert ok and w["written"] is False and w["declined"] and not w.get("pending_approval")
    assert "no projected savings" in w["reasons"][0].lower()
    assert len((tmp_path / "allocations.jsonl").read_text().splitlines()) == 1  # caps untouched
    assert not agent_log.events(tmp_path)
    assert not agent_log.pending(tmp_path, "MUG-001")


def test_stock_sync_is_not_counted_as_margin_loss():
    """Caps shrinking because stock was sold is a stock sync, not a loss."""
    ctx = {ch: {"unit_margin": m, "forecast_per_day": f} for ch, m, f in
           [("DTC", 24, 6), ("Amazon", 16, 14), ("Etsy", 13, 3), ("Walmart", 10, 7)]}
    prev = {"DTC": 44, "Amazon": 33, "Etsy": 7, "Walmart": 16}
    shrink = {"DTC": 36, "Amazon": 19, "Etsy": 5, "Walmart": 10}
    assert agent_log.projected_net_savings(prev, shrink, ctx, 2.3) == 0


def test_alert_and_log_are_persisted(tmp_path):
    reg = tools(DemoConnector(), tmp_path)
    assert call(reg, "create_alert", {"sku": "RUG-003", "problem": "p", "recommended_action": "a",
                                       "risk_of_inaction": "r", "deadline": "d"})[0]
    assert call(reg, "log_decision", {"sku": "RUG-003", "record": {"x": 1}})[0]
    assert json.loads((tmp_path / "alerts.jsonl").read_text().splitlines()[0])["sku"] == "RUG-003"
    assert json.loads((tmp_path / "decisions.jsonl").read_text().splitlines()[0])["record"] == {"x": 1}


def test_invalid_sku_is_rejected_before_any_query(tmp_path):
    db = DemoConnector()
    ok, out = call(tools(db, tmp_path), "compute_allocation", {"sku": "X'; DROP TABLE t; --"})
    assert not ok and "invalid arguments" in out["error"] and db.executed == []


def test_agent_run_compute_then_set_then_answer(tmp_path):
    db = DemoConnector()
    llm = ScriptedClient([
        completion(tool_calls=[tool_call("compute_allocation", {"sku": "MUG-001"}, "c1")]),
        completion(tool_calls=[tool_call("set_channel_allocation", {"sku": "MUG-001", "reason": "tight"}, "c2")]),
        completion(content="MUG-001 is Tight: DTC 65, Amazon 152, Etsy 27, Walmart 63."),
    ])
    agent = ReActAgent(llm, "fake", tools(db, tmp_path), OMNISMARTALLOC_SYSTEM_PROMPT)
    result = agent.run("Allocate MUG-001")
    assert [s.tool for s in result.steps] == ["compute_allocation", "set_channel_allocation"] and all(s.ok for s in result.steps)
    assert json.loads((tmp_path / "allocations.jsonl").read_text().splitlines()[0])["allocation"]["DTC"] == 65
    assert len(result.steps[0].result) < 6000, "compute output must not be truncated"
