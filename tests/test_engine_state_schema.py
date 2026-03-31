import json

from btc_contract_backtest.runtime.engine_state_schema import normalize_legacy_state
from btc_contract_backtest.runtime.runtime_state_store import JsonRuntimeStateStore


def test_normalize_legacy_state_maps_old_fields_into_schema():
    legacy = {
        "capital": 1200.0,
        "position": {"symbol": "BTC/USDT", "side": 1, "quantity": 0.1, "leverage": 3},
        "risk_events": [{"event_type": "stale_data"}],
        "last_payload": {"event": "decision"},
        "last_heartbeat_at": "2026-01-01T00:00:00+00:00",
        "consecutive_failures": 2,
        "halted": True,
        "halt_reason": "test",
    }

    state = normalize_legacy_state(legacy, mode="shadow", symbol="BTC/USDT", leverage=3)

    assert state["mode"] == "shadow"
    assert state["capital"] == 1200.0
    assert state["last_runtime_snapshot"]["event"] == "decision"
    assert state["watchdog"]["halted"] is True
    assert state["position"]["symbol"] == "BTC/USDT"


def test_runtime_state_store_normalizes_existing_legacy_file(tmp_path):
    path = tmp_path / "legacy_state.json"
    path.write_text(
        json.dumps(
            {"capital": 900.0, "last_payload": {"event": "hold"}, "halted": False}
        )
    )

    store = JsonRuntimeStateStore(
        str(path), mode="paper", symbol="BTC/USDT", leverage=5
    )
    state = store.load_normalized_state()

    assert state["mode"] == "paper"
    assert state["capital"] == 900.0
    assert state["position"]["symbol"] == "BTC/USDT"
    assert state["last_runtime_snapshot"]["event"] == "hold"
