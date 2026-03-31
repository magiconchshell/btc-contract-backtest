from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from btc_contract_backtest.live.event_stream import ExecutionEvent
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter


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

    def base_url(self) -> str:
        return self.stream_base_testnet if self.use_testnet else self.stream_base_mainnet

    def normalized_symbol(self) -> str:
        return self.symbol.replace("/", "").replace(":", "").lower()

    def mark_price_stream_url(self) -> str:
        return f"{self.base_url()}/{self.mark_price_path_template.format(symbol_lower=self.normalized_symbol())}"

    def user_data_stream_url(self, listen_key: str) -> str:
        return f"{self.base_url()}/{self.user_stream_path_template.format(listen_key=listen_key)}"


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
    """Production-oriented scaffolding for Binance Futures TESTNET-FIRST streams.

    This class intentionally stops at event-plane responsibilities: endpoint
    selection, listen-key lifecycle hooks, message normalization, and explicit
    polling fallback boundaries. A later phase can attach a real websocket
    transport without forcing another event model rewrite.
    """

    def __init__(self, adapter: ExchangeExecutionAdapter, config: BinanceFuturesStreamConfig):
        self.adapter = adapter
        self.config = config
        self.normalizer = BinanceFuturesEventNormalizer(config.symbol)
        self.listen_key: Optional[str] = None
        self.connected: bool = False

    def source_name(self) -> str:
        mode = "testnet" if self.config.use_testnet else "mainnet"
        return f"binance_futures_user_data:{mode}"

    def source_kind(self) -> str:
        return "websocket"

    def is_live(self) -> bool:
        return self.connected and bool(self.listen_key)

    def describe(self) -> dict[str, Any]:
        return {
            "source": self.source_name(),
            "kind": self.source_kind(),
            "symbol": self.config.symbol,
            "testnet": self.config.use_testnet,
            "connected": self.connected,
            "listen_key_present": bool(self.listen_key),
            "mark_price_stream_url": self.config.mark_price_stream_url(),
            "user_data_stream_url": self.config.user_data_stream_url(self.listen_key or "<listenKey>"),
        }

    def acquire_listen_key(self) -> Optional[str]:
        self.listen_key = self.adapter.create_user_data_stream_listen_key(use_testnet=self.config.use_testnet)
        return self.listen_key

    def keepalive_listen_key(self) -> bool:
        if not self.listen_key:
            return False
        return self.adapter.keepalive_user_data_stream_listen_key(self.listen_key, use_testnet=self.config.use_testnet)

    def close_listen_key(self) -> bool:
        if not self.listen_key:
            return False
        ok = self.adapter.close_user_data_stream_listen_key(self.listen_key, use_testnet=self.config.use_testnet)
        if ok:
            self.listen_key = None
            self.connected = False
        return ok

    def attach_transport(self) -> None:
        self.connected = True

    def detach_transport(self) -> None:
        self.connected = False

    def normalize_message(self, message: dict[str, Any], *, received_at: Optional[str] = None) -> list[ExecutionEvent]:
        return self.normalizer.normalize(message, source=self.source_name(), received_at=received_at)
