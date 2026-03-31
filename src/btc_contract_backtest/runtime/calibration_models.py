from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional, Any


@dataclass
class CalibrationSample:
    timestamp: str
    symbol: str
    mode: str
    side: str
    order_type: str
    quantity: float
    notional: float
    reference_price: float
    executed_price: Optional[float] = None
    fill_quantity: Optional[float] = None
    spread_bps: Optional[float] = None
    slippage_bps: Optional[float] = None
    depth_notional: Optional[float] = None
    queue_model: Optional[str] = None
    queue_probability: Optional[float] = None
    fill_ratio: Optional[float] = None
    funding_rate: Optional[float] = None
    funding_cost: Optional[float] = None
    volatility_bucket: Optional[str] = None
    market_quality_score: Optional[float] = None
    latency_ms: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CalibrationConfig:
    mode: str = "calibrated"
    version: str = "t4-v1"
    slippage_spread_weight: float = 0.35
    slippage_depth_weight: float = 0.45
    slippage_volatility_weight: float = 0.20
    fill_ratio_floor: float = 0.10
    fill_ratio_ceiling: float = 1.0
    queue_probability_floor: float = 0.05
    queue_probability_ceiling: float = 0.95
    market_quality_min_score: float = 0.5
    funding_fallback_to_config: bool = True


@dataclass
class ValidationResult:
    sample_count: int
    slippage_mae_bps: float
    fill_ratio_mae: float
    funding_mae: float
    quality_weighted_score: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
