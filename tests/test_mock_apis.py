"""The mock source APIs keep decimal columns decimal, whatever the JSON files hold."""
import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location("mock_apis", Path(__file__).resolve().parent.parent / "demo" / "mock_apis.py")
mock_apis = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mock_apis)


def test_whole_numbers_in_decimal_columns_are_sent_as_floats():
    payload = {"economics": [{"sku": "MUG-001", "unit_margin": 16, "v7": 3, "v30": 2.5, "floor_units": 4}]}
    out = mock_apis._floats(payload, mock_apis.FLOAT_FIELDS["/api/channels/economics"])
    row = out["economics"][0]
    assert isinstance(row["unit_margin"], float) and isinstance(row["v7"], float) and row["v30"] == 2.5
    assert isinstance(row["floor_units"], int)  # integer columns stay integers
    assert json.dumps(row).count(".0") == 2


def test_booleans_are_left_alone():
    out = mock_apis._floats({"rules": [{"locked": True, "promo_multiplier": 1}]}, ("promo_multiplier", "locked"))
    assert out["rules"][0]["locked"] is True and out["rules"][0]["promo_multiplier"] == 1.0


def test_amazon_partial_shipments_are_sent_as_text():
    out = mock_apis._nested_as_text({"orders": [{"id": "a", "partial_shipments": [{"qty": 1, "reason": "split"}]}, {"id": "b"}]})
    assert out["orders"][0]["partial_shipments"] == ['{"qty": 1, "reason": "split"}']
    assert out["orders"][1]["partial_shipments"] == []
