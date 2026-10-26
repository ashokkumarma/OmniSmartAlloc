"""Units each channel's orders consumed since an allocation was written (demo order stores).

Orders placed at or after `since_ts` that are not cancelled draw down the channel's own count.
Returns {} when the order stores are unreachable, so the agent falls back to the last written counts.
"""
from __future__ import annotations


def used_since(sku: str, since_ts: str) -> dict[str, int]:
    try:
        from demo import order_stores
        orders = order_stores.load_all()
    except Exception:
        return {}
    used: dict[str, int] = {}
    for o in orders:
        if o["sku"] == sku and o["status"] != "cancelled" and o["ts"] >= since_ts:
            used[o["channel"]] = used.get(o["channel"], 0) + o["qty"]
    return used
