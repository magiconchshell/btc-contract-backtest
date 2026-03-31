from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, Protocol

from btc_contract_backtest.live.binance_futures import is_binance_mainnet_enabled
from btc_contract_backtest.live.event_stream import EventDrivenExecutionSource, ExecutionEvent
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter


class WebsocketTransport(Protocol):
    def recv(self) -> str | bytes | dict[str, Any] | None:
        ...

    def close(self) -> None:
        ...


TransportFactory = Callable[[str], WebsocketTransport]
Clock = Callable[[], datetime]
SleepFn = Callable[[float], None]


DEFAULT_LISTEN_KEY_KEEPALIVE_SECONDS = 30 * 60


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _iso_from_millis(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc).isoformat()
    except Exception:  # noqa: BLE001
        return None


@dataclass
class BinanceFuturesStreamConfig:
    symbol: str
    use_testnet: bool = True
    market: str = "usdm"
    stream_base_testnet: str = "wss://stream.binancefuture.com/ws"
    stream_base_mainnet: str = "wss://fstream.binance.com/ws"
    user_stream_path_template: str = "{listen_key}"
    mark_price_path_template: str = "{symbol_lower}@markPrice@1s"
    allow_mainnet: bool = False
    listen_key_keepalive_seconds: int = DEFAULT_LISTEN_KEY_KEEPALIVE_SECONDS

    def base_url(self) -> str:
        return self.stream_base_testnet if self.use_testnet else self.stream_base_mainnet

    def normalized_symbol(self) -> str:
        return self.symbol.replace("/", "").replace(":", "").lower()

    def mark_price_stream_url(self) -> str:
        return f"{self.base_url()}/{self.mark_price_path_template.format(symbol_lower=self.normalized_symbol())}"

    def user_data_stream_url(self, listen_key: str) -> str:
        return f"{self.base_url()}/{self.user_stream_path_template.format(listen_key=listen_key)}"


@dataclass
class ReconnectPolicy:
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    multiplier: float = 2.0
    max_attempts: Optional[int] = None

    def delay_for_attempt(self, attempt: int) -> float:
        if attempt <= 1:
            return self.initial_delay_seconds
        delay = self.initial_delay_seconds * (self.multiplier ** (attempt - 1))
        return min(delay, self.max_delay_seconds)


@dataclass
class ListenKeyState:
    current: Optional[str] = None
    acquired_at: Optional[str] = None
    keepalive_due_at: Optional[str] = None
    last_keepalive_at: Optional[str] = None
    last_keepalive_ok: Optional[bool] = None
    rotations: int = 0
    last_error: Optional[str] = None


@dataclass
class TransportState:
    connected: bool = False
    connection_count: int = 0
    disconnect_count: int = 0
    reconnect_attempts: int = 0
    last_connect_at: Optional[str] = None
    last_disconnect_at: Optional[str] = None
    last_message_at: Optional[str] = None
    last_error: Optional[str] = None
    last_backoff_seconds: Optional[float] = None
    last_url: Optional[str] = None


