from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class Order:
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    reduce_only: bool = False
    post_only: bool = False
    client_order_id: Optional[str] = None
    exchange_order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: float = 0.0
    avg_fill_price: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_error: Optional[str] = None
    tags: dict = field(default_factory=dict)


@dataclass
class FillEvent:
    order_id: str
    symbol: str
    side: OrderSide
    fill_quantity: float
    fill_price: float
    fee: float
    fee_currency: str = "USDT"
    liquidity: str = "taker"
    timestamp: Optional[str] = None


@dataclass
class PositionState:
    symbol: str
    side: int = 0
    quantity: float = 0.0
    entry_price: Optional[float] = None
    entry_time: Optional[str] = None
    notional: float = 0.0
    leverage: float = 1.0
    margin_used: float = 0.0
    bars_held: int = 0
    peak_price: Optional[float] = None
    trough_price: Optional[float] = None
    atr_at_entry: Optional[float] = None
    break_even_armed: bool = False
    partial_taken: bool = False
    stepped_stop_anchor: Optional[float] = None


@dataclass
class MarketSnapshot:
    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    mark_price: Optional[float] = None
    funding_rate: Optional[float] = None
    latency_ms: Optional[int] = None
    stale: bool = False


@dataclass
class RiskEvent:
    event_type: str
    message: str
    severity: str = "warning"
    timestamp: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ReconcileReport:
    ok: bool
    timestamp: Optional[str] = None
    local_position_side: int = 0
    remote_position_side: int = 0
    local_open_orders: int = 0
    remote_open_orders: int = 0
    differences: list[str] = field(default_factory=list)
