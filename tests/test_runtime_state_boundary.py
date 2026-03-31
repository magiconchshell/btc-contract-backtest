import json

from btc_contract_backtest.runtime.runtime_state_store import JsonRuntimeStateStore


def test_json_runtime_state_store_records_steps_and_state(tmp_path):
    path = tmp_path / "runtime_state.json"
    store = JsonRuntimeStateStore(str(path))

    store.set_state_fields(capital=1000.0, halted=False)
    store.record_runtime_step(
        type(
            "Step",
            (),
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "event": "decision",
                "signal": 1,
                "snapshot": {"close": 100.0},
                "intended_order": {"quantity": 1.0},
                "metadata": {"stage": "decision"},
            },
        )()
    )
    store.record_risk_event({"event_type": "stale_data", "severity": "critical"})
    store.save()

    payload = json.loads(path.read_text())
    assert payload["capital"] == 1000.0
    assert payload["halted"] is False
    assert payload["runtime_steps"][0]["event"] == "decision"
    assert payload["risk_events"][0]["event_type"] == "stale_data"


def test_json_runtime_state_store_loads_existing_state(tmp_path):
    path = tmp_path / "runtime_state.json"
    path.write_text(
        json.dumps({"capital": 900.0, "runtime_steps": [], "risk_events": []})
    )

    store = JsonRuntimeStateStore(str(path))
    store.set_state_fields(halted=True)
    store.save()

    payload = json.loads(path.read_text())
    assert payload["capital"] == 900.0
    assert payload["halted"] is True