@dataclass
class RunLoopResult:
    ok: bool
    events: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BinanceFuturesEventNormalizer:
    def __init__(self, symbol: str):
        self.symbol = symbol

    def normalize(
        self,
        message: dict[str, Any],
        *,
        source: str,
        received_at: Optional[str] = None,
    ) -> list[ExecutionEvent]:
        received_at = received_at or datetime.now(timezone.utc).isoformat()
        event_type = message.get("e")
        if event_type == "ORDER_TRADE_UPDATE":
            order = message.get("o") or {}
            timestamp = _iso_from_millis(message.get("T") or order.get("T") or message.get("E")) or received_at
            status = str(order.get("X") or "").lower()
            execution_type = str(order.get("x") or "").lower()
            payload = {
                "raw": message,
                "order_id": order.get("i"),
                "client_order_id": order.get("c"),
                "side": str(order.get("S") or "").lower() or None,
                "order_type": str(order.get("o") or "").lower() or None,
                "time_in_force": order.get("f"),
                "execution_type": execution_type or None,
                "status": status or None,
                "filled_quantity": order.get("z"),
                "last_fill_quantity": order.get("l"),
                "last_fill_price": order.get("L"),
                "average_price": order.get("ap"),
                "reduce_only": order.get("R"),
                "position_side": order.get("ps"),
                "realized_pnl": order.get("rp"),
            }
            normalized_type = {
                "trade": "order_trade_update",
                "new": "order_new",
                "canceled": "order_canceled",
                "expired": "order_expired",
                "calculated": "order_calculated",
            }.get(execution_type, f"order_status_{status or 'unknown'}")
            return [
                ExecutionEvent(
                    event_type=normalized_type,
                    timestamp=timestamp,
                    payload=payload,
                    source=source,
                    source_kind="websocket",
                    event_id=f"order:{order.get('i')}:{message.get('T') or message.get('E')}",
                    exchange_timestamp=_iso_from_millis(message.get("E")),
                    received_at=received_at,
                    symbol=self.symbol,
                    external_sequence=str(order.get("t") or message.get("T") or message.get("E") or ""),
                )
            ]
        if event_type == "ACCOUNT_UPDATE":
            account = message.get("a") or {}
            timestamp = _iso_from_millis(message.get("T") or message.get("E")) or received_at
            payload = {
                "raw": message,
                "reason": account.get("m"),
                "balances": account.get("B") or [],
                "positions": account.get("P") or [],
            }
            return [
                ExecutionEvent(
                    event_type="account_update",
                    timestamp=timestamp,
                    payload=payload,
                    source=source,
                    source_kind="websocket",
                    event_id=f"account:{message.get('T') or message.get('E')}",
                    exchange_timestamp=_iso_from_millis(message.get("E")),
                    received_at=received_at,
                    symbol=self.symbol,
                    external_sequence=str(message.get("T") or message.get("E") or ""),
                )
            ]
        if event_type == "listenKeyExpired":
            timestamp = _iso_from_millis(message.get("E")) or received_at
            return [
                ExecutionEvent(
                    event_type="user_data_stream_expired",
                    timestamp=timestamp,
                    payload={"raw": message},
                    source=source,
                    source_kind="websocket",
                    event_id=f"listenKeyExpired:{message.get('E')}",
                    exchange_timestamp=_iso_from_millis(message.get("E")),
                    received_at=received_at,
                    symbol=self.symbol,
                    external_sequence=str(message.get("E") or ""),
                )
            ]
        if event_type == "markPriceUpdate":
            timestamp = _iso_from_millis(message.get("E") or message.get("T")) or received_at
            payload = {
                "raw": message,
                "mark_price": message.get("p"),
                "index_price": message.get("i"),
                "estimated_settle_price": message.get("P"),
                "funding_rate": message.get("r"),
                "next_funding_time": _iso_from_millis(message.get("T")),
            }
            return [
                ExecutionEvent(
                    event_type="mark_price_update",
                    timestamp=timestamp,
                    payload=payload,
                    source=source,
                    source_kind="websocket",
                    event_id=f"mark:{message.get('E') or message.get('T')}",
                    exchange_timestamp=_iso_from_millis(message.get("E")),
                    received_at=received_at,
                    symbol=self.symbol,
                    external_sequence=str(message.get("E") or message.get("T") or ""),
                )
            ]
        timestamp = _iso_from_millis(message.get("E") or message.get("T")) or received_at
        return [
            ExecutionEvent(
                event_type="exchange_message",
                timestamp=timestamp,
                payload={"raw": message},
                source=source,
                source_kind="websocket",
                event_id=f"raw:{message.get('e') or 'unknown'}:{message.get('E') or message.get('T') or received_at}",
                exchange_timestamp=_iso_from_millis(message.get("E")),
                received_at=received_at,
                symbol=self.symbol,
                external_sequence=str(message.get("E") or message.get("T") or ""),
            )
        ]


