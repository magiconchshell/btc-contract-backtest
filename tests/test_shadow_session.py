import json
from pathlib import Path

import pandas as pd

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, ExecutionConfig, LiveRiskConfig, RiskConfig
from btc_contract_backtest.live.shadow_session import ShadowTradingSession
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


def test_shadow_session_writes_audit_log(tmp_path):
    audit_path = Path(tmp_path) / "shadow.jsonl"
    sess = ShadowTradingSession(
        contract=ContractSpec(symbol="BTC/USDT", leverage=3),
        account=AccountConfig(initial_capital=1000.0),
        risk=RiskConfig(),
        strategy=StaticStrategy(),
        execution=ExecutionConfig(enforce_mark_bid_ask_consistency=False),
        live_risk=LiveRiskConfig(reconcile_on_startup=False),
        audit_log=str(audit_path),
    )
    sess.exchange = FakeExchange()
    sess.adapter.exchange = sess.exchange

    payload = sess.step()
    assert audit_path.exists()
    lines = audit_path.read_text().strip().splitlines()
    assert len(lines) >= 1
    row = json.loads(lines[-1])
    assert row["event_type"] in {"shadow_decision", "shadow_blocked", "reconcile"}
    assert isinstance(payload, dict)
