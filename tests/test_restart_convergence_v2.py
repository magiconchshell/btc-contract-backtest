import json
from pathlib import Path

from btc_contract_backtest.live.restart_convergence import (
    build_execution_replay_summary,
    build_position_convergence,
    build_startup_convergence_report,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "gate_b_restart_convergence_cases.json"


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
        local_position={"side": 1, "quantity": 0.25, "entry_price": 45000.0},
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
            {"sequence": 9, "event_type": "order_new", "timestamp": "2026-01-01T00:00:00+00:00", "payload": {"client_order_id": "cid-missing-remote"}},
            {"sequence": 10, "event_type": "order_trade_update", "timestamp": "2026-01-01T00:00:01+00:00", "payload": {"client_order_id": "cid-missing-remote", "execution_type": "trade", "last_fill_quantity": "0.25", "last_fill_price": "45000.0", "average_price": "45000.0"}},
        ],
        boundary={
            "last_sequence": 10,
            "last_event_timestamp": "2026-01-01T00:00:01+00:00",
            "last_received_at": "2026-01-01T00:00:02+00:00",
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
    assert {item["classification"] for item in report["unresolved_intents"]} == {
        "replay_partial_fill_without_terminal",
        "missing_client_order_id",
    }
    assert any(action["action"] == "replay_and_lookup_unresolved_intents" for action in report["actions"])
    assert any(action["action"] == "adopt_or_cancel_remote_only_orders" for action in report["actions"])


def test_gate_b_restart_convergence_corpus_expectations_hold():
    cases = json.loads(FIXTURES.read_text(encoding="utf-8"))

    for case in cases:
        report = build_startup_convergence_report(
            environment="testnet",
            local_position=case["local_position"],
            remote_position=case["remote_position"],
            unresolved_intents=case["unresolved_intents"],
            remote_only_orders=case["remote_only_orders"],
            local_only_orders=case["local_only_orders"],
            events=case["events"],
            boundary=case["boundary"],
        ).to_dict()
        expected = case["expected"]

        assert report["ok"] is expected["ok"], case["name"]
        assert report["summary"]["critical_action_count"] == expected["critical_action_count"], case["name"]
        assert report["summary"]["warning_action_count"] == expected["warning_action_count"], case["name"]
        assert sorted(item["classification"] for item in report["unresolved_intents"]) == sorted(expected["unresolved_classifications"]), case["name"]
        assert report["watermark"]["replay_event_count"] == expected["replay_event_count"], case["name"]
        assert report["watermark"]["replayable_event_count"] == expected["replayable_event_count"], case["name"]
        assert report["watermark"]["replay_order_event_count"] == expected["replay_order_event_count"], case["name"]
        assert report["watermark"]["replay_fill_event_count"] == expected["replay_fill_event_count"], case["name"]
        assert report["replay_hooks"]["last_order_update_sequence"] == expected["last_order_update_sequence"], case["name"]
        assert report["replay_hooks"]["last_fill_sequence"] == expected["last_fill_sequence"], case["name"]
