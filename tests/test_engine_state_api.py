from btc_contract_backtest.runtime.runtime_state_store import JsonRuntimeStateStore


def test_engine_state_store_canonical_api_roundtrip(tmp_path):
    store = JsonRuntimeStateStore(str(tmp_path / "state.json"), mode="paper", symbol="BTC/USDT", leverage=3)

    store.set_mode("paper")
    store.set_capital(1000.0)
    store.set_position({"symbol": "BTC/USDT", "side": 1, "quantity": 0.1})
    store.set_orders([{"order_id": "o1"}])
    store.append_fill({"order_id": "o1", "fill_quantity": 0.1})
    store.set_trades([{"trade_id": "t1"}])
    store.set_governance_state({"mode": "paper"})
    store.append_operator_action({"action": "submit_intended_order"})
    store.set_watchdog({"halted": False})
    store.set_last_runtime_snapshot({"event": "decision"})
    store.flush()

    payload = store.get_state()
    assert payload["capital"] == 1000.0
    assert payload["position"]["side"] == 1
    assert payload["orders"][0]["order_id"] == "o1"
    assert payload["fills"][0]["order_id"] == "o1"
    assert payload["operator_actions"][0]["action"] == "submit_intended_order"
    assert payload["last_runtime_snapshot"]["event"] == "decision"
