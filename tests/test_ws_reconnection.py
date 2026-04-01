import pytest
from typing import Optional
from btc_contract_backtest.live.binance_futures_stream import (
    BinanceFuturesUserDataEventSource,
    BinanceFuturesStreamConfig,
    ReconnectPolicy,
    WebsocketTransport,
)


class MockTransport:
    def __init__(self, url: str):
        self.url = url
        self.closed = False
        self.messages = []
        self.throws_on_recv = False

    def recv(self):
        if self.closed:
            raise ConnectionError("Transport closed")
        if self.throws_on_recv:
            raise ConnectionError("Simulated network drop")
        if self.messages:
            return self.messages.pop(0)
        return None

    def close(self):
        self.closed = True


class MockAdapter:
    def __init__(self):
        self.listen_key_count = 0
        self.keepalive_count = 0
        self.fail_lk = False

    def create_user_data_stream_listen_key(self) -> Optional[str]:
        if self.fail_lk:
            return None
        self.listen_key_count += 1
        return f"mock_lk_{self.listen_key_count}"

    def keepalive_user_data_stream_listen_key(self, listen_key: str) -> bool:
        self.keepalive_count += 1
        return True

    def close_user_data_stream_listen_key(self, listen_key: str) -> bool:
        return True


def mock_transport_factory(url: str) -> WebsocketTransport:
    if getattr(mock_transport_factory, "fail", False):
        raise ConnectionError("Mock factory failure")
    return MockTransport(url)


class EventSink:
    def __init__(self):
        self.events = []

    def ingest(self, event):
        self.events.append(event)
        return event.to_dict()


def test_websocket_reconnection_policy():
    """Verify that read_once catches Exception from recv and enforces ReconnectPolicy."""
    adapter = MockAdapter()
    config = BinanceFuturesStreamConfig(symbol="BTC/USDT")
    policy = ReconnectPolicy(
        initial_delay_seconds=0.1, max_delay_seconds=1.0, max_attempts=3
    )

    delays = []

    def mock_sleep(sec: float):
        delays.append(sec)

    stream = BinanceFuturesUserDataEventSource(
        adapter,
        config,
        reconnect_policy=policy,
        transport_factory=mock_transport_factory,
        sleep_fn=mock_sleep,
    )

    # First read initializes it
    stream.read_once()
    assert stream.transport is not None
    assert stream.listen_key_state.current == "mock_lk_1"

    # Simulate network drop
    stream.transport.throws_on_recv = True

    # First drop -> returns empty list, detaches transport
    events = stream.read_once()
    assert len(events) == 0
    assert stream.transport is None

    # Next read_once tries to reconnect but the transport factory passes?
    # To test reconnect failure, we make the factory fail.
    mock_transport_factory.fail = True
    events = stream.read_once()
    assert len(events) == 0
    assert stream.transport_state.reconnect_attempts == 1
    assert delays == [0.1]

    events = stream.read_once()
    assert len(events) == 0
    assert stream.transport_state.reconnect_attempts == 2
    assert delays == [0.1, 0.2]

    # Attempt 3 fails too
    events = stream.read_once()
    assert len(events) == 0
    assert stream.transport_state.reconnect_attempts == 3
    assert delays == [0.1, 0.2, 0.4]

    # Attempt 4 should raise RuntimeError
    with pytest.raises(RuntimeError, match="Reconnect failed after 3 attempts"):
        stream.read_once()


def test_websocket_reconnection_flags_reconciliation():
    """Verify that a successful reconnect flips needs_rest_reconciliation = True."""
    mock_transport_factory.fail = False
    adapter = MockAdapter()
    config = BinanceFuturesStreamConfig(symbol="BTC/USDT")
    policy = ReconnectPolicy(
        initial_delay_seconds=0.1, max_delay_seconds=1.0, max_attempts=3
    )

    stream = BinanceFuturesUserDataEventSource(
        adapter,
        config,
        reconnect_policy=policy,
        transport_factory=mock_transport_factory,
        sleep_fn=lambda x: None,
    )

    # First connect
    stream.read_once()
    assert stream.execution_state.needs_rest_reconciliation is False

    # Simulate disconnect
    stream.transport.throws_on_recv = True
    stream.read_once()  # catches error
    assert stream.transport is None

    # Try connect but fail once
    mock_transport_factory.fail = True
    stream.read_once()
    assert stream.transport_state.reconnect_attempts == 1

    # Now succeed
    mock_transport_factory.fail = False

    # Ingest once connects!
    sink = EventSink()

    # Provide a message on the newly created transport so it doesn't block
    def passing_factory(url):
        t = MockTransport(url)
        t.messages = ['{"e":"markPriceUpdate","p":"50000"}']
        return t

    stream.transport_factory = passing_factory
    stream.ingest_once(sink)

    # The reconnect attempt was > 0, so it should flag as needs reconciliation
    assert stream.execution_state.needs_rest_reconciliation is True
    assert stream.transport_state.reconnect_attempts == 0
