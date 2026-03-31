from btc_contract_backtest.config.models import ContractSpec, LeverageBracket
from btc_contract_backtest.live.binance_futures import BinanceSymbolRules, with_binance_symbol_rules
from btc_contract_backtest.live.exchange_constraints import ExchangeConstraintChecker


def test_exchange_constraints_block_invalid_order_shapes():
    checker = ExchangeConstraintChecker(
        ContractSpec(
            symbol="BTC/USDT",
            leverage=5,
            tick_size=0.1,
            lot_size=0.001,
            margin_mode="isolated",
        ),
        min_notional=10.0,
    )
    result = checker.check(
        quantity=0.0015,
        price=100.05,
        notional=5.0,
        available_margin=0.5,
        leverage=3,
        reduce_only=True,
        position_side=0,
        account_mode="weird",
        max_open_positions=1,
        current_open_positions=2,
    ).to_dict()

    assert result["ok"] is False
    codes = {item["code"] for item in result["violations"]}
    assert "lot_size_violation" in codes
    assert "tick_size_violation" in codes
    assert "min_notional_violation" in codes
    assert "leverage_mismatch" in codes
    assert "insufficient_margin" in codes
    assert "reduce_only_without_position" in codes
    assert "unknown_account_mode" in codes
    assert "max_open_positions_exceeded" in codes


def test_exchange_constraints_enforce_leverage_brackets_and_reduce_only_direction():
    checker = ExchangeConstraintChecker(
        ContractSpec(
            symbol="BTC/USDT",
            leverage=5,
            tick_size=0.1,
            lot_size=0.001,
            margin_mode="cross",
            leverage_brackets=[
                LeverageBracket(notional_cap=1000.0, initial_leverage=20, maintenance_margin_ratio=0.005),
                LeverageBracket(notional_cap=10000.0, initial_leverage=10, maintenance_margin_ratio=0.01),
            ],
        ),
        min_notional=5.0,
    )

    result = checker.validate_order(
        quantity=0.5,
        price=100.0,
        side="buy",
        order_type="market",
        notional=50.0,
        leverage=15,
        reduce_only=True,
        position_side=1,
        current_position_side=1,
        current_position_notional=10.0,
        available_margin=0.1,
        account_mode="one_way",
    )

    codes = {item["code"] for item in result.violations}
    assert result.ok is False
    assert "reduce_only_direction_invalid" in codes
    assert "reduce_only_exceeds_position" in codes
    assert "leverage_bracket_violation" not in codes


def test_exchange_constraints_accept_binance_metadata_brackets():
    contract = with_binance_symbol_rules(
        ContractSpec(symbol="BTC/USDT", leverage=15, tick_size=0.1, lot_size=0.001),
        BinanceSymbolRules(
            symbol="BTC/USDT",
            exchange_symbol="BTCUSDT",
            status="TRADING",
            contract_type="PERPETUAL",
            tick_size=0.1,
            lot_size=0.001,
            market_lot_size=0.001,
            min_notional=5.0,
            min_quantity=0.001,
            max_quantity=1000.0,
            price_precision=2,
            quantity_precision=3,
            base_asset="BTC",
            quote_asset="USDT",
            margin_asset="USDT",
            metadata_source="binance_futures_testnet",
            metadata_as_of="2026-03-31T00:00:00+00:00",
            leverage_brackets=[
                LeverageBracket(notional_cap=1000.0, initial_leverage=20, maintenance_margin_ratio=0.005),
                LeverageBracket(notional_cap=10000.0, initial_leverage=10, maintenance_margin_ratio=0.01),
            ],
        ),
    )
    checker = ExchangeConstraintChecker(contract)
    result = checker.validate_order(quantity=0.5, price=100.0, side="buy", notional=50.0, leverage=15)
    assert result.ok is True
