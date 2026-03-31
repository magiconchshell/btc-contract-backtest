import pandas as pd

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, ExecutionConfig, LiveRiskConfig, RiskConfig
from btc_contract_backtest.live.shadow_session import ShadowTradingSession
from btc_contract_backtest.live.live_session import GovernedLiveSession
from btc_contract_backtest.strategies.base import BaseStrategy


class StaticStrategy(BaseStrategy):
    def name(self) -> str:
        return "static"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["signal"] = 1
        out["atr"] = 1.0
        return out


class FakeExchange:
    def fetch_ohlcv(self, symbol, timeframe="1h", limit=300):
        return [[1735689600000, 100, 101, 99, 100, 10], [1735693200000, 100, 102, 99, 101, 12]]

    def fetch_ticker(self, symbol):
        return {"last": 101.0, "bid": 100.95, "ask": 101.05}

    def fetch_positions(self, symbols):
        return []

    def fetch_open_orders(self, symbol):
        return []


def test_shadow_session_still_runs_after_runtime_refactor(tmp_path):
    sess = ShadowTradingSession(
        contract=ContractSpec(symbol="BTC/USDT", leverage=3),
        account=AccountConfig(initial_capital=1000.0),
        risk=RiskConfig(),
        strategy=StaticStrategy(),
        execution=ExecutionConfig(enforce_mark_bid_ask_consistency=False),
        live_risk=LiveRiskConfig(reconcile_on_startup=False),
        audit_log=str(tmp_path / "shadow.jsonl"),
        state_file=str(tmp_path / "shadow_state.json"),
        exchange=FakeExchange(),
    )
    payload = sess.step()
    assert payload["event"] in {"decision", "blocked", "hold"}


def test_governed_live_session_still_runs_after_runtime_refactor(tmp_path):
    sess = GovernedLiveSession(
        contract=ContractSpec(symbol="BTC/USDT", leverage=3),
        account=AccountConfig(initial_capital=1000.0),
        risk=RiskConfig(),
        strategy=StaticStrategy(),
        execution=ExecutionConfig(enforce_mark_bid_ask_consistency=False),
        live_risk=LiveRiskConfig(),
        audit_log=str(tmp_path / "live.jsonl"),
        approval_file=str(tmp_path / "approvals.json"),
        governance_state_file=str(tmp_path / "gov.json"),
        alerts_file=str(tmp_path / "alerts.jsonl"),
        state_file=str(tmp_path / "live_state.json"),
        exchange=FakeExchange(),
    )
    sess.gov_state.set_mode(__import__('btc_contract_backtest.live.governance', fromlist=['TradingMode']).TradingMode.APPROVAL_REQUIRED)
    payload = sess.step()
    assert payload["event"] in {"decision", "halted", "blocked", "hold"} or "result" in payload
