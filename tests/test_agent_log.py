"""Agent log: one event card per agent decision, the approval gate, approve and deny flows."""
from __future__ import annotations

import json

from src.allocation import agent_log
from tests.test_allocation_tools import DemoConnector, call, tools


def _econ(sku: str, rows: dict[str, tuple[float, float, float, float]]) -> list[dict]:
    return [{"sku": sku, "channel": ch, "unit_margin": m, "demand_confidence": conf, "v7": v7, "v30": v7, "v90": v90,
             "trend": 1.0, "floor_units": 0, "margin_age_hours": 1} for ch, (m, conf, v7, v90) in rows.items()]


RUG = _econ("RUG-003", {"DTC": (111.75, 0.9, 2, 2), "Amazon": (74.5, 1.0, 2, 2), "Etsy": (59.6, 0.6, 0.5, 0.5), "Walmart": (44.7, 0.7, 0.5, 0.5)})
MUG = _econ("MUG-001", {"DTC": (24, 0.9, 6, 3), "Amazon": (16, 1.0, 3, 6), "Etsy": (12.8, 0.8, 3, 3), "Walmart": (9.6, 0.9, 7, 7)})


def _seed(store, sku, state, allocation):
    (store / "allocations.jsonl").write_text(json.dumps({"ts": "2026-10-25T00:00:00Z", "sku": sku, "state": state,
                                                          "allocation": allocation, "note": "baseline"}) + "\n", encoding="utf-8")


def _db(sku, econ):
    return DemoConnector(patch={"channel_economics": econ, "wms_inbound": []})


def _chans(ev):
    return {c["channel"]: c for c in ev["channels"]}


def test_changes_are_classified_auto_apply_log_and_notify(tmp_path):
    _seed(tmp_path, "MUG-001", "Balanced", {"DTC": 10, "Amazon": 150, "Etsy": 5, "Walmart": 20})
    reg = tools(_db("MUG-001", MUG), tmp_path)
    call(reg, "compute_allocation", {"sku": "MUG-001"})
    ok, w = call(reg, "set_channel_allocation", {"sku": "MUG-001"})
    assert ok and w["written"]
    ev = agent_log.events(tmp_path)
    assert len(ev) == 1
    e = ev[0]
    assert e["status"] == "auto" and e["approval"] == "Auto-apply" and e["state_from"] == "Balanced"
    assert e["moves"]["add"] and e["moves"]["reduce"] and e["total_savings"] > 0
    assert e["with_change"]["lines"] and e["without_change"]["lines"]
    assert e["with_change"]["total"] - e["without_change"]["total"] == e["net_savings"]
    for c in e["channels"]:
        want = "Auto-apply and log" if c["cap_to"] > c["cap_from"] else "Auto-apply and notify"
        assert c["row_approval"] == want and c["trigger"] and c["reason"] and c["calc"]
        assert (c["savings"].startswith("$") and c["savings_amount"]) if c["cap_to"] > c["cap_from"] else c["savings"].startswith("frees ")
    assert "Amazon" in _chans(e) and "DTC" in _chans(e)


