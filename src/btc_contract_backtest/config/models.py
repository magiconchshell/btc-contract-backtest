from dataclasses import dataclass
from typing import Optional


@dataclass
class ContractSpec:
    symbol: str = "BTC/USDT"
    market_type: str = "perpetual"
    quote_currency: str = "USDT"
    leverage: int = 5


@dataclass
class AccountConfig:
    initial_capital: float = 1000.0
    taker_fee_rate: float = 0.0004
    maker_fee_rate: float = 0.0002
    funding_rate_annual: float = 0.10


@dataclass
class RiskConfig:
    max_position_notional_pct: float = 0.95
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    max_holding_bars: Optional[int] = None
    maintenance_margin_ratio: float = 0.005
