"""Shared exit evaluation logic for both backtest and live trading.

This module extracts position exit checking from BacktestRuntime so that
the same rules (stop-loss, take-profit, trailing stop, ATR stop, break-even,
partial take-profit, stepped trailing stop, time exit) apply to both
backtesting and live trading. The live exit manager wraps this with actual
order submission through the governed execution path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from btc_contract_backtest.config.models import RiskConfig


@dataclass
class ExitEvalContext:
    """Market and position context needed for exit evaluation."""

    position_side: int  # 1 = long, -1 = short, 0 = flat
    entry_price: Optional[float] = None
    quantity: float = 0.0
    bars_held: int = 0
    peak_price: Optional[float] = None
    trough_price: Optional[float] = None
    break_even_armed: bool = False
    partial_taken: bool = False
    stepped_stop_anchor: Optional[float] = None
    atr_at_entry: Optional[float] = None


@dataclass
class ExitSignal:
    """Result of an exit evaluation."""

    should_close: bool
    reason: Optional[str] = None
    is_partial: bool = False
    close_ratio: float = 1.0
    metadata: dict = field(default_factory=dict)


@dataclass
class PositionStateUpdate:
    """State mutations to apply to the position after evaluation."""

    break_even_armed: Optional[bool] = None
    partial_taken: Optional[bool] = None
    stepped_stop_anchor: Optional[float] = None
    peak_price: Optional[float] = None
    trough_price: Optional[float] = None


def update_position_tracking(ctx: ExitEvalContext, price: float) -> PositionStateUpdate:
    """Update peak/trough/bars tracking for an open position.

    This should be called every bar/tick for open positions.
    Returns state updates to apply.
    """
    if ctx.position_side == 0:
        return PositionStateUpdate()

    new_peak = price if ctx.peak_price is None else max(ctx.peak_price, price)
    new_trough = price if ctx.trough_price is None else min(ctx.trough_price, price)
    return PositionStateUpdate(
        peak_price=new_peak,
        trough_price=new_trough,
    )


def evaluate_exit(
    risk: RiskConfig,
    ctx: ExitEvalContext,
    current_price: float,
) -> tuple[Optional[ExitSignal], PositionStateUpdate]:
    """Evaluate whether the current position should be closed.

    This is the core exit logic shared between backtest and live.
    Returns an ExitSignal if a close is warranted, plus any position
    state updates that must be applied regardless of close.

    Important: for partial take-profit, this returns a partial close signal
    first. The full close/exit signals only fire if partial has already
    been taken (or not configured).
    """
    if ctx.position_side == 0 or ctx.entry_price is None:
        return None, PositionStateUpdate()

    price = current_price
    pnl_pct = ((price - ctx.entry_price) / ctx.entry_price) * ctx.position_side

    state_update = PositionStateUpdate()

    # --- Partial take-profit (fires before full close checks) ---
    if (
        risk.partial_take_profit_pct is not None
        and not ctx.partial_taken
        and pnl_pct >= risk.partial_take_profit_pct
    ):
        state_update.partial_taken = True
        return ExitSignal(
            should_close=True,
            reason="partial_take_profit",
            is_partial=True,
            close_ratio=risk.partial_close_ratio,
        ), state_update

    # --- Break-even arming ---
    if (
        risk.break_even_trigger_pct is not None
        and pnl_pct >= risk.break_even_trigger_pct
    ):
        state_update.break_even_armed = True

    # Track the close reason (first matching wins)
    should_close: Optional[str] = None

    # --- ATR stop ---
    if risk.atr_stop_mult is not None and ctx.atr_at_entry is not None:
        if ctx.position_side == 1 and price <= ctx.entry_price - (
            ctx.atr_at_entry * risk.atr_stop_mult
        ):
            should_close = "atr_stop"
        if ctx.position_side == -1 and price >= ctx.entry_price + (
            ctx.atr_at_entry * risk.atr_stop_mult
        ):
            should_close = "atr_stop"

    # --- Break-even stop ---
    break_even_armed = ctx.break_even_armed or (state_update.break_even_armed is True)
    if break_even_armed and should_close is None:
        if ctx.position_side == 1 and price <= ctx.entry_price:
            should_close = "break_even_stop"
        if ctx.position_side == -1 and price >= ctx.entry_price:
            should_close = "break_even_stop"

    # --- Stepped trailing stop ---
    if risk.stepped_trailing_stop_pct is not None and should_close is None:
        if ctx.position_side == 1:
            peak = ctx.peak_price
            if peak is None:
                anchor = ctx.stepped_stop_anchor or price
            else:
                anchor = (
                    peak
                    if ctx.stepped_stop_anchor is None
                    else max(ctx.stepped_stop_anchor, peak)
                )
            state_update.stepped_stop_anchor = anchor
            if price <= anchor * (1 - risk.stepped_trailing_stop_pct):
                should_close = "stepped_trailing_stop"
        if ctx.position_side == -1:
            trough = ctx.trough_price
            if trough is None:
                anchor = ctx.stepped_stop_anchor or price
            else:
                anchor = (
                    trough
                    if ctx.stepped_stop_anchor is None
                    else min(ctx.stepped_stop_anchor, trough)
                )
            state_update.stepped_stop_anchor = anchor
            if price >= anchor * (1 + risk.stepped_trailing_stop_pct):
                should_close = "stepped_trailing_stop"

    # --- Stop-loss ---
    if (
        risk.stop_loss_pct is not None
        and should_close is None
        and pnl_pct <= -risk.stop_loss_pct
    ):
        should_close = "stop_loss"

    # --- Take-profit ---
    if (
        risk.take_profit_pct is not None
        and should_close is None
        and pnl_pct >= risk.take_profit_pct
    ):
        should_close = "take_profit"

    # --- Trailing stop ---
    if risk.trailing_stop_pct is not None and should_close is None:
        if (
            ctx.position_side == 1
            and ctx.peak_price is not None
            and price <= ctx.peak_price * (1 - risk.trailing_stop_pct)
        ):
            should_close = "trailing_stop"
        if (
            ctx.position_side == -1
            and ctx.trough_price is not None
            and price >= ctx.trough_price * (1 + risk.trailing_stop_pct)
        ):
            should_close = "trailing_stop"

    # --- Time exit ---
    if (
        risk.max_holding_bars is not None
        and should_close is None
        and ctx.bars_held >= risk.max_holding_bars
    ):
        should_close = "time_exit"

    if should_close is not None:
        return ExitSignal(
            should_close=True,
            reason=should_close,
            is_partial=False,
            close_ratio=1.0,
            metadata={"pnl_pct": pnl_pct, "price": price},
        ), state_update

    return None, state_update
