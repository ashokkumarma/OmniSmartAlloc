"""Decision memory backed by the Meterless H-MEM engine (engines/hmem, TypeScript, run with Node).

Human approvals and denials of allocation proposals become H-MEM memories (SKU, channel moves,
decision, reason, reviewer, provenance = approval id). compute_allocation recalls the memories for a
SKU on the next run so the agent respects past human judgement, and shows them in its reasoning.

Python talks to the engine through engines/hmem/src/cli.ts (one JSON request on stdin, one JSON
reply on stdout). State lives in <store>/memory/ (state.json + append-only ledger.jsonl).

If Node or the engine is unavailable the calls return None and log a warning; compute_allocation
then falls back to agent_log.denied() (the approvals file), so the agent never stops working.
Set OMNI_HMEM=off to disable the engine; HMEM_NODE overrides the node executable.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
CLI = ROOT / "engines" / "hmem" / "src" / "cli.ts"
TIMEOUT_S = 20


class HMemUnavailable(RuntimeError):
    pass


def memory_dir(store: Path) -> Path:
    return Path(store) / "memory"


def namespace(sku: str) -> str:
    return f"sku:{sku}"


def _node() -> str:
    if os.environ.get("OMNI_HMEM", "").lower() in ("off", "0", "false", "disabled"):
        raise HMemUnavailable("H-MEM disabled by OMNI_HMEM")
    node = os.environ.get("HMEM_NODE") or shutil.which("node")
    if not node:
        raise HMemUnavailable("node executable not found")
    return node


def call(store: Path, request: dict[str, Any]) -> dict[str, Any]:
    """Send one request to the H-MEM CLI. Raises HMemUnavailable on any failure."""
    req = {**request, "dir": str(memory_dir(store))}
    try:
        p = subprocess.run([_node(), str(CLI)], input=json.dumps(req), capture_output=True, text=True,
                           encoding="utf-8", timeout=TIMEOUT_S, cwd=str(ROOT))
    except (OSError, subprocess.TimeoutExpired) as e:
        raise HMemUnavailable(f"could not run the H-MEM engine: {e}") from e
    if p.returncode != 0:
        raise HMemUnavailable((p.stderr or p.stdout or f"exit {p.returncode}").strip()[:300])
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError as e:
        raise HMemUnavailable(f"bad reply from the H-MEM engine: {p.stdout[:200]}") from e


def describe_moves(previous: dict[str, int] | None, allocation: dict[str, int]) -> str:
    prev = previous or {}
    moves = [f"{ch} {prev.get(ch, 0)}→{n}" for ch, n in sorted(allocation.items()) if prev.get(ch, 0) != n]
    moves += [f"{ch} {o}→0" for ch, o in sorted(prev.items()) if ch not in allocation and o]
    return ", ".join(moves) or "no channel changes"


def remember_review(store: Path, proposal: dict[str, Any], approval_id: str, decision: str,
                    reason: str | None = None, reviewer: str | None = None) -> dict[str, Any] | None:
    """Write a human approval/denial as an H-MEM memory. Returns the memory, or None if unavailable."""
    sku = proposal["sku"]
    who = reviewer or "ops reviewer"
    moves = describe_moves(proposal.get("previous"), proposal["allocation"])
    why = (reason or "").strip() or "no reason given"
    content = (f"{who} {decision} the {sku} allocation proposal {approval_id} ({moves}). Reason: {why}.")
    try:
        out = call(store, {
            "op": "add", "content": content, "source": f"approval:{approval_id}",
            "type": "preference", "layer": "working", "namespace": namespace(sku),
            "tags": [decision, sku, *sorted(proposal["allocation"])],
            "confidence": 0.85 if decision == "denied" else 0.75,
            "provenance": {"origin": "user_correction", "label": f"{decision} by {who}",
                           "refs": [f"approval:{approval_id}"]},
        })
    except HMemUnavailable as e:
        log.warning("H-MEM unavailable, review %s not stored as memory: %s", approval_id, e)
        return None
    return out["memory"]


def recall(store: Path, sku: str, channels: list[str] | None = None, top_n: int = 5) -> list[dict[str, Any]] | None:
    """Memories of past human reviews for this SKU, ranked by H-MEM's hybrid score.
    Returns None when the engine is unavailable (caller falls back)."""
    text = " ".join([sku, "allocation", "approved denied", *(channels or [])])
    try:
        out = call(store, {"op": "query", "text": text, "namespace": namespace(sku), "topN": top_n, "threshold": 0.01})
    except HMemUnavailable as e:
        log.warning("H-MEM unavailable, falling back to the approvals log for %s: %s", sku, e)
        return None
    recalled = []
    for item in out.get("memories", []):
        m = item["memory"]
        decision = next((t for t in m["tags"] if t in ("approved", "denied")), None)
        refs = (m.get("provenance") or {}).get("refs") or []
        recalled.append({"memory_id": m["id"], "decision": decision, "content": m["content"],
                         "approval_id": next((r.split(":", 1)[1] for r in refs if r.startswith("approval:")), None),
                         "relevance": item["relevance"], "confidence": m["confidence"],
                         "learned_at": m["provenance"]["learnedAt"]})
    return recalled


def feedback(store: Path, memory_ids: list[str], kind: str) -> None:
    """helpful / not_helpful / wrong: exact H-MEM confidence deltas, recorded in the ledger."""
    for mid in memory_ids:
        try:
            call(store, {"op": "feedback", "id": mid, "kind": kind})
        except HMemUnavailable as e:
            log.warning("H-MEM feedback for %s skipped: %s", mid, e)
            return