def test_channel_pause_is_staged_not_written_until_approved(tmp_path):
    _seed(tmp_path, "RUG-003", "Balanced", {"DTC": 16, "Amazon": 7, "Etsy": 1, "Walmart": 6})
    reg = tools(_db("RUG-003", RUG), tmp_path)
    assert call(reg, "compute_allocation", {"sku": "RUG-003"})[1]["allocation"]["Walmart"] == 0
    ok, w = call(reg, "set_channel_allocation", {"sku": "RUG-003"})
    assert ok and w["written"] is False and w["pending_approval"] and "Walmart" in w["reasons"][0]
    assert len((tmp_path / "allocations.jsonl").read_text().splitlines()) == 1

    ev = agent_log.events(tmp_path)
    assert len(ev) == 1
    e = ev[0]
    assert e["status"] == "pending" and e["approval"] == "Needs approval" and e["approval_id"]
    assert e["moves"]["reduce"] == [{"channel": "Walmart", "units": 6}, {"channel": "Amazon", "units": 2}]
    chans = _chans(e)
    pause = chans["Walmart"]
    assert (pause["cap_from"], pause["cap_to"]) == (6, 0) and pause["kind"] == "pause" and pause["primary"]
    assert pause["savings"].startswith("up to $") and pause["savings"].endswith("if approved")
    assert e["net_savings"] == e["total_savings"] - e["baseline_savings"] and e["baseline_savings"] > 0
    assert e["with_change"]["total"] == 60 and e["without_change"]["total"] == 265 and e["net_savings"] == -205
    assert chans["Amazon"]["savings"] == "frees 2 units" and chans["Etsy"]["savings"].startswith("$")
    assert sum(c["primary"] for c in e["channels"]) == 1

    code, out = agent_log.approve(tmp_path, e["approval_id"])
    assert code == 200 and out["allocation"]["Walmart"] == 0
    last = json.loads((tmp_path / "allocations.jsonl").read_text().splitlines()[-1])
    assert last["allocation"]["Walmart"] == 0 and last["approval_id"] == e["approval_id"] and last["previous"]["Walmart"] == 6
    after = agent_log.events(tmp_path)
    assert len(after) == 1 and after[0]["status"] == "approved" and after[0]["approval"] == "Approved"
    assert agent_log.approve(tmp_path, e["approval_id"])[0] == 409
    assert agent_log.approve(tmp_path, "nope")[0] == 404


def test_stale_proposal_is_refused_and_new_proposal_supersedes_old(tmp_path):
    _seed(tmp_path, "RUG-003", "Balanced", {"DTC": 16, "Amazon": 7, "Etsy": 1, "Walmart": 6})
    reg = tools(_db("RUG-003", RUG), tmp_path)
    call(reg, "compute_allocation", {"sku": "RUG-003"})
    first = call(reg, "set_channel_allocation", {"sku": "RUG-003"})[1]["approval_id"]
    call(reg, "compute_allocation", {"sku": "RUG-003"})
    second = call(reg, "set_channel_allocation", {"sku": "RUG-003"})[1]["approval_id"]
    states = agent_log.approvals(tmp_path)
    assert states[first]["status"] == "superseded" and states[second]["status"] == "pending"
    assert [e["approval_id"] for e in agent_log.events(tmp_path)] == [second]

    _seed(tmp_path, "RUG-003", "Balanced", {"DTC": 30, "Amazon": 5, "Etsy": 1, "Walmart": 6})
    code, out = agent_log.approve(tmp_path, second)
    assert code == 409 and "changed" in out["error"]


def test_denial_needs_a_reason_and_reaches_the_agent(tmp_path):
    _seed(tmp_path, "RUG-003", "Balanced", {"DTC": 16, "Amazon": 7, "Etsy": 1, "Walmart": 6})
    reg = tools(_db("RUG-003", RUG), tmp_path)
    call(reg, "compute_allocation", {"sku": "RUG-003"})
    aid = call(reg, "set_channel_allocation", {"sku": "RUG-003"})[1]["approval_id"]
    assert agent_log.deny(tmp_path, aid, "")[0] == 400
    code, out = agent_log.deny(tmp_path, aid, "keep Walmart listed for marketplace ranking")
    assert code == 200 and out["reason"].startswith("keep Walmart")
    ev = agent_log.events(tmp_path)
    assert len(ev) == 1 and ev[0]["status"] == "denied" and ev[0]["approval"] == "Denied"
    assert ev[0]["deny_reason"].startswith("keep Walmart")
    ok, r = call(reg, "compute_allocation", {"sku": "RUG-003"})
    assert ok and r["recent_denied_proposals"][-1]["deny_reason"].startswith("keep Walmart")
    assert agent_log.deny(tmp_path, aid, "again")[0] == 409 and agent_log.approve(tmp_path, aid)[0] == 409
