from __future__ import annotations

from datetime import datetime, timedelta, timezone

from btc_contract_backtest.live.binance_futures_stream import (
    BinanceFuturesEventNormalizer,
    BinanceFuturesStreamConfig,
    BinanceFuturesUserDataEventSource,
    ReconnectPolicy,
)
from btc_contract_backtest.live.event_stream import (
    EventDrivenExecutionSource,
    EventRecorder,
)
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
    def __init__(self, start=None):
        self.now = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now = self.now + timedelta(seconds=seconds)

    def advance(self, seconds):
        self.now = self.now + timedelta(seconds=seconds)


def test_event_stream_records_and_replays_sequence(tmp_path):
    recorder = EventRecorder(str(tmp_path / "events.jsonl"))
    source = EventDrivenExecutionSource(recorder)

    evt1 = source.emit(
        "submit_intent_created",
        "2026-01-01T00:00:00+00:00",
        {"request_id": "r1"},
        source="runtime",
    )
    evt2 = source.emit(
        "submit_intent_submitted",
        "2026-01-01T00:00:01+00:00",
        {"request_id": "r1"},
        source="exchange",
    )
    replay = source.replay()

    assert evt1["sequence"] == 1
    assert evt2["sequence"] == 2
    assert len(replay) == 2
    assert replay[1]["event_type"] == "submit_intent_submitted"


def test_event_stream_replay_sorts_by_sequence_and_tracks_numeric_watermarks(tmp_path):
    recorder = EventRecorder(str(tmp_path / "events.jsonl"))
    recorder.append(
        {
            "event_type": "order_trade_update",
            "timestamp": "2026-01-01T00:00:03+00:00",
            "payload": {"client_order_id": "c1"},
            "sequence": 10,
            "external_sequence": "100",
            "received_at": "2026-01-01T00:00:03+00:00",
        }
    )
    recorder.append(
        {
            "event_type": "order_new",
            "timestamp": "2026-01-01T00:00:01+00:00",
            "payload": {"client_order_id": "c1"},
            "sequence": 2,
            "external_sequence": "9",
            "received_at": "2026-01-01T00:00:01+00:00",
        }
    )
    source = EventDrivenExecutionSource(recorder)

    replay = source.replay()

    assert [row["sequence"] for row in replay] == [2, 10]
    assert source.last_sequence == 10
    assert source.last_external_sequence == "100"


def test_event_stream_boundary_requires_polling_without_live_upstream(tmp_path):
    exchange = FakeListenKeyExchange()
    adapter = ExchangeExecutionAdapter(exchange, "BTC/USDT")
    upstream = BinanceFuturesUserDataEventSource(
        adapter,
        BinanceFuturesStreamConfig(symbol="BTC/USDT", use_testnet=True),
    )
    source = EventDrivenExecutionSource(
        EventRecorder(str(tmp_path / "events.jsonl")), upstream=upstream
    )

    boundary = source.boundary_state()

    assert boundary["poll_fallback_required"] is True
    assert boundary["upstream"]["testnet"] is True
    assert boundary["upstream"]["listen_key_present"] is False

    upstream.acquire_listen_key()
    upstream.attach_transport(FakeTransport([]))

    boundary = source.boundary_state()
    assert boundary["poll_fallback_required"] is False
    assert boundary["upstream"]["listen_key_present"] is True
    assert boundary["upstream"]["transport"]["connected"] is True
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
            "a": {
                "m": "ORDER",
                "B": [{"a": "USDT", "wb": "1000"}],
                "P": [{"s": "BTCUSDT", "pa": "0.001"}],
            },
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


def test_user_data_run_loop_ingests_normalized_events_and_keeps_listen_key_alive(
    tmp_path,
):
    exchange = FakeListenKeyExchange()
    adapter = ExchangeExecutionAdapter(exchange, "BTC/USDT")
    clock = ClockHarness()
    scripts = [
        [
            {
                "e": "ORDER_TRADE_UPDATE",
                "E": 1735689600123,
                "T": 1735689600456,
                "o": {"i": 101, "c": "client-1", "x": "TRADE", "X": "FILLED", "t": 99},
            },
            {
                "e": "ACCOUNT_UPDATE",
                "E": 1735689601123,
                "T": 1735689601456,
                "a": {
                    "m": "ORDER",
                    "B": [{"a": "USDT", "wb": "1000"}],
                    "P": [{"s": "BTCUSDT", "pa": "0.001"}],
                },
            },
        ]
    ]

    def transport_factory(_url):
        return FakeTransport(scripts.pop(0))

    source = BinanceFuturesUserDataEventSource(
        adapter,
        BinanceFuturesStreamConfig(
            symbol="BTC/USDT", use_testnet=True, listen_key_keepalive_seconds=1
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
    result = source.run_loop(sink, max_messages=2)
    rows = sink.replay()

    assert result.ok is True
    assert [row["event_type"] for row in rows] == [
        "order_trade_update",
        "account_update",
    ]
    assert source.listen_key_state.last_keepalive_ok is True
    assert source.transport_state.connected is True
    assert source.transport_state.last_message_at is not None
    assert [call[0] for call in exchange.calls][:2] == ["post", "put"]


def test_user_data_run_loop_reconnects_with_backoff_and_continues_ingest(tmp_path):
    exchange = FakeListenKeyExchange()
    adapter = ExchangeExecutionAdapter(exchange, "BTC/USDT")
    clock = ClockHarness()
    scripts = [
        [RuntimeError("socket dropped")],
        [{"e": "listenKeyExpired", "E": 1735689602000}],
        [
            {
                "e": "markPriceUpdate",
                "E": 1735689603000,
                "p": "45000",
                "i": "44990",
                "P": "45010",
                "r": "0.0001",
                "T": 1735718400000,
            }
        ],
    ]

    def transport_factory(_url):
        return FakeTransport(scripts.pop(0))

    source = BinanceFuturesUserDataEventSource(
        adapter,
        BinanceFuturesStreamConfig(symbol="BTC/USDT", use_testnet=True),
        reconnect_policy=ReconnectPolicy(
            initial_delay_seconds=2, max_delay_seconds=10, multiplier=2.0
        ),
        transport_factory=transport_factory,
        clock=clock,
        sleep_fn=clock.sleep,
    )
    sink = EventDrivenExecutionSource(
        EventRecorder(str(tmp_path / "events.jsonl")), upstream=source
    )

    result = source.run_loop(sink, max_messages=3)
    rows = sink.replay()

    assert result.ok is True
    assert any(row["event_type"] == "user_data_stream_expired" for row in rows)
    assert any(row["event_type"] == "mark_price_update" for row in rows)
    assert source.transport_state.connection_count == 3
    assert source.transport_state.disconnect_count >= 2
    assert clock.sleeps == []


def test_mainnet_requires_explicit_opt_in():
    exchange = FakeListenKeyExchange()
    adapter = ExchangeExecutionAdapter(exchange, "BTC/USDT")
    source = BinanceFuturesUserDataEventSource(
        adapter,
        BinanceFuturesStreamConfig(
            symbol="BTC/USDT", use_testnet=False, allow_mainnet=False
        ),
    )

    try:
        source.acquire_listen_key()
    except ValueError as exc:
        assert "explicit opt-in" in str(exc)
    else:
        raise AssertionError(
            "expected mainnet opt-in guard to reject unapproved websocket mode"
        )
