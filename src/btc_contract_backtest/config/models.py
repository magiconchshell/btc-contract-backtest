from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LeverageBracket:
    notional_cap: float
    initial_leverage: int
    maintenance_margin_ratio: float = 0.0


@dataclass
class ContractSpec:
    symbol: str = "BTC/USDT"
    market_type: str = "perpetual"
    quote_currency: str = "USDT"
    exchange_id: str = "binance"
    exchange_profile: str = "binance_futures_mainnet"
    leverage: int = 5
    tick_size: float = 0.1
    lot_size: float = 0.001
    min_notional: float = 5.0
    min_quantity: Optional[float] = None
    max_quantity: Optional[float] = None
    price_precision: Optional[int] = None
    quantity_precision: Optional[int] = None
    margin_mode: str = "isolated"
    position_mode: str = "one_way"
    metadata_source: str = "static"
    metadata_as_of: Optional[str] = None
    leverage_brackets: list[LeverageBracket] = field(default_factory=list)


@dataclass
class AccountConfig:
    initial_capital: float = 1000.0
    taker_fee_rate: float = 0.0004
    maker_fee_rate: float = 0.0002
    funding_rate_annual: float = 0.10
    fee_tier: str = "default"
    use_vip_fee_schedule: bool = False


@dataclass
class RiskConfig:
    max_position_notional_pct: float = 0.95
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    max_holding_bars: Optional[int] = None
    atr_stop_mult: Optional[float] = None
    break_even_trigger_pct: Optional[float] = None
    partial_take_profit_pct: Optional[float] = None
    partial_close_ratio: float = 0.5
    stepped_trailing_stop_pct: Optional[float] = None
    risk_per_trade_pct: Optional[float] = None
    atr_position_sizing_mult: Optional[float] = None
    drawdown_position_scale: bool = False
    max_drawdown_scale_start_pct: float = 10.0
    max_drawdown_scale_floor: float = 0.35
    maintenance_margin_ratio: float = 0.005
    max_daily_loss_pct: Optional[float] = None
    max_symbol_exposure_pct: Optional[float] = None
    kill_on_stale_data: bool = True
    stale_data_threshold_seconds: int = 120


@dataclass
class ExecutionConfig:
    use_orderbook_simulation: bool = True
    simulated_spread_bps: float = 1.5
    simulated_slippage_bps: float = 2.0
    max_fill_ratio_per_bar: float = 1.0
    maker_fill_probability: float = 0.35
    latency_ms: int = 150
    allow_partial_fills: bool = True
    queue_priority_model: str = "probabilistic"
    default_order_type: str = "market"
    enable_reduce_only: bool = True
    funding_interval_hours: int = 8
    use_realistic_funding: bool = True
    orderbook_depth_levels: int = 5
    simulated_depth_notional: float = 250000.0
    impact_exponent: float = 0.6
    enforce_mark_bid_ask_consistency: bool = True
    stale_mark_deviation_bps: float = 15.0
    calibration_mode: str = "calibrated"
    calibration_version: str = "t4-v1"
    enforce_exchange_constraints: bool = False


@dataclass
class LiveRiskConfig:
    enable_kill_switch: bool = True
    max_consecutive_failures: int = 5
    max_daily_loss_pct: float = 5.0
    max_open_positions: int = 1
    heartbeat_timeout_seconds: int = 180
    reconcile_on_startup: bool = True
    cancel_open_orders_on_shutdown: bool = True


@dataclass
class EngineConfig:
    contract: ContractSpec = field(default_factory=ContractSpec)
    account: AccountConfig = field(default_factory=AccountConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    live_risk: LiveRiskConfig = field(default_factory=LiveRiskConfig)
