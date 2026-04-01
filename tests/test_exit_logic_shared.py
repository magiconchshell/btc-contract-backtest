"""Unit tests for the shared exit_logic module (pure functions)."""

from __future__ import annotations

from btc_contract_backtest.config.models import RiskConfig
from btc_contract_backtest.runtime.exit_logic import (
    ExitEvalContext,
    evaluate_exit,
    update_position_tracking,
)


def _ctx(
    side: int = 1,
    entry: float = 100.0,
    quantity: float = 1.0,
    bars_held: int = 0,
    peak_price: float | None = None,
    trough_price: float | None = None,
    break_even_armed: bool = False,
    partial_taken: bool = False,
    atr_at_entry: float | None = None,
    stepped_stop_anchor: float | None = None,
) -> ExitEvalContext:
    return ExitEvalContext(
        position_side=side,
        entry_price=entry,
        quantity=quantity,
        bars_held=bars_held,
        peak_price=peak_price,
        trough_price=trough_price,
        break_even_armed=break_even_armed,
        partial_taken=partial_taken,
        atr_at_entry=atr_at_entry,
        stepped_stop_anchor=stepped_stop_anchor,
    )


# ─── Flat / no-op ───


def test_flat_position_no_exit():
    sig, _ = evaluate_exit(RiskConfig(stop_loss_pct=0.03), _ctx(side=0), 95.0)
    assert sig is None


def test_no_entry_price_no_exit():
    sig, _ = evaluate_exit(
        RiskConfig(stop_loss_pct=0.03), _ctx(side=1, entry=None), 95.0
    )
    assert sig is None


# ─── Stop-loss ───


def test_long_stop_loss_triggers():
    sig, _ = evaluate_exit(
        RiskConfig(stop_loss_pct=0.03), _ctx(side=1, entry=100), 96.0
    )
    assert sig is not None and sig.reason == "stop_loss"


def test_long_stop_loss_not_triggered():
    sig, _ = evaluate_exit(
        RiskConfig(stop_loss_pct=0.03), _ctx(side=1, entry=100), 98.0
    )
    assert sig is None


def test_short_stop_loss_triggers():
    sig, _ = evaluate_exit(
        RiskConfig(stop_loss_pct=0.03), _ctx(side=-1, entry=100), 104.0
    )
    assert sig is not None and sig.reason == "stop_loss"


def test_short_stop_loss_not_triggered():
    sig, _ = evaluate_exit(
        RiskConfig(stop_loss_pct=0.03), _ctx(side=-1, entry=100), 102.0
    )
    assert sig is None


# ─── Take-profit ───


def test_long_take_profit_triggers():
    sig, _ = evaluate_exit(
        RiskConfig(take_profit_pct=0.05), _ctx(side=1, entry=100), 106.0
    )
    assert sig is not None and sig.reason == "take_profit"


def test_short_take_profit_triggers():
    sig, _ = evaluate_exit(
        RiskConfig(take_profit_pct=0.05), _ctx(side=-1, entry=100), 94.0
    )
    assert sig is not None and sig.reason == "take_profit"


# ─── Trailing stop ───


def test_long_trailing_stop_triggers():
    sig, _ = evaluate_exit(
        RiskConfig(trailing_stop_pct=0.02),
        _ctx(side=1, entry=100, peak_price=110.0),
        107.0,  # 110 * 0.98 = 107.8 → price 107 triggers
    )
    assert sig is not None and sig.reason == "trailing_stop"


def test_long_trailing_stop_not_triggered():
    sig, _ = evaluate_exit(
        RiskConfig(trailing_stop_pct=0.02),
        _ctx(side=1, entry=100, peak_price=110.0),
        108.5,
    )
    assert sig is None


def test_short_trailing_stop_triggers():
    sig, _ = evaluate_exit(
        RiskConfig(trailing_stop_pct=0.02),
        _ctx(side=-1, entry=100, trough_price=90.0),
        92.0,  # 90 * 1.02 = 91.8 → price 92 triggers
    )
    assert sig is not None and sig.reason == "trailing_stop"


def test_no_peak_no_trailing_stop():
    sig, _ = evaluate_exit(
        RiskConfig(trailing_stop_pct=0.02),
        _ctx(side=1, entry=100, peak_price=None),
        90.0,
    )
    assert sig is None


# ─── ATR stop ───


def test_long_atr_stop_triggers():
    sig, _ = evaluate_exit(
        RiskConfig(atr_stop_mult=2.0),
        _ctx(side=1, entry=100, atr_at_entry=3.0),
        93.0,  # 100 - 6 = 94 → 93 triggers
    )
    assert sig is not None and sig.reason == "atr_stop"


