from __future__ import annotations
from typing import Optional

from dataclasses import asdict

from btc_contract_backtest.runtime.calibration_models import CalibrationConfig, CalibrationSample, ValidationResult
from btc_contract_backtest.runtime.funding_loader import FundingSnapshotStore


def market_quality_score(*, spread_bps: Optional[float], depth_notional: Optional[float], funding_rate: Optional[float], stale: bool = False) -> float:
    score = 1.0
    if stale:
        score -= 0.5
    if spread_bps is None:
        score -= 0.15
    elif spread_bps > 10:
        score -= 0.15
    if depth_notional is None or depth_notional <= 0:
        score -= 0.2
    if funding_rate is None:
        score -= 0.1
    return max(0.0, min(1.0, score))


def calibrate_slippage_bps(sample: CalibrationSample, config: CalibrationConfig) -> float:
    if config.mode == "baseline":
        return sample.spread_bps or 0.0
    spread_component = (sample.spread_bps or 0.0) * config.slippage_spread_weight
    if sample.depth_notional and sample.depth_notional > 0 and sample.notional > 0:
        depth_ratio = sample.notional / sample.depth_notional
    else:
        depth_ratio = 1.0
    depth_component = depth_ratio * 100 * config.slippage_depth_weight
    vol_component = (0.0 if sample.volatility_bucket != "high" else 5.0) * config.slippage_volatility_weight
    return max(0.0, spread_component + depth_component + vol_component)


def calibrate_fill_ratio(sample: CalibrationSample, config: CalibrationConfig) -> float:
    if sample.depth_notional and sample.depth_notional > 0 and sample.notional > 0:
        ratio = 1.0 - min(sample.notional / sample.depth_notional, 1.0)
    else:
        ratio = config.fill_ratio_floor
    if sample.market_quality_score is not None:
        ratio *= max(sample.market_quality_score, config.market_quality_min_score)
    return max(config.fill_ratio_floor, min(config.fill_ratio_ceiling, ratio))


def calibrate_queue_probability(sample: CalibrationSample, config: CalibrationConfig) -> float:
    base = 0.5
    if sample.queue_model == "conservative":
        base = 0.25
    elif sample.queue_model == "probabilistic":
        base = 0.5
    if sample.market_quality_score is not None:
        base *= max(sample.market_quality_score, config.market_quality_min_score)
    return max(config.queue_probability_floor, min(config.queue_probability_ceiling, base))


def funding_cost_from_sample(sample: CalibrationSample, config: CalibrationConfig, funding_store: Optional[FundingSnapshotStore] = None) -> float:
    if sample.funding_rate is not None and sample.notional is not None:
        return sample.notional * sample.funding_rate
    if funding_store is not None:
        row = funding_store.lookup(sample.timestamp)
        if row and row.get("funding_rate") is not None and sample.notional is not None:
            return sample.notional * float(row["funding_rate"])
    if config.funding_fallback_to_config:
        return sample.funding_cost or 0.0
    return 0.0


def validate_samples(samples: list[dict], config: CalibrationConfig, funding_store: Optional[FundingSnapshotStore] = None) -> ValidationResult:
    if not samples:
        return ValidationResult(sample_count=0, slippage_mae_bps=0.0, fill_ratio_mae=0.0, funding_mae=0.0, quality_weighted_score=0.0, notes=["no samples"])

    slippage_errors = []
    fill_ratio_errors = []
    funding_errors = []
    quality_scores = []

    for raw in samples:
        sample = CalibrationSample(**raw)
        predicted_slippage = calibrate_slippage_bps(sample, config)
        if sample.slippage_bps is not None:
            slippage_errors.append(abs(predicted_slippage - sample.slippage_bps))

        predicted_fill_ratio = calibrate_fill_ratio(sample, config)
        if sample.fill_ratio is not None:
            fill_ratio_errors.append(abs(predicted_fill_ratio - sample.fill_ratio))

        predicted_funding = funding_cost_from_sample(sample, config, funding_store=funding_store)
        if sample.funding_cost is not None:
            funding_errors.append(abs(predicted_funding - sample.funding_cost))

        quality_scores.append(sample.market_quality_score or 0.0)

    def avg(values):
        return sum(values) / len(values) if values else 0.0

    return ValidationResult(
        sample_count=len(samples),
        slippage_mae_bps=avg(slippage_errors),
        fill_ratio_mae=avg(fill_ratio_errors),
        funding_mae=avg(funding_errors),
        quality_weighted_score=avg(quality_scores),
        notes=[],
    )


def sample_from_execution(
    *,
    timestamp: str,
    symbol: str,
    mode: str,
    side: str,
    order_type: str,
    quantity: float,
    notional: float,
    reference_price: float,
    executed_price: Optional[float],
    fill_quantity: Optional[float],
    spread_bps: Optional[float],
    depth_notional: Optional[float],
    queue_model: Optional[str],
    funding_rate: Optional[float],
    funding_cost: Optional[float],
    volatility_bucket: Optional[str],
    latency_ms: Optional[int],
    stale: bool = False,
    metadata: Optional[dict] = None,
) -> CalibrationSample:
    slippage_bps = None
    if executed_price is not None and reference_price > 0:
        slippage_bps = abs(executed_price - reference_price) / reference_price * 10000
    fill_ratio = None if fill_quantity is None or quantity <= 0 else fill_quantity / quantity
    quality = market_quality_score(spread_bps=spread_bps, depth_notional=depth_notional, funding_rate=funding_rate, stale=stale)
    sample = CalibrationSample(
        timestamp=timestamp,
        symbol=symbol,
        mode=mode,
        side=side,
        order_type=order_type,
        quantity=quantity,
        notional=notional,
        reference_price=reference_price,
        executed_price=executed_price,
        fill_quantity=fill_quantity,
        spread_bps=spread_bps,
        slippage_bps=slippage_bps,
        depth_notional=depth_notional,
        queue_model=queue_model,
        fill_ratio=fill_ratio,
        funding_rate=funding_rate,
        funding_cost=funding_cost,
        volatility_bucket=volatility_bucket,
        market_quality_score=quality,
        latency_ms=latency_ms,
        metadata=metadata or {},
    )
    sample.queue_probability = calibrate_queue_probability(sample, CalibrationConfig())
    return sample
