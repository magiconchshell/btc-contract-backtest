from pathlib import Path

from btc_contract_backtest.config.models import ContractSpec, LiveRiskConfig, RiskConfig
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.event_stream import EventRecorder
from btc_contract_backtest.live.exchange_adapter import AdapterResult
from btc_contract_backtest.live.fault_injection import (
    EventSequenceMonitor,
    ResidualRiskInspector,
    SoakHarness,
)
from btc_contract_backtest.live.governance import (
    AlertSink,
    GovernancePolicy,
    OperatorApprovalQueue,
    TradingMode,
)
from btc_contract_backtest.live.guarded_live import GuardedLiveExecutor
from btc_contract_backtest.live.recovery_orchestrator import RecoveryOrchestrator
from btc_contract_backtest.live.submit_ledger import SubmitLedger


class AmbiguousSubmitAdapter:
    def __init__(self):
        self.client_orders = {}
        self.submit_calls = 0
        self.open_fetch_calls = 0

    def submit_order(self, order):
        self.submit_calls += 1
        remote = {
            "id": f"ex-{self.submit_calls}",
            "clientOrderId": order.client_order_id,
            "status": "open",
        }
        self.client_orders[order.client_order_id] = remote
        return AdapterResult(ok=False, error="timeout_after_accept")

    def fetch_open_orders_by_client_order_id(self, client_order_id):
        remote = self.client_orders.get(client_order_id)
        payload = [remote] if remote is not None else []
        return AdapterResult(ok=True, payload=payload)

    def fetch_open_orders(self):
        self.open_fetch_calls += 1
        return AdapterResult(ok=True, payload=list(self.client_orders.values()))


class PostCrashLookupAdapter:
    def __init__(self, remote_orders, remote_positions=None):
        self.remote_orders = list(remote_orders)
        self.remote_positions = list(remote_positions or [])

    def fetch_open_orders(self):
        return AdapterResult(ok=True, payload=list(self.remote_orders))

    def fetch_positions(self):
        return AdapterResult(ok=True, payload=list(self.remote_positions))

    def fetch_open_orders_by_client_order_id(self, client_order_id):
        matches = [
            row
            for row in self.remote_orders
            if row.get("clientOrderId") == client_order_id
        ]
        return AdapterResult(ok=True, payload=matches)


def _executor(tmp_path, adapter, *, ledger_name="submit_ledger.json"):
    policy = GovernancePolicy(
        RiskConfig(),
        LiveRiskConfig(),
        TradingMode.GUARDED_LIVE,
        contract=ContractSpec(symbol="BTC/USDT", leverage=3, lot_size=0.001),
    )
    approvals = OperatorApprovalQueue(str(Path(tmp_path) / "approvals.json"))
    alerts = AlertSink(str(Path(tmp_path) / "alerts.jsonl"))
    audit = AuditLogger(str(Path(tmp_path) / "audit.jsonl"))
    ledger = SubmitLedger(str(Path(tmp_path) / ledger_name))
    return (
        GuardedLiveExecutor(
            adapter, policy, approvals, alerts, audit, submit_ledger=ledger
        ),
        ledger,
    )


def test_event_sequence_monitor_flags_gap_and_reconnect_need(tmp_path):
    harness = SoakHarness(EventRecorder(str(tmp_path / "events.jsonl")))

    result = harness.ingest_events(
        [
            {
                "event_type": "order_trade_update",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "payload": {"status": "new"},
                "source": "binance_futures_user_data:testnet",
                "source_kind": "websocket",
                "symbol": "BTC/USDT",
                "external_sequence": "100",
            },
            {
                "event_type": "order_trade_update",
                "timestamp": "2026-01-01T00:00:01+00:00",
                "payload": {"status": "partial"},
                "source": "binance_futures_user_data:testnet",
                "source_kind": "websocket",
                "symbol": "BTC/USDT",
                "external_sequence": "102",
            },
            {
                "event_type": "order_trade_update",
                "timestamp": "2026-01-01T00:00:02+00:00",
                "payload": {"status": "filled"},
                "source": "binance_futures_user_data:testnet",
                "source_kind": "websocket",
                "symbol": "BTC/USDT",
                "external_sequence": "101",
            },
        ]
    )

    counts = result["monitor"]["counts"]
    assert result["monitor"]["reconnect_required"] is True
    assert counts["gap"] == 1
    assert counts["reorder_or_duplicate"] == 1
    assert result["boundary"]["last_external_sequence"] == "101"


def test_ambiguous_submit_recovers_without_duplicate_submit(tmp_path):
    adapter = AmbiguousSubmitAdapter()
    executor, ledger = _executor(tmp_path, adapter)

    result = executor.submit_intended_order(
        symbol="BTC/USDT",
        signal=1,
        quantity=0.001,
        notional=10.0,
        stale=False,
        reconcile_ok=True,
        watchdog_halted=False,
    )

    assert result["status"] == "submitted_recovered"
    assert adapter.submit_calls == 1
    stored = ledger.get(result["request_id"])
    assert stored is not None
    assert stored["state"] == "submitted"
    assert stored["metadata"]["recovered_from"] == "client_order_lookup"


