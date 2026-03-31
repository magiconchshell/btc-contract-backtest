from btc_contract_backtest.engine.execution_models import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)
from btc_contract_backtest.runtime.order_state_bridge import (
    apply_local_submit,
    apply_remote_status,
    canonical_record_from_order,
)
from btc_contract_backtest.runtime.order_state_machine import CanonicalOrderState


def test_order_state_bridge_maps_local_and_remote_events():
    order = Order(
        order_id="o1",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
        client_order_id="c1",
        created_at="2026-01-01T00:00:00+00:00",
    )
    record = canonical_record_from_order(order, submission_mode="paper")
    record = apply_local_submit(
        record, timestamp=order.created_at, payload={"signal": 1}
    )
    record = apply_remote_status(
        record,
        status=OrderStatus.PARTIALLY_FILLED.value,
        timestamp="2026-01-01T00:00:01+00:00",
        payload={"filled": 0.5},
        filled_quantity=0.5,
        avg_fill_price=100.0,
        exchange_order_id="ex1",
    )

    assert record.state == CanonicalOrderState.PARTIAL.value
    assert record.exchange_order_id == "ex1"
    assert len(record.local_events) == 1
    assert len(record.remote_events) == 1


def test_order_state_bridge_can_reach_terminal_state():
    order = Order(
        order_id="o1",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
    )
    record = canonical_record_from_order(order, submission_mode="governed_live")
    record = apply_local_submit(record, timestamp="2026-01-01T00:00:00+00:00")
    record = apply_remote_status(
        record,
        status=OrderStatus.FILLED.value,
        timestamp="2026-01-01T00:00:02+00:00",
        filled_quantity=1.0,
        avg_fill_price=101.0,
    )

    assert record.state == CanonicalOrderState.FILLED.value
    assert record.final_at == "2026-01-01T00:00:02+00:00"
