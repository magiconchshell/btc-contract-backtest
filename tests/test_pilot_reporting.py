import json

from btc_contract_backtest.live.governance import GovernanceState, TradingMode
from btc_contract_backtest.live.pilot_controls import build_operator_preflight, build_pilot_readiness
from btc_contract_backtest.live.pilot_reporting import build_pilot_dossier, evaluate_pilot_run, run_post_submit_closed_loop
from btc_contract_backtest.runtime.calibration_engine import sample_from_execution
from btc_contract_backtest.runtime.calibration_store import CalibrationSampleStore
from btc_contract_backtest.runtime.funding_loader import FundingSnapshotStore
from btc_contract_backtest.runtime.runtime_state_store import JsonRuntimeStateStore


def _seed(tmp_path):
    state_file = tmp_path / "state.json"
    gov_file = tmp_path / "gov.json"
    approval_file = tmp_path / "approvals.json"
    alert_file = tmp_path / "alerts.jsonl"
    sample_file = tmp_path / "samples.jsonl"
    funding_file = tmp_path / "funding.jsonl"

    store = JsonRuntimeStateStore(str(state_file), mode="governed_live", symbol="BTC/USDT", leverage=3)
    store.set_state_fields(
        orders=[{"order_id": "o1", "state": "new"}],
        operator_actions=[{"action": "submit_intended_order"}],
        watchdog={"halted": False},
        updated_at="2026-01-01T00:00:00+00:00",
    )
    store.flush()
    GovernanceState(str(gov_file)).set_mode(TradingMode.APPROVAL_REQUIRED)
    CalibrationSampleStore(str(sample_file)).append(sample_from_execution(
        timestamp="2026-01-01T00:00:00+00:00", symbol="BTC/USDT", mode="governed_live", side="buy", order_type="market",
        quantity=1.0, notional=100.0, reference_price=100.0, executed_price=100.2, fill_quantity=1.0,
        spread_bps=2.0, depth_notional=10000.0, queue_model="probabilistic", funding_rate=0.0001,
        funding_cost=0.01, volatility_bucket="normal", latency_ms=100,
    ))
    FundingSnapshotStore(str(funding_file)).append({"timestamp": "2026-01-01T00:00:00+00:00", "funding_rate": 0.0001})
    alert_file.write_text(json.dumps({"alert_type": "pilot_blocking", "severity": "critical"}) + "\n")
    return state_file, gov_file, approval_file, alert_file, sample_file, funding_file


def test_post_submit_closed_loop_creates_actions(tmp_path):
    state_file, gov_file, approval_file, alert_file, sample_file, funding_file = _seed(tmp_path)
    result = run_post_submit_closed_loop(state_file=str(state_file), alerts_file=str(alert_file), incidents_file=str(tmp_path / "incidents.json"))
    assert result["open_order_count"] == 1
    assert result["actions"]


def test_dossier_and_evaluation_outputs(tmp_path):
    state_file, gov_file, approval_file, alert_file, sample_file, funding_file = _seed(tmp_path)
    readiness = build_pilot_readiness(
        state_file=str(state_file), governance_state_file=str(gov_file), approval_file=str(approval_file),
        calibration_samples_path=str(sample_file), funding_snapshots_path=str(funding_file),
    )
    preflight = build_operator_preflight(readiness=readiness, state_file=str(state_file), governance_state_file=str(gov_file))
    outputs = build_pilot_dossier(
        dossier_dir=str(tmp_path / "dossier"),
        readiness=readiness,
        preflight=preflight,
        state_file=str(state_file),
        alerts_file=str(alert_file),
        incidents_file=str(tmp_path / "incidents.json"),
        calibration_samples_path=str(sample_file),
        funding_snapshots_path=str(funding_file),
    )
    assert outputs["audit"].endswith("audit.json")
    report = evaluate_pilot_run(
        state_file=str(state_file),
        alerts_file=str(alert_file),
        incidents_file=str(tmp_path / "incidents.json"),
        calibration_samples_path=str(sample_file),
    )
    assert report.submit_count == 1
    assert report.recommendation in {"go", "hold", "rollback"}
