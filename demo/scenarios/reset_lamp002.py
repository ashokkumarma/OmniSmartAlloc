"""Restore the exact Scenario 1 starting state for LAMP-002 (use between demo runs).

Removes everything on LAMP-002 that happened since seeding (extra orders, agent allocations, alerts,
decisions), then reseeds. Safe to run any number of times.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "demo"))

from scenarios import seed_lamp002  # noqa: E402


def run() -> dict:
    return seed_lamp002.run()


if __name__ == "__main__":
    out = run()
    print(f"Scenario 1 reset: LAMP-002 on_hand {out['on_hand']}, sellable {out['sellable']}, remaining caps {out['remaining']}")
