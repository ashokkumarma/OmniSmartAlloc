"""Meterless H-MEM engine as decision memory: human reviews become memories and are recalled on the next run.

These tests run the real engine (engines/hmem, Node) through src/memory/hmem.py; they are skipped if
Node is not installed, except the fallback test which needs no Node.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from src.allocation import agent_log
from src.memory import hmem
from tests.test_agent_log import RUG, _db, _seed
from tests.test_allocation_tools import call, tools

ROOT = Path(__file__).resolve().parent.parent
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _pending(tmp_path):
    _seed(tmp_path, "RUG-003", "Balanced", {"DTC": 5, "Amazon": 10, "Etsy": 3, "Walmart": 12})
    reg = tools(_db("RUG-003", RUG), tmp_path)
    call(reg, "compute_allocation", {"sku": "RUG-003"})
    ok, out = call(reg, "set_channel_allocation", {"sku": "RUG-003"})
    assert ok and out.get("pending_approval")
    return reg, out["approval_id"]


@needs_node
def test_denial_becomes_memory_and_is_recalled_on_next_compute(tmp_path):
    reg, aid = _pending(tmp_path)
    code, out = agent_log.deny(tmp_path, aid, "keep Walmart listed for marketplace ranking", reviewer="Dana (ops)")
    assert code == 200 and out["memory_id"]

    state = json.loads((tmp_path / "memory" / "state.json").read_text(encoding="utf-8"))
    mem = next(r for r in state["records"] if r["id"] == out["memory_id"])
    assert mem["namespace"] == "sku:RUG-003" and "denied" in mem["tags"]
    assert mem["provenance"]["refs"] == [f"approval:{aid}"] and mem["provenance"]["origin"] == "user_correction"
    assert "Dana (ops) denied the RUG-003 allocation proposal" in mem["content"] and "Walmart 9→0" in mem["content"]
    ledger = (tmp_path / "memory" / "ledger.jsonl").read_text(encoding="utf-8")
    assert '"action":"create"' in ledger

    ok, r = call(reg, "compute_allocation", {"sku": "RUG-003"})
    assert ok and r["memory_engine"] == "meterless-hmem"
    rec = r["recalled_memories"]
    assert len(rec) == 1 and rec[0]["decision"] == "denied" and rec[0]["approval_id"] == aid
    assert "keep Walmart listed" in rec[0]["content"]
    assert any(line.startswith(f"Recalled from memory ({out['memory_id']}") for line in r["reasoning"])


@needs_node
def test_recall_is_scoped_to_the_sku(tmp_path):
    _, aid = _pending(tmp_path)
    agent_log.deny(tmp_path, aid, "keep Walmart listed")
    assert hmem.recall(tmp_path, "MUG-001") == []
    assert [m["approval_id"] for m in hmem.recall(tmp_path, "RUG-003")] == [aid]


@needs_node
def test_approval_becomes_memory_and_marks_recalled_memories_helpful(tmp_path):
    reg, aid = _pending(tmp_path)
    agent_log.deny(tmp_path, aid, "too aggressive for Walmart this week")
    call(reg, "compute_allocation", {"sku": "RUG-003"})  # recalls the denial
    ok, out = call(reg, "set_channel_allocation", {"sku": "RUG-003"})
    assert ok and out.get("pending_approval")
    staged = agent_log.approvals(tmp_path)[out["approval_id"]]
    denial_mem = staged["recalled_memories"][0]["memory_id"]

    code, res = agent_log.approve(tmp_path, out["approval_id"], reviewer="Dana (ops)")
    assert code == 200 and res["memory_id"]
    decisions = {m["approval_id"]: m for m in hmem.recall(tmp_path, "RUG-003")}
    assert decisions[out["approval_id"]]["decision"] == "approved"
    state = json.loads((tmp_path / "memory" / "state.json").read_text(encoding="utf-8"))
    conf = {r["id"]: r["confidence"] for r in state["records"]}
    assert conf[denial_mem] == pytest.approx(0.85 + 0.05)  # H-MEM "helpful" delta, exact

    ev = agent_log.events(tmp_path)
    assert ev and ev[0]["status"] == "approved" and ev[0]["recalled_memories"][0]["memory_id"] == denial_mem


def test_engine_failure_falls_back_to_the_approvals_log(tmp_path, monkeypatch):
    monkeypatch.setenv("HMEM_NODE", str(tmp_path / "no-such-node.exe"))
    reg, aid = _pending(tmp_path)
    code, out = agent_log.deny(tmp_path, aid, "keep Walmart listed for marketplace ranking")
    assert code == 200 and out["memory_id"] is None  # the denial itself still succeeds
    ok, r = call(reg, "compute_allocation", {"sku": "RUG-003"})
    assert ok and r["memory_engine"].startswith("fallback")
    assert r["recalled_memories"] == []
    assert r["recent_denied_proposals"][-1]["deny_reason"].startswith("keep Walmart")


def test_engine_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNI_HMEM", "off")
    assert hmem.recall(tmp_path, "RUG-003") is None


@needs_node
def test_official_hmem_conformance_suite_passes():
    hm = ROOT / "engines" / "hmem"
    p = subprocess.run(["node", str(hm / "conformance" / "runner.ts")], cwd=str(hm / "conformance"),
                       env={**os.environ, "HMEM_IMPL": str(hm / "src" / "index.ts")},
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "13/13 checks passed" in p.stdout
