import pytest

from btc_contract_backtest.runtime.order_state_bridge import apply_local_submit, apply_remote_status, canonical_record_from_order, propagate_replace_chain
from btc_contract_backtest.runtime.order_state_machine import AmbiguousOrderState
from btc_contract_backtest.runtime.order_state_machine import CanonicalOrderState
from btc_contract_backtest.engine.execution_models import Order, OrderSide, OrderStatus, OrderType


def test_duplicate_remote_update_is_idempotent():
    order = Order(order_id="o1", symbol="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1.0)
    record = canonical_record_from_order(order, submission_mode="paper")
    record = apply_local_submit(record, timestamp="2026-01-01T00:00:00+00:00")

    record = apply_remote_status(record, status=OrderStatus.NEW.value, timestamp="2026-01-01T00:00:01+00:00", payload={"id": "ex1"}, exchange_order_id="ex1")
    record = apply_remote_status(record, status=OrderStatus.NEW.value, timestamp="2026-01-01T00:00:01+00:00", payload={"id": "ex1"}, exchange_order_id="ex1")

    assert record.state == CanonicalOrderState.NEW.value
    assert len(record.remote_events) == 1


def test_restart_after_ack_can_continue_to_fill():
    order = Order(order_id="o1", symbol="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1.0)
    record = canonical_record_from_order(order, submission_mode="governed_live")
    record = apply_local_submit(record, timestamp="2026-01-01T00:00:00+00:00")
    record = apply_remote_status(record, status=OrderStatus.NEW.value, timestamp="2026-01-01T00:00:01+00:00", payload={"id": "ex1"}, exchange_order_id="ex1")

    # simulate restart by serializing and reusing the record fields
    restored = canonical_record_from_order(order, submission_mode="governed_live")
    restored.state = record.state
    restored.exchange_order_id = record.exchange_order_id
    restored.local_events = list(record.local_events)
    restored.remote_events = list(record.remote_events)
    restored.acked_at = record.acked_at

    restored = apply_remote_status(restored, status=OrderStatus.FILLED.value, timestamp="2026-01-01T00:00:02+00:00", filled_quantity=1.0, avg_fill_price=101.0)
    assert restored.state == CanonicalOrderState.FILLED.value
    assert restored.final_at == "2026-01-01T00:00:02+00:00"


def test_terminal_remote_state_is_stable_across_late_partial_updates():
    order = Order(order_id="o-term", symbol="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1.0)
    record = canonical_record_from_order(order, submission_mode="governed_live")
    record = apply_local_submit(record, timestamp="2026-01-01T00:00:00+00:00")
    record = apply_remote_status(record, status=OrderStatus.FILLED.value, timestamp="2026-01-01T00:00:01+00:00", filled_quantity=1.0, avg_fill_price=100.0)

    same = apply_remote_status(record, status=OrderStatus.FILLED.value, timestamp="2026-01-01T00:00:02+00:00", filled_quantity=1.0, avg_fill_price=100.0)
    assert same.state == CanonicalOrderState.FILLED.value
    assert same.final_at == "2026-01-01T00:00:01+00:00"


def test_apply_remote_status_quarantines_unsafe_ambiguity():
    order = Order(order_id="o1", symbol="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1.0)
    record = canonical_record_from_order(order, submission_mode="governed_live")
    record = apply_local_submit(record, timestamp="2026-01-01T00:00:00+00:00")
    record = apply_remote_status(record, status=OrderStatus.CANCELED.value, timestamp="2026-01-01T00:00:03+00:00", payload={"external_sequence": "30"})

    with pytest.raises(AmbiguousOrderState):
        apply_remote_status(
            record,
            status=OrderStatus.FILLED.value,
            timestamp="2026-01-01T00:00:02+00:00",
            payload={"external_sequence": "20", "filled": 1.0},
            filled_quantity=1.0,
        )

    assert record.tags["quarantine"]["blocked"] is True
    assert record.tags["quarantine"]["incoming_status"] == CanonicalOrderState.FILLED.value


def test_apply_remote_fill_after_replace_marks_duplicate_exposure_risk():
    parent = canonical_record_from_order(
        Order(order_id="o1", symbol="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1.0),
        submission_mode="governed_live",
    )
    parent = apply_local_submit(parent, timestamp="2026-01-01T00:00:00+00:00")
    child = canonical_record_from_order(
        Order(order_id="o2", symbol="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=0.6),
        submission_mode="governed_live",
    )
    propagate_replace_chain(parent, child)

    updated = apply_remote_status(
        parent,
        status=OrderStatus.FILLED.value,
        timestamp="2026-01-01T00:00:02+00:00",
        payload={"external_sequence": "40", "filled": 1.0},
        filled_quantity=1.0,
    )

    assert updated.state == CanonicalOrderState.FILLED.value
    assert updated.tags["duplicate_exposure_risk"]["blocked"] is True
    assert updated.tags["duplicate_exposure_risk"]["replacement_order_id"] == "o2"
    assert updated.tags["quarantine"]["reason"] == "late_fill_after_replace_intent"


def test_propagate_replace_chain_preserves_root_and_lineage():
    parent = canonical_record_from_order(
        Order(order_id="o1", symbol="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1.0),
        submission_mode="governed_live",
    )
    child = canonical_record_from_order(
        Order(order_id="o2", symbol="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=0.6),
        submission_mode="governed_live",
    )

    propagated = propagate_replace_chain(parent, child)

    assert propagated.tags["replace_chain_root_order_id"] == "o1"
    assert propagated.tags["replaces_order_id"] == "o1"
    assert propagated.tags["replacement_depth"] == 1
    assert parent.tags["replaced_by_order_id"] == "o2"
