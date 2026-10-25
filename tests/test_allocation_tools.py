"""Snapshot -> engine -> tools -> agent, offline, using the demo data files through a fake connector."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent import ReActAgent
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
    {"sku": "KBD-003", "on_hand": 30, "committed": 4, "unputaway": 0, "age_hours": 0.2},
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


def test_demo_data_reproduces_the_worked_example(tmp_path):
    ok, r = call(tools(DemoConnector(), tmp_path), "compute_allocation", {"sku": "MUG-001"})
    assert ok and r["state"] == "Tight" and r["sellable_units"] == 328
    assert r["allocation"] == {"DTC": 130, "Amazon": 114, "Etsy": 65, "Walmart": 19}


def test_demo_skus_cover_critical_and_locked(tmp_path):
    reg = tools(DemoConnector(), tmp_path)
    assert call(reg, "compute_allocation", {"sku": "KBD-003"})[1]["state"] == "Critical"
    locked = call(reg, "compute_allocation", {"sku": "LOCK-004"})[1]
    assert not locked["write_allowed"]
    ok, w = call(reg, "set_channel_allocation", {"sku": "LOCK-004"})
    assert ok and w["written"] is False and "would_have_allocated" in w
    assert not (tmp_path / "allocations.jsonl").exists()


def test_set_requires_compute_first(tmp_path):
    ok, out = call(tools(DemoConnector(), tmp_path), "set_channel_allocation", {"sku": "MUG-001"})
    assert not ok and "compute_allocation" in out["error"]


def test_missing_on_hand_stops_allocation(tmp_path):
    ok, out = call(tools(DemoConnector(drop={"wms_inventory"}), tmp_path), "compute_allocation", {"sku": "MUG-001"})
    assert not ok and "on-hand" in out["error"]


def test_missing_supplier_reliability_uses_documented_defaults(tmp_path):
    ok, r = call(tools(DemoConnector(drop={"supplier_reliability"}), tmp_path), "compute_allocation", {"sku": "MUG-001"})
    assert ok and any("70%" in f and "7-day" in f for f in r["fallbacks_used"])
    assert r["time_to_replenish_days"] == 21.0


def test_missing_committed_is_low_confidence(tmp_path):
    inv = [{"sku": "MUG-001", "on_hand": 400, "committed": None, "unputaway": 0, "age_hours": 0.1}]
    ok, r = call(tools(DemoConnector(patch={"wms_inventory": inv}), tmp_path), "compute_allocation", {"sku": "MUG-001"})
    assert ok and r["confidence"] == "low"


def test_25_percent_limit_steps_toward_target_when_state_unchanged(tmp_path):
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
    assert second["stepped_by_25pct_limit"] and second["applied"]["DTC"] == 75
    assert sum(second["applied"].values()) <= 328


def test_alert_and_log_are_persisted(tmp_path):
    reg = tools(DemoConnector(), tmp_path)
    assert call(reg, "create_alert", {"sku": "KBD-003", "problem": "p", "recommended_action": "a",
                                       "risk_of_inaction": "r", "deadline": "d"})[0]
    assert call(reg, "log_decision", {"sku": "KBD-003", "record": {"x": 1}})[0]
    assert json.loads((tmp_path / "alerts.jsonl").read_text().splitlines()[0])["sku"] == "KBD-003"
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
        completion(content="MUG-001 is Tight: DTC 130, Etsy 65, Amazon 114, Walmart 19."),
    ])
    agent = ReActAgent(llm, "fake", tools(db, tmp_path), OMNISMARTALLOC_SYSTEM_PROMPT)
    result = agent.run("Allocate MUG-001")
    assert [s.tool for s in result.steps] == ["compute_allocation", "set_channel_allocation"] and all(s.ok for s in result.steps)
    assert json.loads((tmp_path / "allocations.jsonl").read_text().splitlines()[0])["allocation"]["DTC"] == 130
    assert len(result.steps[0].result) < 6000, "compute output must not be truncated"
