from btc_contract_backtest.runtime.runtime_state_store import JsonRuntimeStateStore


def test_paper_mode_order_state_records_can_be_upserted(tmp_path):
    store = JsonRuntimeStateStore(str(tmp_path / "paper_state.json"), mode="paper", symbol="BTC/USDT", leverage=3)
    store.upsert_order({"order_id": "o1", "state": "new", "submission_mode": "paper"})
    store.upsert_order({"order_id": "o1", "state": "filled", "submission_mode": "paper", "filled_quantity": 1.0})
    store.flush()

    state = store.get_state()
    assert len(state["orders"]) == 1
    assert state["orders"][0]["state"] == "filled"
    assert state["orders"][0]["submission_mode"] == "paper"


def test_governed_live_mode_order_state_records_can_be_upserted(tmp_path):
    store = JsonRuntimeStateStore(str(tmp_path / "live_state.json"), mode="governed_live", symbol="BTC/USDT", leverage=3)
    store.upsert_order({"order_id": "o2", "state": "new", "submission_mode": "governed_live", "client_order_id": "c2"})
    store.upsert_order({"order_id": "o2", "state": "acked", "submission_mode": "governed_live", "client_order_id": "c2", "exchange_order_id": "ex2"})
    store.flush()

    state = store.get_state()
    assert len(state["orders"]) == 1
    assert state["orders"][0]["state"] == "acked"
    assert state["orders"][0]["exchange_order_id"] == "ex2"
