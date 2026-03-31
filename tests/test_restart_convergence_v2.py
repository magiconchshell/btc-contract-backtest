from btc_contract_backtest.live.restart_convergence import (
    build_execution_replay_summary,
    build_position_convergence,
    build_startup_convergence_report,
)


def test_position_convergence_detects_entry_basis_quantity_and_side_mismatch():
    report = build_position_convergence(
        local_position={"side": 1, "quantity": 0.5, "entry_price": 45000.0},
        remote_position={"positionAmt": "-0.25", "entryPrice": "45100.0"},
    ).to_dict()

    assert report["ok"] is False
    assert set(report["mismatch_types"]) == {"side", "quantity", "entry_basis"}
    assert report["severity"] == "critical"


def test_startup_convergence_classifies_ambiguous_intents_and_replay_hooks():
    report = build_startup_convergence_report(
        environment="testnet",
        local_position={"symbol": "BTC/USDT", "side": 1, "quantity": 0.25, "entry_price": 45000.0},
        remote_position={"positionAmt": "0.25", "entryPrice": "45000.0"},
        unresolved_intents=[
            {"request_id": "r1", "client_order_id": "cid-missing-remote", "state": "unknown"},
            {"request_id": "r2", "client_order_id": None, "state": "submit_pending"},
        ],
        remote_only_orders=[
            {"id": "ex-1", "clientOrderId": "remote-extra", "status": "open"},
        ],
        local_only_orders=[
            {"order_id": "local-1", "client_order_id": "local-extra", "state": "new"},
        ],
        events=[
            {"sequence": 9, "event_type": "order_new", "timestamp": "2026-01-01T00:00:00+00:00", "payload": {"client_order_id": "cid-missing-remote", "side": "buy", "order_type": "market"}},
            {"sequence": 10, "event_type": "order_trade_update", "timestamp": "2026-01-01T00:00:01+00:00", "payload": {"client_order_id": "cid-missing-remote", "execution_type": "trade", "status": "filled", "last_fill_quantity": "0.25", "filled_quantity": "0.25", "last_fill_price": "45000.0", "average_price": "45000.0"}},
            {"sequence": 11, "event_type": "account_update", "timestamp": "2026-01-01T00:00:02+00:00", "payload": {"balances": [{"a": "USDT", "wb": "1000"}], "positions": [{"s": "BTCUSDT", "pa": "0.25", "ep": "45000.0"}]}},
        ],
        boundary={
            "last_sequence": 11,
            "last_event_timestamp": "2026-01-01T00:00:02+00:00",
            "last_received_at": "2026-01-01T00:00:03+00:00",
            "last_external_sequence": "99",
            "poll_fallback_required": True,
            "upstream": {"connected": False, "listen_key_present": False},
        },
    ).to_dict()

    assert report["ok"] is False
    assert report["environment"] == "testnet"
    assert report["watermark"]["replay_fill_event_count"] == 1
    assert report["replay_hooks"]["last_fill_sequence"] == 10
    assert report["summary"]["unresolved_intent_count"] == 2
    assert report["replay_hooks"]["authoritative_replay"]["derived_position"]["quantity"] == 0.25
    assert report["replay_hooks"]["authoritative_replay"]["order_records"][0]["state"] == "filled"
    assert {item["classification"] for item in report["unresolved_intents"]} == {
        "replay_terminal_state",
        "missing_client_order_id",
    }
    assert any(action["action"] == "replay_and_lookup_unresolved_intents" for action in report["actions"])
    assert any(action["action"] == "adopt_or_cancel_remote_only_orders" for action in report["actions"])


def test_startup_convergence_accepts_replay_terminal_fill_without_blocking_intent():
    report = build_startup_convergence_report(
        environment="testnet",
        local_position={"symbol": "BTC/USDT", "side": 1, "quantity": 0.25, "entry_price": 45000.0},
        remote_position={"positionAmt": "0.25", "entryPrice": "45000.0"},
        unresolved_intents=[
            {"request_id": "r-filled", "client_order_id": "cid-filled", "state": "unknown"},
        ],
        remote_only_orders=[],
        local_only_orders=[],
        events=[
            {"sequence": 1, "event_type": "order_new", "timestamp": "2026-01-01T00:00:00+00:00", "payload": {"client_order_id": "cid-filled", "order_id": "ex-filled", "status": "new"}},
            {"sequence": 2, "event_type": "order_trade_update", "timestamp": "2026-01-01T00:00:01+00:00", "payload": {"client_order_id": "cid-filled", "order_id": "ex-filled", "execution_type": "trade", "status": "filled", "filled_quantity": "0.25", "last_fill_quantity": "0.25", "average_price": "45000.0"}},
        ],
        boundary={
            "last_sequence": 2,
            "poll_fallback_required": False,
            "upstream": {"connected": True, "listen_key_present": True},
        },
    ).to_dict()

    assert report["ok"] is True
    assert report["summary"]["blocking_unresolved_intent_count"] == 0
    assert report["summary"]["critical_action_count"] == 0
    assert report["unresolved_intents"][0]["classification"] == "replay_terminal_state"
    assert report["replay_hooks"]["terminal_order_count"] == 1
    assert report["actions"] == [{
        "action": "resume_guarded_live",
        "severity": "info",
        "reason": "Startup convergence found no blocking divergence",
        "metadata": {},
    }]


def test_execution_replay_summary_is_deterministic_for_out_of_order_events():
    summary = build_execution_replay_summary(
        [
            {"sequence": 10, "event_type": "order_trade_update", "timestamp": "2026-01-01T00:00:02+00:00", "payload": {"client_order_id": "cid-1", "status": "partially_filled", "execution_type": "trade", "last_fill_quantity": "0.25", "filled_quantity": "0.25", "average_price": "45010.0"}, "external_sequence": "100"},
            {"sequence": 2, "event_type": "order_new", "timestamp": "2026-01-01T00:00:01+00:00", "payload": {"client_order_id": "cid-1", "side": "buy", "order_type": "market"}, "external_sequence": "99"},
            {"sequence": 11, "event_type": "account_update", "timestamp": "2026-01-01T00:00:03+00:00", "payload": {"balances": [{"a": "USDT", "wb": "999.5"}], "positions": [{"s": "BTCUSDT", "pa": "0.25", "ep": "45010.0"}]}, "external_sequence": "101"},
        ],
        symbol="BTC/USDT",
    )

    assert summary["applied_event_count"] == 3
    assert summary["skipped_event_count"] == 0
    assert summary["last_applied_sequence"] == 11
    assert summary["last_applied_external_sequence"] == "101"
    assert summary["order_records"][0]["state"] == "partial"
    assert summary["derived_position"]["side"] == 1
    assert summary["derived_account"]["balances"][0]["a"] == "USDT"
