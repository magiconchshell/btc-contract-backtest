from btc_contract_backtest.live.binance_futures_stream import (
    BinanceFuturesEventNormalizer,
    BinanceFuturesStreamConfig,
    BinanceFuturesUserDataEventSource,
)
from btc_contract_backtest.live.event_stream import EventDrivenExecutionSource, EventRecorder
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter


class FakeListenKeyExchange:
    def __init__(self):
        self.options = {}
        self.sandbox = None
        self.calls = []

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


def test_event_stream_records_and_replays_sequence(tmp_path):
    recorder = EventRecorder(str(tmp_path / "events.jsonl"))
    source = EventDrivenExecutionSource(recorder)

    evt1 = source.emit("submit_intent_created", "2026-01-01T00:00:00+00:00", {"request_id": "r1"}, source="runtime")
    evt2 = source.emit("submit_intent_submitted", "2026-01-01T00:00:01+00:00", {"request_id": "r1"}, source="exchange")
    replay = source.replay()

    assert evt1["sequence"] == 1
    assert evt2["sequence"] == 2
    assert len(replay) == 2
    assert replay[1]["event_type"] == "submit_intent_submitted"


def test_event_stream_boundary_requires_polling_without_live_upstream(tmp_path):
    exchange = FakeListenKeyExchange()
    adapter = ExchangeExecutionAdapter(exchange, "BTC/USDT")
    upstream = BinanceFuturesUserDataEventSource(
        adapter,
        BinanceFuturesStreamConfig(symbol="BTC/USDT", use_testnet=True),
    )
    source = EventDrivenExecutionSource(EventRecorder(str(tmp_path / "events.jsonl")), upstream=upstream)

    boundary = source.boundary_state()

    assert boundary["poll_fallback_required"] is True
    assert boundary["upstream"]["testnet"] is True
    assert boundary["upstream"]["listen_key_present"] is False

    upstream.acquire_listen_key()
    upstream.attach_transport()

    boundary = source.boundary_state()
    assert boundary["poll_fallback_required"] is False
    assert boundary["upstream"]["listen_key_present"] is True
    assert exchange.sandbox is True


def test_binance_user_data_source_manages_listen_key_lifecycle():
    exchange = FakeListenKeyExchange()
    adapter = ExchangeExecutionAdapter(exchange, "BTC/USDT")
    source = BinanceFuturesUserDataEventSource(
        adapter,
        BinanceFuturesStreamConfig(symbol="BTC/USDT", use_testnet=True),
    )

    assert source.acquire_listen_key() == "lk-test"
    assert source.keepalive_listen_key() is True
    assert source.close_listen_key() is True
    assert [call[0] for call in exchange.calls] == ["post", "put", "delete"]


def test_binance_event_normalizer_maps_order_trade_update():
    normalizer = BinanceFuturesEventNormalizer("BTC/USDT")
    events = normalizer.normalize(
        {
            "e": "ORDER_TRADE_UPDATE",
            "E": 1735689600123,
            "T": 1735689600456,
            "o": {
                "i": 101,
                "c": "client-1",
                "S": "BUY",
                "o": "MARKET",
                "f": "GTC",
                "x": "TRADE",
                "X": "FILLED",
                "z": "0.010",
                "l": "0.010",
                "L": "45000.1",
                "ap": "45000.1",
                "R": False,
                "ps": "BOTH",
                "rp": "12.3",
                "t": 99,
            },
        },
        source="binance_futures_user_data:testnet",
        received_at="2026-01-01T00:00:05+00:00",
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "order_trade_update"
    assert event.payload["client_order_id"] == "client-1"
    assert event.payload["status"] == "filled"
    assert event.source_kind == "websocket"
    assert event.external_sequence == "99"


def test_binance_event_normalizer_maps_account_and_mark_price_updates():
    normalizer = BinanceFuturesEventNormalizer("BTC/USDT")

    account_events = normalizer.normalize(
        {
            "e": "ACCOUNT_UPDATE",
            "E": 1735689600123,
            "T": 1735689600456,
            "a": {"m": "ORDER", "B": [{"a": "USDT", "wb": "1000"}], "P": [{"s": "BTCUSDT", "pa": "0.001"}]},
        },
        source="binance_futures_user_data:testnet",
    )
    mark_events = normalizer.normalize(
        {
            "e": "markPriceUpdate",
            "E": 1735689600123,
            "p": "45123.4",
            "i": "45120.0",
            "P": "45130.0",
            "r": "0.0001",
            "T": 1735718400000,
        },
        source="binance_futures_user_data:testnet",
    )

    assert account_events[0].event_type == "account_update"
    assert account_events[0].payload["reason"] == "ORDER"
    assert mark_events[0].event_type == "mark_price_update"
    assert mark_events[0].payload["mark_price"] == "45123.4"
