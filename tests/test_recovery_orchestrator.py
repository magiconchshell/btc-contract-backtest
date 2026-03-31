from pathlib import Path

from btc_contract_backtest.live.exchange_adapter import AdapterResult
from btc_contract_backtest.live.recovery_orchestrator import RecoveryOrchestrator
from btc_contract_backtest.live.submit_ledger import SubmitIntent, SubmitLedger


class RecoveryAdapter:
    def fetch_open_orders(self):
        return AdapterResult(ok=True, payload=[
            {"id": "ex-1", "clientOrderId": "c1", "status": "open"},
            {"id": "ex-2", "clientOrderId": "c-remote-only", "status": "open"},
        ])

    def fetch_open_orders_by_client_order_id(self, client_order_id):
        if client_order_id == "c1":
            return AdapterResult(ok=True, payload=[{"id": "ex-1", "clientOrderId": "c1", "status": "open"}])
        return AdapterResult(ok=True, payload=[])


def test_recovery_orchestrator_recovers_pending_intent_and_flags_orphans(tmp_path):
    ledger = SubmitLedger(str(Path(tmp_path) / "submit_ledger.json"))
    ledger.upsert(SubmitIntent(request_id="r1", client_order_id="c1", symbol="BTC/USDT", signal=1, quantity=1.0, notional=100.0, state="unknown"))
    orchestrator = RecoveryOrchestrator(RecoveryAdapter(), ledger)

    report = orchestrator.recover(local_orders=[{"order_id": "o-local", "client_order_id": "c-local-only", "state": "new"}]).to_dict()
    assert report["ok"] is True
    assert len(report["recovered_intents"]) == 1
    assert len(report["remote_only_orders"]) == 2
    assert len(report["local_only_orders"]) == 1
