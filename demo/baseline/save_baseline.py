"""Capture the current demo state as the baseline that "Reset demo" restores.

Copies every demo/data/*.json file, dumps all channel orders (Postgres x3 + the
Amazon REST-backed JSON store) and the outbox event logs into demo/baseline/.
Run this whenever the demo's desired starting state changes:

    py -3.12 demo/baseline/save_baseline.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "demo"
BASELINE = DEMO / "baseline"
OUTBOX = DEMO / "outbox"

sys.path.insert(0, str(DEMO))
import order_stores  # noqa: E402

FILES = ["allocations.jsonl", "approvals.jsonl", "alerts.jsonl", "decisions.jsonl"]


def save() -> dict:
    data_dir = BASELINE / "data"
    outbox_dir = BASELINE / "outbox"
    data_dir.mkdir(parents=True, exist_ok=True)
    outbox_dir.mkdir(parents=True, exist_ok=True)

    data_files = sorted((DEMO / "data").glob("*.json"))
    for f in data_files:
        shutil.copy2(f, data_dir / f.name)

    orders = order_stores.load_all()
    (BASELINE / "orders.json").write_text(json.dumps(orders, indent=1), encoding="utf-8")

    for name in FILES:
        src = OUTBOX / name
        (outbox_dir / name).write_text(src.read_text(encoding="utf-8") if src.exists() else "", encoding="utf-8")

    return {"data_files": [f.name for f in data_files], "orders": len(orders)}


if __name__ == "__main__":
    print("baseline saved:", json.dumps(save(), indent=1))
