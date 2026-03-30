import json

from btc_contract_backtest.runtime.calibration_engine import funding_cost_from_sample, sample_from_execution, validate_samples
from btc_contract_backtest.runtime.calibration_models import CalibrationConfig
from btc_contract_backtest.runtime.calibration_store import CalibrationSampleStore
from btc_contract_backtest.runtime.funding_loader import FundingSnapshotStore


def test_calibration_store_can_append_and_load(tmp_path):
    store = CalibrationSampleStore(str(tmp_path / "samples.jsonl"))
    sample = sample_from_execution(
        timestamp="2026-01-01T00:00:00+00:00",
        symbol="BTC/USDT",
        mode="backtest",
        side="buy",
        order_type="market",
        quantity=1.0,
        notional=100.0,
        reference_price=100.0,
        executed_price=100.1,
        fill_quantity=1.0,
        spread_bps=2.0,
        depth_notional=10000.0,
        queue_model="probabilistic",
        funding_rate=0.0001,
        funding_cost=0.01,
        volatility_bucket="normal",
        latency_ms=100,
    )
    store.append(sample)
    loaded = store.load()
    assert len(loaded) == 1
    assert loaded[0]["mode"] == "backtest"


def test_funding_snapshot_lookup_and_runtime_fallback(tmp_path):
    funding = FundingSnapshotStore(str(tmp_path / "funding.jsonl"))
    funding.append({"timestamp": "2026-01-01T00:00:00+00:00", "funding_rate": 0.0002})

    cfg = CalibrationConfig(mode="validation")
    sample = sample_from_execution(
        timestamp="2026-01-01T00:30:00+00:00",
        symbol="BTC/USDT",
        mode="backtest",
        side="funding",
        order_type="funding",
        quantity=1.0,
        notional=100.0,
        reference_price=100.0,
        executed_price=100.0,
        fill_quantity=1.0,
        spread_bps=1.0,
        depth_notional=10000.0,
        queue_model="probabilistic",
        funding_rate=None,
        funding_cost=None,
        volatility_bucket="normal",
        latency_ms=100,
    )

    cost = funding_cost_from_sample(sample, cfg, funding_store=funding)
    assert cost == 0.02


def test_validation_respects_runtime_mode_and_version(tmp_path):
    store = CalibrationSampleStore(str(tmp_path / "samples.jsonl"))
    sample = sample_from_execution(
        timestamp="2026-01-01T00:00:00+00:00",
        symbol="BTC/USDT",
        mode="validation",
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
        metadata={"calibration_version": "t4-v1"},
    )
    store.append(sample)
    result = validate_samples(store.load(), CalibrationConfig(mode="validation", version="t4-v1"))
    assert result.sample_count == 1
    assert result.quality_weighted_score >= 0
