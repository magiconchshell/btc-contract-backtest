from btc_contract_backtest.config.models import AccountConfig, ContractSpec, ExecutionConfig, RiskConfig
from btc_contract_backtest.engine.execution_models import MarketSnapshot, OrderSide, OrderStatus, OrderType
from btc_contract_backtest.engine.simulator_core import SimulatorCore


def make_core(**risk_overrides):
    return SimulatorCore(
        contract=ContractSpec(symbol="BTC/USDT", leverage=5),
        account=AccountConfig(initial_capital=1000.0),
        risk=RiskConfig(**risk_overrides),
        execution=ExecutionConfig(),
    )


def make_snapshot(close=100.0, stale=False):
    return MarketSnapshot(
        symbol="BTC/USDT",
        timestamp="2026-01-01T00:00:00Z",
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
        bid=close - 0.1,
        ask=close + 0.1,
        mark_price=close,
        stale=stale,
    )


def test_market_order_creates_and_fills():
    core = make_core()
    order = core.create_order(OrderSide.BUY, 1.0, OrderType.MARKET)
    fills = core.try_fill_order(order, make_snapshot())
    assert len(fills) == 1
    assert order.status in {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED}


def test_cancel_order_changes_status():
    core = make_core()
    order = core.create_order(OrderSide.BUY, 1.0, OrderType.LIMIT, price=100.0)
    core.cancel_order(order.order_id)
    assert order.status == OrderStatus.CANCELED


def test_stale_snapshot_blocked():
    core = make_core(kill_on_stale_data=True)
    allowed = core.check_snapshot_safety(make_snapshot(stale=True))
    assert allowed is False
    assert len(core.risk_events) >= 1


def test_daily_loss_kill_triggered():
    core = make_core(max_daily_loss_pct=1.0)
    core.day_start_equity = 1000.0
    assert core.check_daily_loss_kill(989.0) is True


def test_apply_fill_opens_position():
    core = make_core()
    order = core.create_order(OrderSide.BUY, 1.0, OrderType.MARKET)
    fill = core.try_fill_order(order, make_snapshot())[0]
    core.apply_fill(fill)
    assert core.position.side == 1
    assert core.position.quantity > 0
