import json

from btc_contract_backtest.runtime.runtime_state_store import JsonRuntimeStateStore


def test_recovery_convergence_preserves_legacy_and_normalized_fields(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({
        "capital": 1500.0,
        "position": {"symbol": "BTC/USDT", "side": 1, "quantity": 0.2, "leverage": 3},
        "orders": [{"order_id": "abc"}],
        "risk_events": [{"event_type": "reconcile_failed"}],
        "last_payload": {"event": "hold"},
        "halted": True,
        "halt_reason": "legacy",
    }))

    store = JsonRuntimeStateStore(str(path), mode="paper", symbol="BTC/USDT", leverage=3)
    state = store.load_normalized_state()

    assert state["capital"] == 1500.0
    assert state["position"]["quantity"] == 0.2
    assert state["orders"][0]["order_id"] == "abc"
    assert state["last_runtime_snapshot"]["event"] == "hold"
    assert state["watchdog"]["halted"] is True
