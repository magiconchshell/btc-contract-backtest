from btc_contract_backtest.config.models import AccountConfig, ContractSpec, ExecutionConfig, RiskConfig
from btc_contract_backtest.engine.execution_models import MarketSnapshot, OrderSide, OrderType
from btc_contract_backtest.engine.simulator_core import SimulatorCore


def make_snapshot(close=100.0, bid=99.9, ask=100.1, mark_price=100.0, funding_rate=None, stale=False):
    return MarketSnapshot(
        symbol="BTC/USDT",
        timestamp="2026-01-01T00:00:00Z",
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
        bid=bid,
        ask=ask,
        mark_price=mark_price,
        funding_rate=funding_rate,
        stale=stale,
    )


def make_core(execution: ExecutionConfig | None = None):
    return SimulatorCore(
        contract=ContractSpec(symbol="BTC/USDT", leverage=5),
        account=AccountConfig(initial_capital=1000.0),
        risk=RiskConfig(),
        execution=execution or ExecutionConfig(),
    )


def test_mark_bid_ask_inconsistency_blocked():
    core = make_core(ExecutionConfig(enforce_mark_bid_ask_consistency=True, stale_mark_deviation_bps=5.0))
    allowed = core.check_snapshot_safety(make_snapshot(mark_price=110.0))
    assert allowed is False
    assert len(core.risk_events) >= 1


def test_depth_impact_increases_fill_price():
    core = make_core(ExecutionConfig(simulated_slippage_bps=1.0, simulated_depth_notional=100.0, impact_exponent=1.0))
    order = core.create_order(OrderSide.BUY, quantity=10.0, order_type=OrderType.MARKET)
    fill = core.try_fill_order(order, make_snapshot(close=100.0))[0]
    assert fill.fill_price > 100.1


def test_probabilistic_limit_fill_ratio_reduces_fill_quantity():
    core = make_core(ExecutionConfig(allow_partial_fills=True, max_fill_ratio_per_bar=1.0, maker_fill_probability=0.25, queue_priority_model="probabilistic"))
    order = core.create_order(OrderSide.BUY, quantity=10.0, order_type=OrderType.LIMIT, price=100.0)
    fill = core.try_fill_order(order, make_snapshot(close=100.0))[0]
    assert fill.fill_quantity <= 2.5 + 1e-9


def test_realistic_funding_uses_snapshot_rate():
    core = make_core(ExecutionConfig(use_realistic_funding=True))
    core.position.side = 1
    core.position.quantity = 1.0
    core.position.notional = 100.0
    cost = core.apply_periodic_funding(make_snapshot(close=100.0, funding_rate=0.001))
    assert round(cost, 6) == 0.1
