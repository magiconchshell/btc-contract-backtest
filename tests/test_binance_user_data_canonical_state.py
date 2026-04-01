from __future__ import annotations

from datetime import datetime, timedelta, timezone

from btc_contract_backtest.live.binance_futures_stream import (
    BinanceFuturesStreamConfig,
    BinanceFuturesUserDataEventSource,
    ReconnectPolicy,
)
from btc_contract_backtest.live.event_stream import (
    EventDrivenExecutionSource,
    EventRecorder,
)
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter


class FakeExchangeStateful:
    def __init__(self):
        self.options = {}
        self.sandbox = None
        self.calls = []
        self.positions = [
            {"symbol": "BTCUSDT", "contracts": 0.001, "entryPrice": 45000.0}
        ]
        self.open_orders = [
            {
                "id": "ex-1",
                "clientOrderId": "c-1",
                "status": "open",
                "side": "buy",
                "type": "market",
                "amount": 0.001,
                "filled": 0.0,
            },
        ]

    def set_sandbox_mode(self, enabled):
        self.sandbox = enabled

    def fapiPrivatePostListenKey(self, params):
        self.calls.append(("post", params))
        return {"listenKey": "lk-test"}

    def fapiPrivatePutListenKey(self, params):
        self.calls.append(("put", params))
        return {"result": "ok"}

    def fapiPrivateDeleteListenKey(self, params):
        self.calls.append(("delete", params))
        return {"result": "ok"}

    def fetch_positions(self, symbols):
        self.calls.append(("fetch_positions", symbols))
        return list(self.positions)

    def fetch_open_orders(self, symbol):
        self.calls.append(("fetch_open_orders", symbol))
        return list(self.open_orders)


class FakeTransport:
    def __init__(self, script):
        self.script = list(script)
        self.closed = False

    def recv(self):
        if not self.script:
            return None
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        self.closed = True


class ClockHarness:
    def __init__(self):
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


def test_execution_state_dedupes_replayed_events_and_tracks_gap(tmp_path):
    exchange = FakeExchangeStateful()
    adapter = ExchangeExecutionAdapter(exchange, "BTC/USDT")
    clock = ClockHarness()
    script = [
        [
            {
                "e": "ORDER_TRADE_UPDATE",
                "E": 1735689600123,
                "T": 1735689600456,
                "o": {
                    "i": 101,
                    "c": "c-1",
                    "x": "TRADE",
                    "X": "FILLED",
                    "z": "0.001",
                    "t": 1,
                },
            },
            {
                "e": "ORDER_TRADE_UPDATE",
                "E": 1735689600123,
                "T": 1735689600456,
                "o": {
                    "i": 101,
                    "c": "c-1",
                    "x": "TRADE",
                    "X": "FILLED",
                    "z": "0.001",
                    "t": 1,
                },
            },
            {
                "e": "ACCOUNT_UPDATE",
                "E": 1735689601123,
                "T": 1735689601456,
                "a": {"m": "ORDER", "B": [], "P": [{"s": "BTCUSDT", "pa": "0.001"}]},
            },
            {
                "e": "ORDER_TRADE_UPDATE",
                "E": 1735689602123,
                "T": 1735689602456,
                "o": {
                    "i": 102,
                    "c": "c-1",
                    "x": "TRADE",
                    "X": "FILLED",
                    "z": "0.001",
                    "t": 4,
                },
            },
        ]
    ]

    def transport_factory(_url):
        return FakeTransport(script.pop(0))

    source = BinanceFuturesUserDataEventSource(
        adapter,
        BinanceFuturesStreamConfig(
            symbol="BTC/USDT", listen_key_keepalive_seconds=1
        ),
        transport_factory=transport_factory,
        clock=clock,
        sleep_fn=clock.sleep,
    )
    sink = EventDrivenExecutionSource(
        EventRecorder(str(tmp_path / "events.jsonl")), upstream=source
    )

    source.acquire_listen_key()
    clock.advance(2)
    result = source.run_loop(sink, max_messages=4)

    assert result.ok is False
    assert result.notes[-1] == "rest_reconciliation_required"
    assert len(sink.replay()) == 4
    assert source.execution_state.needs_rest_reconciliation is True
    assert any(obs["status"] == "gap" for obs in source.execution_state.observations)
    assert len(source.execution_state.orders) == 1


def test_execution_state_rest_sync_reconciles_snapshot(tmp_path):
    exchange = FakeExchangeStateful()
    adapter = ExchangeExecutionAdapter(exchange, "BTC/USDT")
    source = BinanceFuturesUserDataEventSource(
        adapter,
        BinanceFuturesStreamConfig(symbol="BTC/USDT"),
    )

    source.execution_state.needs_rest_reconciliation = True
    snapshot = source.sync_from_rest()

    assert snapshot["ok"] is True
    assert source.execution_state.needs_rest_reconciliation is False
    assert source.execution_state.positions["BTCUSDT"]["contracts"] == 0.001
    assert source.execution_state.orders["c-1"]["id"] == "ex-1"


def test_keepalive_and_reconnect_policy_are_exposed_in_state(tmp_path):
    exchange = FakeExchangeStateful()
    adapter = ExchangeExecutionAdapter(exchange, "BTC/USDT")
    clock = ClockHarness()
    source = BinanceFuturesUserDataEventSource(
        adapter,
        BinanceFuturesStreamConfig(
            symbol="BTC/USDT", listen_key_keepalive_seconds=1
        ),
        reconnect_policy=ReconnectPolicy(initial_delay_seconds=2, max_delay_seconds=5),
        transport_factory=lambda _url: FakeTransport([]),
        clock=clock,
        sleep_fn=clock.sleep,
    )

    source.acquire_listen_key()
    clock.advance(2)
    source.attach_transport(FakeTransport([]))
    source.maybe_keepalive()
    state = source.describe()

    assert state["execution_state"]["needs_rest_reconciliation"] is False
    assert state["transport"]["connected"] is True
    assert source.listen_key_state.last_keepalive_ok is True


def test_execution_state_derives_authoritative_position_and_open_orders():
    exchange = FakeExchangeStateful()
    adapter = ExchangeExecutionAdapter(exchange, "BTC/USDT")
    source = BinanceFuturesUserDataEventSource(
        adapter,
        BinanceFuturesStreamConfig(symbol="BTC/USDT"),
    )

    source.execution_state.orders = {
        "open-1": {"clientOrderId": "open-1", "status": "open"},
        "filled-1": {"clientOrderId": "filled-1", "status": "filled"},
    }
    source.execution_state.positions = {
        "BTCUSDT": {"symbol": "BTCUSDT", "pa": "-0.25", "ep": "45100.0"}
    }

    assert len(source.execution_state.active_orders()) == 1
    position = source.execution_state.derived_position()
    assert position["side"] == -1
    assert position["quantity"] == 0.25
    assert position["entry_price"] == 45100.0
