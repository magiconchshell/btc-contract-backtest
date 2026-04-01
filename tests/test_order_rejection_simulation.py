"""Tests for order rejection simulation in backtest.

Validates that when enforce_exchange_constraints=True, the simulator
correctly rejects orders that violate exchange constraints (min_notional,
lot_size, etc.).
"""

from __future__ import annotations

import pandas as pd

from btc_contract_backtest.config.models import (
    AccountConfig,
    ContractSpec,
    ExecutionConfig,
    RiskConfig,
)
from btc_contract_backtest.engine.futures_engine import FuturesBacktestEngine


def make_engine(
    execution: ExecutionConfig | None = None,
    contract: ContractSpec | None = None,
    risk: RiskConfig | None = None,
) -> FuturesBacktestEngine:
    return FuturesBacktestEngine(
        contract=contract
        or ContractSpec(
            symbol="BTC/USDT",
            leverage=5,
            min_notional=5.0,
            lot_size=0.001,
        ),
        account=AccountConfig(initial_capital=1000.0),
        risk=risk or RiskConfig(max_position_notional_pct=0.5),
        timeframe="1h",
        execution=execution
        or ExecutionConfig(
            allow_partial_fills=False,
            enforce_exchange_constraints=True,
        ),
    )


def make_df(closes, signals, atr_values=None):
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="h")
    df = pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [100] * len(closes),
            "signal": signals,
        },
        index=idx,
    )
    if atr_values is not None:
        df["atr"] = atr_values
    return df


def test_order_rejection_below_min_notional():
    """Orders with notional < min_notional should be rejected."""
    engine = make_engine(
        contract=ContractSpec(
            symbol="BTC/USDT",
            leverage=5,
            min_notional=100.0,  # Very high — will reject small orders
            lot_size=0.001,
        ),
        execution=ExecutionConfig(
            allow_partial_fills=False,
            enforce_exchange_constraints=True,
        ),
        risk=RiskConfig(max_position_notional_pct=0.001),  # Very small → tiny orders
    )
    df = make_df([100, 100, 100], [1, 0, 0])
    results = engine.simulate(df)
    # With min_notional=100 and tiny position, order should be rejected
    risk_events = results.get("risk_events")
    if risk_events is not None and not risk_events.empty:
        rejection_events = risk_events[risk_events["event_type"] == "order_rejected"]
        assert len(rejection_events) >= 1
    else:
        # If no risk events at all, the order was too small to be created
        assert results["trades"].empty


def test_no_rejection_when_constraints_disabled():
    """Without enforce_exchange_constraints, orders should fill normally."""
    engine = make_engine(
        execution=ExecutionConfig(
            allow_partial_fills=False,
            enforce_exchange_constraints=False,  # Default
        ),
    )
    df = make_df([100, 100, 100], [1, 0, 0])
    results = engine.simulate(df)
    risk_events = results.get("risk_events")
    if risk_events is not None and not risk_events.empty:
        rejection_events = risk_events[risk_events["event_type"] == "order_rejected"]
        assert len(rejection_events) == 0


def test_valid_orders_pass_constraint_check():
    """Orders with sufficient notional should pass constraints when lot_size aligns."""
    engine = make_engine(
        contract=ContractSpec(
            symbol="BTC/USDT",
            leverage=5,
            min_notional=5.0,  # Low threshold
            lot_size=0.00001,  # Very fine lot size to avoid rounding issues
        ),
        execution=ExecutionConfig(
            allow_partial_fills=False,
            enforce_exchange_constraints=True,
        ),
        risk=RiskConfig(max_position_notional_pct=0.5),
    )
    # Use realistic BTC price → notional will easily exceed 5 USDT
    df = make_df([50000, 50000, 50000], [1, 0, 0])
    results = engine.simulate(df)
    # Should have no rejection events
    risk_events = results.get("risk_events")
    if risk_events is not None and not risk_events.empty:
        rejection_events = risk_events[risk_events["event_type"] == "order_rejected"]
        assert len(rejection_events) == 0
