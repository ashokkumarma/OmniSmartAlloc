"""Smoke tests against a running demo stack (see SMOKE_TESTS.md).

Start the stack first:  .venv\\Scripts\\python.exe scripts/start_demo.py
Run:                    .venv\\Scripts\\python.exe -m pytest smoke
Base URLs: OMNI_UI_URL (default http://localhost:8902), OMNI_API_URL (default http://localhost:8901).

The tests reset the demo before and after, so demo/data/*.json ends where it started.
Agent runs and the Zetaris federation panel need Zetaris and a model key, so they are not covered here.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

UI = os.environ.get("OMNI_UI_URL", "http://localhost:8902").rstrip("/")
API = os.environ.get("OMNI_API_URL", "http://localhost:8901").rstrip("/")


def _call(method: str, url: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw, code, ctype = r.read().decode(), r.status, r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raw, code, ctype = e.read().decode(), e.code, e.headers.get("Content-Type", "")
    return code, json.loads(raw) if "json" in ctype else raw


def _post(path: str, body: dict | None = None):
    return _call("POST", UI + path, body or {})


def _get(path: str):
    return _call("GET", UI + path)


@pytest.fixture(scope="module", autouse=True)
def baseline():
    try:
        urllib.request.urlopen(UI + "/api/agent/status", timeout=3)
    except OSError:
        pytest.skip(f"demo UI not reachable at {UI}; start it with scripts/start_demo.py")
    code, out = _post("/api/reset")
    assert code == 200 and out["reset"] is True, out
    yield
    _post("/api/reset")


def _app_built() -> bool:
    code, html = _get("/")
    return code == 200 and 'id="root"' in html


def test_pages_load():
    """The React app answers every section URL, or the original pages do when it has not been built."""
    built = _app_built()
    for path in ("/", "/app", "/ops", "/channels", "/orders", "/inventory", "/agent", "/storefronts", "/sources"):
        code, html = _get(path)
        assert code == 200, path
        if built:
            assert 'id="root"' in html, path
    if not built:
        assert "Sales Channels" in _get("/channels")[1] and "Inventory & Agent Ops" in _get("/ops")[1]


def test_product_page_urls():
    """/inventory/<SKU> returns the app (the app shows an empty state for an unknown SKU); odd paths do not."""
    if not _app_built():
        return
    code, html = _get("/inventory/MUG-001")
    assert code == 200 and 'id="root"' in html
    assert _get("/inventory/../../etc/passwd")[0] == 404
    assert _get("/inventory/" + "A" * 40)[0] == 404


def test_original_pages_stay_available():
    # /oms and /ims are the URLs the guided demo walkthrough uses; /classic/... are aliases
    for path, title in (("/oms", "Sales Channels"), ("/ims", "Inventory & Agent Ops"),
                        ("/classic/channels", "Sales Channels"), ("/classic/ops", "Inventory & Agent Ops")):
        code, html = _get(path)
        assert code == 200 and title in html


def test_app_assets_and_path_traversal():
    if not _app_built():
        pytest.skip("React UI not built (npm run build in demo/app)")
    import re
    js = re.search(r'src="(/assets/[^"]+\.js)"', _get("/")[1]).group(1)
    code, body = _get(js)
    assert code == 200 and "OmniSmartAlloc" in body
    assert _get("/favicon.svg")[0] == 200
    for bad in ("/assets/../server.py", "/assets/%2e%2e/server.py", "/assets/.env", "/nope"):
        assert _call("GET", UI + bad)[0] == 404, bad


def test_source_apis_up():
    code, out = _call("GET", API + "/health")
    assert code == 200 and out["status"] == "ok"
    code, out = _call("GET", API + "/api/wms/inventory")
    assert code == 200 and len(out["inventory"]) == 4


# The saved baseline decides how many orders a reset restores; read it rather than hard-code it.
BASELINE_ORDERS = len(json.loads((Path(__file__).resolve().parent.parent / "demo" / "baseline" / "orders.json").read_text(encoding="utf-8")))


def test_reset_restores_baseline():
    code, out = _post("/api/reset")
    assert code == 200 and out == {**out, "reset": True, "skus": 4, "orders_restored": BASELINE_ORDERS}
    code, s = _get("/api/state")
    assert code == 200 and len(s["skus"]) == 4 and s["alerts"] and s["decisions"]
    # KPIs count every order, not just the 200 recent ones the page lists
    assert len(s["orders"]) == 200 and s["totals"]["orders"] == BASELINE_ORDERS
    assert sum(s["totals"]["status_counts"].values()) == BASELINE_ORDERS


def _sku(state: dict, sku: str) -> dict:
    return next(x for x in state["skus"] if x["sku"] == sku)


def test_order_lifecycle_updates_stock():
    _, before = _get("/api/state")
    committed = _sku(before, "MUG-001")["committed"]

    code, out = _post("/api/order", {"channel": "DTC", "sku": "MUG-001", "qty": 3})
    assert code == 201, out
    oid = out["order"]["id"]
    assert out["stored_in"]["location"] == "CHANNEL_DB.dtc_orders"
    _, s = _get("/api/state")
    assert _sku(s, "MUG-001")["committed"] == committed + 3

    code, out = _post(f"/api/order/{oid}/partial", {"qty": 1, "reason": "smoke"})
    assert code == 200 and out["order"]["status"] == "partial" and out["order"]["remaining"] == 2
    code, out = _post(f"/api/order/{oid}/fulfill")
    assert code == 200 and out["order"]["status"] == "fulfilled"
    code, out = _post(f"/api/order/{oid}/cancel")
    assert code == 409


def test_cancel_releases_units():
    _, before = _get("/api/state")
    committed = _sku(before, "RUG-003")["committed"]
    code, out = _post("/api/order", {"channel": "Amazon", "sku": "RUG-003", "qty": 1})
    assert code == 201, out
    code, out = _post(f"/api/order/{out['order']['id']}/cancel")
    assert code == 200 and out["order"]["status"] == "cancelled"
    _, s = _get("/api/state")
    assert _sku(s, "RUG-003")["committed"] == committed


@pytest.mark.parametrize("body,code", [
    ({"channel": "DTC", "sku": "MUG-001", "qty": 0}, 400),
    ({"channel": "eBay", "sku": "MUG-001", "qty": 1}, 400),
    ({"channel": "DTC", "sku": "NOPE-999", "qty": 1}, 404),
    ({"channel": "DTC", "sku": "MUG-001", "qty": 999}, 409),
])
def test_order_validation(body, code):
    assert _post("/api/order", body)[0] == code


def test_scenario1_loads_and_verifies():
    code, out = _post("/api/scenario/1")
    assert code == 200, out
    failed = [c for c in out["checks"] if c["ok"] is False and c["name"] != "Zetaris federation"]
    assert not failed, failed
    assert out["summary"]["orders_total"] > 0