def test_recovery_orchestrator_converges_unknown_submit_after_restart(tmp_path):
    ledger_path = Path(tmp_path) / "submit_ledger.json"
    ledger = SubmitLedger(str(ledger_path))
    ledger.upsert(
        {
            "request_id": "r-1",
            "client_order_id": "c-1",
            "symbol": "BTC/USDT",
            "signal": 1,
            "quantity": 0.001,
            "notional": 10.0,
            "state": "unknown",
            "attempts": [],
            "metadata": {"reason": "crash_during_submit"},
        }
    )

    adapter = PostCrashLookupAdapter(
        [
            {"id": "ex-1", "clientOrderId": "c-1", "status": "open"},
        ]
    )
    report = (
        RecoveryOrchestrator(adapter, SubmitLedger(str(ledger_path)))
        .recover(
            local_orders=[
                {"order_id": "o-1", "client_order_id": "c-1", "state": "new"}
            ],
            local_position={},
            events=[
                {
                    "sequence": 1,
                    "event_type": "order_trade_update",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "payload": {"client_order_id": "c-1", "execution_type": "trade"},
                    "replayable": True,
                }
            ],
            event_boundary={
                "last_sequence": 1,
                "last_event_timestamp": "2026-01-01T00:00:00+00:00",
                "last_received_at": "2026-01-01T00:00:01+00:00",
                "last_external_sequence": "1",
                "poll_fallback_required": False,
                "upstream": {"connected": True, "listen_key_present": True},
            },
        )
        .to_dict()
    )

    assert report["ok"] is True
    assert len(report["recovered_intents"]) == 1
    assert report["recovered_intents"][0]["exchange_order_id"] == "ex-1"
    assert len(report["remote_only_orders"]) == 0
    assert report["startup_convergence"]["summary"]["critical_action_count"] == 0


def test_residual_risk_inspector_flags_double_open_cancel_replace_race():
    report = ResidualRiskInspector.inspect_cancel_replace(
        cancel_order_id="old-1",
        replacement_order_id="new-1",
        remote_orders=[
            {"id": "old-1", "status": "open"},
            {"id": "new-1", "status": "open"},
        ],
    ).to_dict()

    assert report["ok"] is False
    assert report["status"] == "double_open_risk"
    assert "both_old_and_new_orders_open" in report["notes"]


def test_residual_risk_inspector_flags_fill_then_replace_exposure():
    report = ResidualRiskInspector.inspect_cancel_replace(
        cancel_order_id="old-1",
        replacement_order_id="new-1",
        remote_orders=[
            {"id": "old-1", "status": "filled"},
            {"id": "new-1", "status": "open"},
        ],
    ).to_dict()

    assert report["ok"] is False
    assert report["status"] == "residual_exposure_risk"
    assert report["residual_filled_order_ids"] == ["old-1"]


def test_event_sequence_monitor_tracks_symbol_partitions_and_non_numeric_sequences():
    monitor = EventSequenceMonitor()

    first = monitor.observe(
        {
            "source": "binance_futures_user_data:testnet",
            "symbol": "BTC/USDT",
            "external_sequence": "10",
        }
    )
    second = monitor.observe(
        {
            "source": "binance_futures_user_data:testnet",
            "symbol": "ETH/USDT",
            "external_sequence": "10",
        }
    )
    third = monitor.observe(
        {
            "source": "binance_futures_user_data:testnet",
            "symbol": "BTC/USDT",
            "external_sequence": "11",
        }
    )
    bad = monitor.observe(
        {
            "source": "binance_futures_user_data:testnet",
            "symbol": "BTC/USDT",
            "external_sequence": "abc",
        }
    )

    assert first.status == "ok"
    assert second.status == "ok"
    assert third.status == "ok"
    assert bad.status == "non_numeric"
    assert monitor.summary()["counts"]["non_numeric"] == 1
    assert monitor.summary()["counts"]["gap"] == 0


def test_soak_harness_restart_replay_preserves_long_run_boundary(tmp_path):
    recorder = EventRecorder(str(tmp_path / "events.jsonl"))
    monitor = EventSequenceMonitor()
    harness = SoakHarness(recorder=recorder, monitor=monitor)
    events = []
    for idx in range(1, 251):
        events.append(
            {
                "event_type": "mark_price_update",
                "timestamp": f"2026-01-01T00:00:{idx % 60:02d}+00:00",
                "payload": {"mark_price": str(45000 + idx)},
                "source": "binance_futures_user_data:testnet",
                "source_kind": "websocket",
                "symbol": "BTC/USDT",
                "external_sequence": str(idx),
            }
        )

    ingest = harness.ingest_events(events)
    replay = harness.restart_and_replay()

    assert ingest["processed"] == 250
    assert ingest["monitor"]["counts"]["gap"] == 0
    assert replay["replayed"] == 250
    assert replay["boundary"]["last_sequence"] == 250
    assert replay["boundary"]["last_external_sequence"] == "250"
