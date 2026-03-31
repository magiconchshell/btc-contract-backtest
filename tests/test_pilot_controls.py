from btc_contract_backtest.live.governance import GovernanceState, TradingMode
from btc_contract_backtest.live.pilot_controls import (
    PilotRiskEnvelope,
    PilotRiskEnvelopeStore,
    build_operator_preflight,
    build_pilot_readiness,
)
from btc_contract_backtest.runtime.calibration_store import CalibrationSampleStore
from btc_contract_backtest.runtime.calibration_engine import sample_from_execution
from btc_contract_backtest.runtime.funding_loader import FundingSnapshotStore
from btc_contract_backtest.runtime.runtime_state_store import JsonRuntimeStateStore


def test_pilot_readiness_reports_warnings_and_score(tmp_path):
    state_file = tmp_path / "live_state.json"
    gov_file = tmp_path / "gov.json"
    approval_file = tmp_path / "approvals.json"
    sample_file = tmp_path / "samples.jsonl"
    funding_file = tmp_path / "funding.jsonl"

    JsonRuntimeStateStore(
        str(state_file), mode="governed_live", symbol="BTC/USDT", leverage=3
    ).flush()
    GovernanceState(str(gov_file)).set_mode(TradingMode.APPROVAL_REQUIRED)
    CalibrationSampleStore(str(sample_file)).append(
        sample_from_execution(
            timestamp="2026-01-01T00:00:00+00:00",
            symbol="BTC/USDT",
            mode="governed_live",
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
    )
    FundingSnapshotStore(str(funding_file)).append(
        {"timestamp": "2026-01-01T00:00:00+00:00", "funding_rate": 0.0001}
    )

    report = build_pilot_readiness(
        state_file=str(state_file),
        governance_state_file=str(gov_file),
        approval_file=str(approval_file),
        calibration_samples_path=str(sample_file),
        funding_snapshots_path=str(funding_file),
    )
    assert report.score > 0
    assert report.evidence["funding_snapshot_count"] == 1


def test_operator_preflight_blocks_when_readiness_below_threshold(tmp_path):
    state_file = tmp_path / "live_state.json"
    gov_file = tmp_path / "gov.json"
    envelope_file = tmp_path / "envelope.json"

    JsonRuntimeStateStore(
        str(state_file), mode="governed_live", symbol="BTC/USDT", leverage=3
    ).flush()
    GovernanceState(str(gov_file)).set_mode(TradingMode.APPROVAL_REQUIRED)
    PilotRiskEnvelopeStore(str(envelope_file)).save(
        PilotRiskEnvelope(min_readiness_score=0.95)
    )

    readiness = build_pilot_readiness(
        state_file=str(state_file),
        governance_state_file=str(gov_file),
        approval_file=str(tmp_path / "approvals.json"),
        calibration_samples_path=str(tmp_path / "samples.jsonl"),
        funding_snapshots_path=str(tmp_path / "funding.jsonl"),
    )
    preflight = build_operator_preflight(
        readiness=readiness,
        state_file=str(state_file),
        governance_state_file=str(gov_file),
        envelope_file=str(envelope_file),
    )
    assert preflight.proceed is False
    assert "readiness_score_below_minimum" in preflight.hard_blocks
