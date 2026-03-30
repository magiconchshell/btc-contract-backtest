from btc_contract_backtest.runtime.order_state_bridge import apply_local_submit, apply_remote_status, canonical_record_from_order
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