class BinanceFuturesUserDataEventSource:
    """Testnet-first websocket/user-data stream foundation.

    The focus here is transport lifecycle, listen-key keepalive rotation, bounded
    reconnect policy, and normalized ingest into the existing execution-event
    substrate. It intentionally avoids full restart convergence v2 and race-
    hardening beyond the transport/event-plane boundary.
    """

    def __init__(
        self,
        adapter: ExchangeExecutionAdapter,
        config: BinanceFuturesStreamConfig,
        *,
        reconnect_policy: Optional[ReconnectPolicy] = None,
        transport_factory: Optional[TransportFactory] = None,
        clock: Clock = _utcnow,
        sleep_fn: SleepFn = time.sleep,
    ):
        self.adapter = adapter
        self.config = config
        self.normalizer = BinanceFuturesEventNormalizer(config.symbol)
        self.reconnect_policy = reconnect_policy or ReconnectPolicy()
        self.transport_factory = transport_factory
        self.clock = clock
        self.sleep_fn = sleep_fn
        self.listen_key_state = ListenKeyState()
        self.transport_state = TransportState()
        self.transport: Optional[WebsocketTransport] = None

    def source_name(self) -> str:
        mode = "testnet" if self.config.use_testnet else "mainnet"
        return f"binance_futures_user_data:{mode}"

    def source_kind(self) -> str:
        return "websocket"

    def is_live(self) -> bool:
        return self.transport_state.connected and bool(self.listen_key_state.current)

    def _assert_mode_allowed(self) -> None:
        if self.config.use_testnet:
            return
        if not is_binance_mainnet_enabled(
            "binance_futures_mainnet",
            allow_mainnet=self.config.allow_mainnet,
        ):
            raise ValueError("Binance Futures mainnet websocket requires explicit opt-in")

    def describe(self) -> dict[str, Any]:
        return {
            "source": self.source_name(),
            "kind": self.source_kind(),
            "symbol": self.config.symbol,
            "testnet": self.config.use_testnet,
            "connected": self.transport_state.connected,
            "listen_key_present": bool(self.listen_key_state.current),
            "listen_key": asdict(self.listen_key_state),
            "transport": asdict(self.transport_state),
            "mark_price_stream_url": self.config.mark_price_stream_url(),
            "user_data_stream_url": self.config.user_data_stream_url(self.listen_key_state.current or "<listenKey>"),
        }

    def acquire_listen_key(self) -> Optional[str]:
        self._assert_mode_allowed()
        listen_key = self.adapter.create_user_data_stream_listen_key(use_testnet=self.config.use_testnet)
        now = self.clock()
        if listen_key:
            if self.listen_key_state.current and self.listen_key_state.current != listen_key:
                self.listen_key_state.rotations += 1
            self.listen_key_state.current = listen_key
            self.listen_key_state.acquired_at = _iso(now)
            self.listen_key_state.keepalive_due_at = _iso(now + timedelta(seconds=self.config.listen_key_keepalive_seconds))
            self.listen_key_state.last_error = None
        else:
            self.listen_key_state.last_error = "listen_key_acquire_failed"
        return listen_key

    def keepalive_listen_key(self) -> bool:
        listen_key = self.listen_key_state.current
        if not listen_key:
            self.listen_key_state.last_error = "listen_key_missing"
            return False
        ok = self.adapter.keepalive_user_data_stream_listen_key(listen_key, use_testnet=self.config.use_testnet)
        now = self.clock()
        self.listen_key_state.last_keepalive_at = _iso(now)
        self.listen_key_state.last_keepalive_ok = ok
        if ok:
            self.listen_key_state.keepalive_due_at = _iso(now + timedelta(seconds=self.config.listen_key_keepalive_seconds))
            self.listen_key_state.last_error = None
        else:
            self.listen_key_state.last_error = "listen_key_keepalive_failed"
        return ok

    def close_listen_key(self) -> bool:
        listen_key = self.listen_key_state.current
        if not listen_key:
            return False
        ok = self.adapter.close_user_data_stream_listen_key(listen_key, use_testnet=self.config.use_testnet)
        if ok:
            self.listen_key_state.current = None
            self.transport_state.connected = False
        else:
            self.listen_key_state.last_error = "listen_key_close_failed"
        return ok

    def attach_transport(self, transport: Optional[WebsocketTransport] = None) -> None:
        if transport is not None:
            self.transport = transport
        self.transport_state.connected = self.transport is not None
        self.transport_state.connection_count += 1 if self.transport is not None else 0
        self.transport_state.last_connect_at = _iso(self.clock()) if self.transport is not None else None
        if self.transport is not None:
            self.transport_state.last_error = None
            self.transport_state.last_url = self.config.user_data_stream_url(self.listen_key_state.current or "<listenKey>")

    def detach_transport(self, *, error: Optional[str] = None) -> None:
        if self.transport is not None:
            try:
                self.transport.close()
            except Exception:  # noqa: BLE001
                pass
        self.transport = None
        if self.transport_state.connected:
            self.transport_state.disconnect_count += 1
        self.transport_state.connected = False
        self.transport_state.last_disconnect_at = _iso(self.clock())
        if error:
            self.transport_state.last_error = error

    def _connect_transport(self) -> None:
        if self.transport_factory is None:
            raise RuntimeError("websocket transport factory is not configured")
        if not self.listen_key_state.current and not self.acquire_listen_key():
            raise RuntimeError("failed to acquire listen key")
        url = self.config.user_data_stream_url(self.listen_key_state.current or "")
        transport = self.transport_factory(url)
        self.attach_transport(transport)

    def maybe_keepalive(self) -> bool:
        due = self.listen_key_state.keepalive_due_at
        if due is None:
            return False
        try:
            due_at = datetime.fromisoformat(due)
        except ValueError:
            return False
        if self.clock() < due_at:
            return False
        return self.keepalive_listen_key()

    def _decode_message(self, raw_message: str | bytes | dict[str, Any] | None) -> Optional[dict[str, Any]]:
        if raw_message is None:
            return None
        if isinstance(raw_message, dict):
            return raw_message
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode("utf-8")
        payload = str(raw_message).strip()
        if not payload:
            return None
        return json.loads(payload)

    def normalize_message(self, message: dict[str, Any], *, received_at: Optional[str] = None) -> list[ExecutionEvent]:
        return self.normalizer.normalize(message, source=self.source_name(), received_at=received_at)

    def read_once(self) -> list[ExecutionEvent]:
        if self.transport is None:
            self._connect_transport()
        self.maybe_keepalive()
        raw = self.transport.recv() if self.transport is not None else None
        message = self._decode_message(raw)
        if message is None:
            return []
        received_at = _iso(self.clock())
        self.transport_state.last_message_at = received_at
        events = self.normalize_message(message, received_at=received_at)
        for event in events:
            if event.event_type == "user_data_stream_expired":
                self.listen_key_state.current = None
                self.listen_key_state.keepalive_due_at = None
                self.detach_transport(error="listen_key_expired")
                break
        return events

    def ingest_once(self, sink: EventDrivenExecutionSource) -> list[dict[str, Any]]:
        emitted = []
        for event in self.read_once():
            emitted.append(sink.ingest(event))
        return emitted

    def _backoff_then_reconnect(self) -> bool:
        self.transport_state.reconnect_attempts += 1
        attempt = self.transport_state.reconnect_attempts
        if self.reconnect_policy.max_attempts is not None and attempt > self.reconnect_policy.max_attempts:
            self.transport_state.last_error = "reconnect_attempts_exhausted"
            return False
        delay = self.reconnect_policy.delay_for_attempt(attempt)
        self.transport_state.last_backoff_seconds = delay
        self.sleep_fn(delay)
        self._connect_transport()
        return True

    def run_loop(
        self,
        sink: EventDrivenExecutionSource,
        *,
        max_messages: Optional[int] = None,
        stop_on_error: bool = False,
    ) -> RunLoopResult:
        emitted: list[dict[str, Any]] = []
        notes: list[str] = []
        processed = 0
        while True:
            if max_messages is not None and processed >= max_messages:
                break
            try:
                rows = self.ingest_once(sink)
                if rows:
                    emitted.extend(rows)
                    processed += len(rows)
                    self.transport_state.reconnect_attempts = 0
                else:
                    processed += 1
            except Exception as exc:  # noqa: BLE001
                self.detach_transport(error=str(exc))
                notes.append(f"transport_error:{exc}")
                if stop_on_error:
                    return RunLoopResult(ok=False, events=emitted, notes=notes, state=self.describe())
                if not self._backoff_then_reconnect():
                    notes.append("reconnect_exhausted")
                    return RunLoopResult(ok=False, events=emitted, notes=notes, state=self.describe())
                notes.append("reconnected")
                continue
        return RunLoopResult(ok=True, events=emitted, notes=notes, state=self.describe())
