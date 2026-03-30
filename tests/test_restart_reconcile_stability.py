import json

from btc_contract_backtest.runtime.runtime_state_store import JsonRuntimeStateStore


def test_restart_stability_keeps_operator_actions_and_fills(tmp_path):
    path = tmp_path / "state.json"

    store = JsonRuntimeStateStore(str(path), mode="governed_live", symbol="BTC/USDT", leverage=3)
    store.append_fill({"order_id": "o1", "fill_quantity": 0.1})
    store.append_operator_action({"action": "submit_intended_order", "result": "submitted"})
    store.set_watchdog({"halted": False, "consecutive_failures": 1})
    store.flush()

    reloaded = JsonRuntimeStateStore(str(path), mode="governed_live", symbol="BTC/USDT", leverage=3)
    state = reloaded.load_normalized_state()

    assert state["fills"][0]["order_id"] == "o1"
    assert state["operator_actions"][0]["action"] == "submit_intended_order"
    assert state["watchdog"]["consecutive_failures"] == 1


def test_reconcile_stability_state_can_accumulate_runtime_and_governance_context(tmp_path):
    path = tmp_path / "state.json"
    store = JsonRuntimeStateStore(str(path), mode="governed_live", symbol="BTC/USDT", leverage=3)

    store.set_governance_state({"mode": "approval_required", "emergency_stop": False})
    store.set_last_runtime_snapshot({"event": "decision", "signal": 1})
    store.set_state_fields(reconcile_report={"ok": True, "differences": []})
    store.flush()

    payload = json.loads(path.read_text())
    assert payload["governance_state"]["mode"] == "approval_required"
    assert payload["last_runtime_snapshot"]["signal"] == 1
    assert payload["reconcile_report"]["ok"] is True
