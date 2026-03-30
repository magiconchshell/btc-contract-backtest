import json
from pathlib import Path

from btc_contract_backtest.engine.execution_models import Order, OrderSide, OrderStatus, OrderType
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.session_recovery import SessionRecovery
from btc_contract_backtest.live.watchdog import HeartbeatWatchdog


class FakeExchange:
    def __init__(self):
        self.created = []
        self.canceled = []

    def create_order(self, symbol, type, side, amount, price=None, params=None):
        payload = {"id": "ex-1", "symbol": symbol, "type": type, "side": side, "amount": amount, "price": price, "params": params or {}, "status": "open"}
        self.created.append(payload)
        return payload

    def cancel_order(self, order_id, symbol):
        self.canceled.append((order_id, symbol))
        return {"id": order_id, "status": "canceled"}

    def fetch_open_orders(self, symbol):
        return [{"id": "ex-1", "symbol": symbol, "status": "open"}]

    def fetch_positions(self, symbols):
        return [{"symbol": symbols[0], "contracts": 1}]

    def fetch_order(self, order_id, symbol):
        return {"id": order_id, "symbol": symbol, "status": "closed", "filled": 1}


def test_session_recovery_dedupes_client_ids(tmp_path):
    path = Path(tmp_path) / "state.json"
    path.write_text(json.dumps({
        "orders": [
            {
                "order_id": "1", "symbol": "BTC/USDT", "side": "buy", "order_type": "market", "quantity": 1,
                "client_order_id": "dup", "status": "new"
            },
            {
                "order_id": "2", "symbol": "BTC/USDT", "side": "sell", "order_type": "limit", "quantity": 1,
                "client_order_id": "dup", "status": "new"
            },
        ]
    }))
    recovery = SessionRecovery(str(path))
    state = recovery.load_state()
    orders = recovery.restore_orders(state)
    duplicates = recovery.dedupe_client_order_ids(orders)
    assert duplicates == ["dup"]


def test_adapter_submit_and_reconcile():
    adapter = ExchangeExecutionAdapter(FakeExchange(), "BTC/USDT")
    order = Order(order_id="1", symbol="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1.0, client_order_id="abc")
    submit = adapter.submit_order(order)
    assert submit.ok is True
    reconcile = adapter.reconcile_state(local_position_side=1, local_open_orders=1)
    assert reconcile.ok is True
    assert reconcile.payload["remote_position_side"] == 1


def test_watchdog_halts_after_failures():
    watchdog = HeartbeatWatchdog(heartbeat_timeout_seconds=10, max_consecutive_failures=2)
    watchdog.record_failure("x")
    assert watchdog.state.halted is False
    watchdog.record_failure("y")
    assert watchdog.state.halted is True
    assert watchdog.state.halt_reason == "y"


def test_watchdog_timeout_sets_halt():
    from datetime import datetime, timedelta, timezone

    watchdog = HeartbeatWatchdog(heartbeat_timeout_seconds=1, max_consecutive_failures=2)
    watchdog.beat()
    future = datetime.now(timezone.utc) + timedelta(seconds=5)
    assert watchdog.check_timeout(future) is True
