from btc_contract_backtest.config.models import ContractSpec
from btc_contract_backtest.live.exchange_constraints import ExchangeConstraintChecker


def test_exchange_constraints_block_invalid_order_shapes():
    checker = ExchangeConstraintChecker(ContractSpec(symbol="BTC/USDT", leverage=5, tick_size=0.1, lot_size=0.001), min_notional=10.0)
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
