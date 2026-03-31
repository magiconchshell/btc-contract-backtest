from pathlib import Path

from btc_contract_backtest.live.exchange_adapter import AdapterResult
from btc_contract_backtest.live.recovery_orchestrator import RecoveryOrchestrator
from btc_contract_backtest.live.submit_ledger import SubmitIntent, SubmitLedger


class RecoveryAdapter:
    def fetch_open_orders(self):
        return AdapterResult(
            ok=True,
            payload=[
                {"id": "ex-1", "clientOrderId": "c1", "status": "open"},
                {"id": "ex-2", "clientOrderId": "c-remote-only", "status": "open"},
            ],
        )

    def fetch_positions(self):
        return AdapterResult(
            ok=True,
            payload=[{"symbol": "BTC/USDT", "positionAmt": "1", "entryPrice": "45000"}],
        )

    def fetch_open_orders_by_client_order_id(self, client_order_id):
        if client_order_id == "c1":
            return AdapterResult(
                ok=True,
                payload=[{"id": "ex-1", "clientOrderId": "c1", "status": "open"}],
            )
        return AdapterResult(ok=True, payload=[])


class ReplayTerminalAdapter:
    def fetch_open_orders(self):
        return AdapterResult(ok=True, payload=[])

    def fetch_positions(self):
        return AdapterResult(
            ok=True,
            payload=[
                {"symbol": "BTC/USDT", "positionAmt": "0.25", "entryPrice": "45000"}
            ],
        )

    def fetch_open_orders_by_client_order_id(self, client_order_id):
        return AdapterResult(ok=True, payload=[])


def test_recovery_orchestrator_recovers_pending_intent_and_flags_orphans(tmp_path):
    ledger = SubmitLedger(str(Path(tmp_path) / "submit_ledger.json"))
    ledger.upsert(
        SubmitIntent(
            request_id="r1",
            client_order_id="c1",
            symbol="BTC/USDT",
            signal=1,
            quantity=1.0,
            notional=100.0,
            state="unknown",
        )
    )
    orchestrator = RecoveryOrchestrator(RecoveryAdapter(), ledger)

    report = orchestrator.recover(
        local_orders=[
            {"order_id": "o-local", "client_order_id": "c-local-only", "state": "new"}
        ],
        local_position={"side": 1, "quantity": 1.0, "entry_price": 45000.0},
        events=[
            {
                "sequence": 1,
                "event_type": "order_new",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "payload": {"client_order_id": "c1"},
            },
            {
                "sequence": 2,
                "event_type": "order_trade_update",
                "timestamp": "2026-01-01T00:00:01+00:00",
                "payload": {
                    "client_order_id": "c1",
                    "execution_type": "trade",
                    "last_fill_quantity": "1",
                    "last_fill_price": "45000",
                },
            },
        ],
        event_boundary={
            "last_sequence": 2,
            "poll_fallback_required": True,
            "upstream": {"connected": False, "listen_key_present": False},
        },
        environment="testnet",
    ).to_dict()
    assert report["ok"] is False
    assert len(report["recovered_intents"]) == 1
    assert len(report["remote_only_orders"]) == 2
    assert len(report["local_only_orders"]) == 1
    assert report["startup_convergence"]["environment"] == "testnet"
    assert report["startup_convergence"]["watermark"]["replay_fill_event_count"] == 1
    assert report["startup_convergence"]["summary"]["critical_action_count"] >= 1
    assert "startup_convergence_blocked" in report["notes"]


def test_recovery_orchestrator_recovers_terminal_fill_from_replay_without_orphans(
    tmp_path,
):
    ledger = SubmitLedger(str(Path(tmp_path) / "submit_ledger.json"))
    ledger.upsert(
        SubmitIntent(
            request_id="r-filled",
            client_order_id="c-filled",
            symbol="BTC/USDT",
            signal=1,
            quantity=0.25,
            notional=25.0,
            state="unknown",
        )
    )
    orchestrator = RecoveryOrchestrator(ReplayTerminalAdapter(), ledger)

    report = orchestrator.recover(
        local_orders=[
            {
                "order_id": "o-local-filled",
                "client_order_id": "c-filled",
                "state": "new",
            }
        ],
        local_position={"side": 1, "quantity": 0.25, "entry_price": 45000.0},
        events=[
            {
                "sequence": 1,
                "event_type": "order_new",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "payload": {
                    "client_order_id": "c-filled",
                    "order_id": "ex-filled",
                    "status": "new",
                },
            },
            {
                "sequence": 2,
                "event_type": "order_trade_update",
                "timestamp": "2026-01-01T00:00:01+00:00",
                "payload": {
                    "client_order_id": "c-filled",
                    "order_id": "ex-filled",
                    "execution_type": "trade",
                    "status": "filled",
                    "filled_quantity": "0.25",
                    "last_fill_quantity": "0.25",
                    "average_price": "45000.0",
                },
            },
        ],
        event_boundary={
            "last_sequence": 2,
            "poll_fallback_required": False,
            "upstream": {"connected": True, "listen_key_present": True},
        },
        environment="testnet",
    ).to_dict()

    assert report["ok"] is True
    assert len(report["recovered_intents"]) == 1
    assert report["recovered_intents"][0]["state"] == "filled"
    assert report["recovered_intents"][0]["exchange_order_id"] == "ex-filled"
    assert report["recovered_intents"][0]["metadata"]["recovered_by"] == "event_replay"
    assert report["unresolved_intents"] == []
    assert report["remote_only_orders"] == []
    assert report["local_only_orders"] == []
    assert report["startup_convergence"]["ok"] is True
    assert report["startup_convergence"]["summary"]["critical_action_count"] == 0
