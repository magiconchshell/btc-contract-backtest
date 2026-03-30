from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


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
    executed_price: float | None = None
    fill_quantity: float | None = None
    spread_bps: float | None = None
    slippage_bps: float | None = None
    depth_notional: float | None = None
    queue_model: str | None = None
    queue_probability: float | None = None
    fill_ratio: float | None = None
    funding_rate: float | None = None
    funding_cost: float | None = None
    volatility_bucket: str | None = None
    market_quality_score: float | None = None
    latency_ms: int | None = None
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