def test_long_atr_stop_not_triggered():
    sig, _ = evaluate_exit(
        RiskConfig(atr_stop_mult=2.0),
        _ctx(side=1, entry=100, atr_at_entry=3.0),
        95.0,
    )
    assert sig is None


def test_short_atr_stop_triggers():
    sig, _ = evaluate_exit(
        RiskConfig(atr_stop_mult=2.0),
        _ctx(side=-1, entry=100, atr_at_entry=3.0),
        107.0,  # 100 + 6 = 106 → 107 triggers
    )
    assert sig is not None and sig.reason == "atr_stop"


# ─── Break-even ───


def test_break_even_armed_triggers_long():
    sig, _ = evaluate_exit(
        RiskConfig(break_even_trigger_pct=0.05),
        _ctx(side=1, entry=100, break_even_armed=True),
        99.0,
    )
    assert sig is not None and sig.reason == "break_even_stop"


def test_break_even_not_armed_no_trigger():
    sig, _ = evaluate_exit(
        RiskConfig(break_even_trigger_pct=0.05),
        _ctx(side=1, entry=100, break_even_armed=False),
        99.0,
    )
    assert sig is None


def test_break_even_arms_on_profit():
    _, upd = evaluate_exit(
        RiskConfig(break_even_trigger_pct=0.05),
        _ctx(side=1, entry=100),
        106.0,
    )
    assert upd.break_even_armed is True


# ─── Partial take-profit ───


def test_partial_take_profit_triggers():
    sig, upd = evaluate_exit(
        RiskConfig(partial_take_profit_pct=0.03, partial_close_ratio=0.5),
        _ctx(side=1, entry=100, partial_taken=False),
        104.0,
    )
    assert sig is not None
    assert sig.reason == "partial_take_profit"
    assert sig.is_partial
    assert sig.close_ratio == 0.5
    assert upd.partial_taken is True


def test_partial_already_taken_skips():
    sig, _ = evaluate_exit(
        RiskConfig(partial_take_profit_pct=0.03, take_profit_pct=0.06),
        _ctx(side=1, entry=100, partial_taken=True),
        104.0,
    )
    assert sig is None  # No full TP at 4%


# ─── Time exit ───


def test_time_exit_triggers():
    sig, _ = evaluate_exit(
        RiskConfig(max_holding_bars=10),
        _ctx(side=1, entry=100, bars_held=10),
        100.0,
    )
    assert sig is not None and sig.reason == "time_exit"


def test_time_exit_not_triggered():
    sig, _ = evaluate_exit(
        RiskConfig(max_holding_bars=10),
        _ctx(side=1, entry=100, bars_held=9),
        100.0,
    )
    assert sig is None


# ─── Stepped trailing stop ───


def test_long_stepped_trailing_triggers():
    sig, upd = evaluate_exit(
        RiskConfig(stepped_trailing_stop_pct=0.02),
        _ctx(side=1, entry=100, peak_price=110.0, stepped_stop_anchor=None),
        107.0,  # anchor=110, 110*0.98=107.8 → 107 triggers
    )
    assert sig is not None and sig.reason == "stepped_trailing_stop"
    assert upd.stepped_stop_anchor == 110.0


def test_short_stepped_trailing_triggers():
    sig, _ = evaluate_exit(
        RiskConfig(stepped_trailing_stop_pct=0.02),
        _ctx(side=-1, entry=100, trough_price=90.0, stepped_stop_anchor=None),
        92.0,  # anchor=90, 90*1.02=91.8 → 92 triggers
    )
    assert sig is not None and sig.reason == "stepped_trailing_stop"


# ─── Priority ───


def test_atr_stop_higher_priority_than_stop_loss():
    sig, _ = evaluate_exit(
        RiskConfig(atr_stop_mult=1.0, stop_loss_pct=0.01),
        _ctx(side=1, entry=100, atr_at_entry=5.0),
        94.0,  # Both trigger, ATR should win
    )
    assert sig is not None and sig.reason == "atr_stop"


# ─── Position tracking ───


def test_update_tracking_updates_peak():
    upd = update_position_tracking(_ctx(side=1, peak_price=105), 110.0)
    assert upd.peak_price == 110.0


def test_update_tracking_preserves_peak():
    upd = update_position_tracking(_ctx(side=1, peak_price=105), 103.0)
    assert upd.peak_price == 105.0


def test_update_tracking_updates_trough():
    upd = update_position_tracking(_ctx(side=-1, trough_price=95), 90.0)
    assert upd.trough_price == 90.0


def test_update_tracking_flat_no_update():
    upd = update_position_tracking(_ctx(side=0), 100.0)
    assert upd.peak_price is None
    assert upd.trough_price is None
