import pytest

from btc_contract_backtest.runtime.order_state_machine import (
    AmbiguousOrderState,
    CanonicalOrderState,
    InvalidOrderTransition,
    OrderEvent,
    OrderStateMachine,
)


def test_order_state_machine_allows_valid_transition_chain():
    record = OrderStateMachine.create_record(
        order_id="o1",
        client_order_id="c1",
        symbol="BTC/USDT",
        side="buy",
        order_type="market",
        quantity=1.0,
        submission_mode="paper",
        created_at="2026-01-01T00:00:00+00:00",
    )

    OrderStateMachine.apply_transition(
        record,
        next_state=CanonicalOrderState.ACKED.value,
        event=OrderEvent(
            source="remote",
            event_type="ack",
            state="acked",
            timestamp="2026-01-01T00:00:01+00:00",
        ),
        exchange_order_id="ex1",
    )
    OrderStateMachine.apply_transition(
        record,
        next_state=CanonicalOrderState.PARTIAL.value,
        event=OrderEvent(
            source="remote",
            event_type="partial_fill",
            state="partial",
            timestamp="2026-01-01T00:00:02+00:00",
        ),
        filled_quantity=0.4,
        avg_fill_price=100.0,
    )
    OrderStateMachine.apply_transition(
        record,
        next_state=CanonicalOrderState.FILLED.value,
        event=OrderEvent(
            source="remote",
            event_type="filled",
            state="filled",
            timestamp="2026-01-01T00:00:03+00:00",
        ),
        filled_quantity=1.0,
        avg_fill_price=100.5,
    )

    assert record.state == CanonicalOrderState.FILLED.value
    assert record.exchange_order_id == "ex1"
    assert record.filled_quantity == 1.0
    assert record.acked_at == "2026-01-01T00:00:01+00:00"
    assert record.final_at == "2026-01-01T00:00:03+00:00"
    assert len(record.remote_events) == 3


def test_order_state_machine_rejects_illegal_transition():
    record = OrderStateMachine.create_record(order_id="o1")
    OrderStateMachine.apply_transition(
        record,
        next_state=CanonicalOrderState.CANCELED.value,
        event=OrderEvent(
            source="remote",
            event_type="canceled",
            state="canceled",
            timestamp="2026-01-01T00:00:01+00:00",
        ),
    )

    with pytest.raises(InvalidOrderTransition):
        OrderStateMachine.apply_transition(
            record,
            next_state=CanonicalOrderState.ACKED.value,
            event=OrderEvent(
                source="remote",
                event_type="ack",
                state="acked",
                timestamp="2026-01-01T00:00:02+00:00",
            ),
        )


def test_order_state_machine_is_idempotent_for_duplicate_event():
    record = OrderStateMachine.create_record(order_id="o1")
    event = OrderEvent(
        source="remote",
        event_type="ack",
        state="acked",
        timestamp="2026-01-01T00:00:01+00:00",
    )

    OrderStateMachine.apply_transition(
        record, next_state=CanonicalOrderState.ACKED.value, event=event
    )
    OrderStateMachine.apply_transition(
        record, next_state=CanonicalOrderState.ACKED.value, event=event
    )

    assert record.state == CanonicalOrderState.ACKED.value
    assert len(record.remote_events) == 1


def test_order_state_store_upsert_replaces_existing_order(tmp_path):
    from btc_contract_backtest.runtime.runtime_state_store import JsonRuntimeStateStore

    store = JsonRuntimeStateStore(
        str(tmp_path / "state.json"), mode="paper", symbol="BTC/USDT", leverage=3
    )
    store.upsert_order({"order_id": "o1", "state": "new", "client_order_id": "c1"})
    store.upsert_order({"order_id": "o1", "state": "acked", "client_order_id": "c1"})

    assert len(store.get_state()["orders"]) == 1
    assert store.get_state()["orders"][0]["state"] == "acked"


def test_order_state_machine_ignores_out_of_order_regression_after_partial_fill():
    record = OrderStateMachine.create_record(order_id="o1", quantity=1.0)
    OrderStateMachine.apply_transition(
        record,
        next_state=CanonicalOrderState.PARTIAL.value,
        event=OrderEvent(
            source="remote",
            event_type="partial_fill",
            state="partial",
            timestamp="2026-01-01T00:00:02+00:00",
            payload={"external_sequence": "20", "filled": 0.4},
        ),
        filled_quantity=0.4,
    )

    OrderStateMachine.apply_transition(
        record,
        next_state=CanonicalOrderState.ACKED.value,
        event=OrderEvent(
            source="remote",
            event_type="ack",
            state="acked",
            timestamp="2026-01-01T00:00:01+00:00",
            payload={"external_sequence": "10"},
        ),
    )

    assert record.state == CanonicalOrderState.PARTIAL.value
    assert record.filled_quantity == 0.4
    assert record.tags["residual_quantity"] == 0.6


def test_order_state_machine_quarantines_conflicting_terminal_out_of_order_event():
    record = OrderStateMachine.create_record(order_id="o1", quantity=1.0)
    OrderStateMachine.apply_transition(
        record,
        next_state=CanonicalOrderState.CANCELED.value,
        event=OrderEvent(
            source="remote",
            event_type="canceled",
            state="canceled",
            timestamp="2026-01-01T00:00:03+00:00",
            payload={"external_sequence": "30"},
        ),
    )

    with pytest.raises(AmbiguousOrderState):
        OrderStateMachine.apply_transition(
            record,
            next_state=CanonicalOrderState.FILLED.value,
            event=OrderEvent(
                source="remote",
                event_type="filled",
                state="filled",
                timestamp="2026-01-01T00:00:02+00:00",
                payload={"external_sequence": "20", "filled": 1.0},
            ),
            filled_quantity=1.0,
        )


def test_order_state_machine_uses_numeric_remote_sequence_ordering():
    record = OrderStateMachine.create_record(order_id="o1", quantity=1.0)
    OrderStateMachine.apply_transition(
        record,
        next_state=CanonicalOrderState.PARTIAL.value,
        event=OrderEvent(
            source="remote",
            event_type="partial_fill",
            state="partial",
            timestamp="2026-01-01T00:00:02+00:00",
            payload={"external_sequence": "100", "filled": 0.25},
        ),
        filled_quantity=0.25,
    )

    OrderStateMachine.apply_transition(
        record,
        next_state=CanonicalOrderState.ACKED.value,
        event=OrderEvent(
            source="remote",
            event_type="ack",
            state="acked",
            timestamp="2026-01-01T00:00:01+00:00",
            payload={"external_sequence": "99"},
        ),
    )

    assert record.state == CanonicalOrderState.PARTIAL.value
    assert record.tags["last_remote_sequence"] == "100"
