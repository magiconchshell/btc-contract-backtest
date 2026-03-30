from btc_contract_backtest.runtime.calibration_engine import (
    calibrate_fill_ratio,
    calibrate_queue_probability,
    calibrate_slippage_bps,
    funding_cost_from_sample,
    market_quality_score,
    sample_from_execution,
    validate_samples,
)
from btc_contract_backtest.runtime.calibration_models import CalibrationConfig, CalibrationSample


def test_sample_from_execution_computes_quality_and_slippage():
    sample = sample_from_execution(
        timestamp="2026-01-01T00:00:00+00:00",
        symbol="BTC/USDT",
        mode="paper",
        side="buy",
        order_type="market",
        quantity=1.0,
        notional=100.0,
        reference_price=100.0,
        executed_price=100.2,
        fill_quantity=1.0,
        spread_bps=2.0,
        depth_notional=10000.0,
        queue_model="probabilistic",
        funding_rate=0.0001,
        funding_cost=0.01,
        volatility_bucket="normal",
        latency_ms=100,
    )
    assert sample.slippage_bps is not None
    assert sample.market_quality_score > 0
    assert sample.queue_probability is not None


def test_calibration_functions_return_bounded_values():
    cfg = CalibrationConfig()
    sample = CalibrationSample(
        timestamp="2026-01-01T00:00:00+00:00",
        symbol="BTC/USDT",
        mode="simulation",
        side="buy",
        order_type="market",
        quantity=1.0,
        notional=100.0,
        reference_price=100.0,
        spread_bps=3.0,
        depth_notional=1000.0,
        queue_model="probabilistic",
        funding_rate=0.0001,
        volatility_bucket="high",
        market_quality_score=0.8,
    )
    assert calibrate_slippage_bps(sample, cfg) >= 0
    assert 0 <= calibrate_fill_ratio(sample, cfg) <= 1
    assert 0 <= calibrate_queue_probability(sample, cfg) <= 1
    assert funding_cost_from_sample(sample, cfg) >= 0


def test_validation_harness_returns_metrics():
    cfg = CalibrationConfig()
    sample = sample_from_execution(
        timestamp="2026-01-01T00:00:00+00:00",
        symbol="BTC/USDT",
        mode="paper",
        side="buy",
        order_type="market",
        quantity=1.0,
        notional=100.0,
        reference_price=100.0,
        executed_price=100.2,
        fill_quantity=0.8,
        spread_bps=2.0,
        depth_notional=10000.0,
        queue_model="probabilistic",
        funding_rate=0.0001,
        funding_cost=0.01,
        volatility_bucket="normal",
        latency_ms=100,
    )
    result = validate_samples([sample.to_dict()], cfg)
    assert result.sample_count == 1
    assert result.quality_weighted_score >= 0


def test_market_quality_score_penalizes_stale_or_missing_inputs():
    good = market_quality_score(spread_bps=2.0, depth_notional=10000.0, funding_rate=0.0001, stale=False)
    bad = market_quality_score(spread_bps=None, depth_notional=0.0, funding_rate=None, stale=True)
    assert good > bad
