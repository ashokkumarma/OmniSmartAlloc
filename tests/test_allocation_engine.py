from src.allocation import Channel, Inbound, SkuInput, allocate, step_toward


def mug(**kw) -> SkuInput:
    base = dict(
        sku="MUG-001", on_hand=400, committed=60,
        inbound=[Inbound("PO-1", 500, 14, "in_transit", on_time_rate=0.8, delay_days=4)],
        channels=[Channel("DTC", 14, 0.9, 6, 6, 6), Channel("Amazon", 6, 1.0, 14, 14, 14),
                  Channel("Etsy", 11, 0.8, 3, 3, 3), Channel("Walmart", 5, 0.9, 7, 7, 7)])
    base.update(kw)
    return SkuInput(**base)


def test_worked_example_matches_the_document():
    r = allocate(mug())
    assert (r["state"], r["sellable_units"], r["buffer_units"]) == ("Tight", 328, 12)
    assert r["days_of_cover"] == 10.9 and r["time_to_replenish_days"] == 18
    assert r["inbound_credit_units"] == 0
    assert r["allocation"] == {"DTC": 130, "Etsy": 65, "Amazon": 114, "Walmart": 19}
    assert sum(r["allocation"].values()) == 328
    assert r["confidence"] == "medium" and "Expedite inbound PO" in r["recommended_human_actions"]
    assert r["alerts"] and r["write_allowed"]
    assert [c["score"] for c in r["channels"]] == [12.6, 6.0, 8.8, 4.5]


def test_inbound_credit_when_it_arrives_before_stockout():
    r = allocate(mug(inbound=[Inbound("PO-2", 100, 3, "in_transit", on_time_rate=1.0, delay_days=0)]))
    assert r["inbound_credit_units"] == 90 and r["state"] in ("Balanced", "Abundant", "Tight")


def test_critical_state_pauses_lowest_margin_channel_and_alerts():
    r = allocate(mug(on_hand=40, committed=4, inbound=[Inbound("PO-3", 200, 40, "planned")]))
    assert r["state"] == "Critical" and r["allocation"]["Walmart"] == 0
    assert sum(r["allocation"].values()) <= r["sellable_units"]
    assert any("Critical" in a["problem"] for a in r["alerts"])


def test_abundant_uses_shared_pool():
    r = allocate(mug(on_hand=5000, committed=0, inbound=[]))
    assert r["state"] == "Abundant" and r["shared_pool"]
    assert sum(r["allocation"].values()) == r["sellable_units"]


def test_unconfirmed_inbound_gets_no_credit_and_planned_is_zero():
    r = allocate(mug(inbound=[Inbound("PO-4", 500, 2, "planned")]))
    assert r["inbound_credit_units"] == 0 and r["time_to_replenish_days"] is None


def test_negative_margin_channel_gets_nothing_unless_clearance():
    chs = [Channel("DTC", 10, 0.9, 5, 5, 5), Channel("Amazon", -2, 1.0, 5, 5, 5)]
    r = allocate(mug(channels=chs, inbound=[]))
    assert r["allocation"]["Amazon"] == 0
    r2 = allocate(mug(channels=chs, inbound=[], clearance=True))
    assert r2["allocation"]["Amazon"] > 0


def test_locked_and_stale_block_writes():
    assert not allocate(mug(locked=True))["write_allowed"]
    r = allocate(mug(stock_age_hours=3))
    assert not r["write_allowed"] and r["confidence"] == "low"


def test_dead_inventory_is_flagged():
    r = allocate(mug(on_hand=9000, committed=0, inbound=[]))
    assert any("Dead inventory" in x for x in r["risks"])


def test_step_toward_limits_change_to_25_percent():
    cur = {"A": 100, "B": 100}
    assert step_toward(cur, {"A": 200, "B": 0}, 300) == {"A": 125, "B": 75}
    assert step_toward(cur, {"A": 200, "B": 0}, 190) == {"A": 115, "B": 75}
    assert step_toward(cur, {"A": 200, "B": 0}, 150) is None
    assert step_toward({}, {"A": 50}, 50) == {"A": 50}
