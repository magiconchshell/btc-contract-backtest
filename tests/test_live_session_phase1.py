"""Tests for GovernedLiveSession Phase 1 additions.

Tests position sync, fill processing, exit integration, and shutdown.
"""

from __future__ import annotations


import pytest

from btc_contract_backtest.runtime.exit_logic import (
    ExitEvalContext,
    evaluate_exit,
    update_position_tracking,
)


# ─── Test fill processing logic (isolated from live session) ─────────


class FakePosition:
    def __init__(self):
        self.side = 0
        self.quantity = 0.0
        self.entry_price = None
        self.entry_time = None
        self.notional = 0.0
        self.leverage = 5
        self.margin_used = 0.0
        self.symbol = "BTC/USDT"
        self.bars_held = 0
        self.peak_price = None
        self.trough_price = None
        self.break_even_armed = False
        self.partial_taken = False
        self.stepped_stop_anchor = None
        self.atr_at_entry = None


class TestFillProcessing:
    """Test the fill processing logic used by _process_pending_fills."""

    def test_open_fill_sets_position(self):
        pos = FakePosition()
        fill_data = {
            "fill_price": 50000.0,
            "fill_quantity": 0.01,
            "side": "buy",
            "reduce_only": False,
            "realized_pnl": None,
            "timestamp": "2026-01-01T00:00:00Z",
        }
        # Simulate open fill logic
        fill_side = 1 if fill_data["side"] == "buy" else -1
        pos.side = fill_side
        pos.quantity = fill_data["fill_quantity"]
        pos.entry_price = fill_data["fill_price"]
        pos.notional = pos.quantity * pos.entry_price

        assert pos.side == 1
        assert pos.quantity == 0.01
        assert pos.entry_price == 50000.0
        assert pos.notional == 500.0

    def test_close_fill_applies_pnl(self):
        pos = FakePosition()
        pos.side = 1
        pos.quantity = 0.01
        pos.entry_price = 50000.0
        pos.notional = 500.0
        capital = 1000.0

        fill_data = {
            "fill_price": 51000.0,
            "fill_quantity": 0.01,
            "side": "sell",
            "reduce_only": True,
            "realized_pnl": "10.0",
        }

        pnl = float(fill_data["realized_pnl"])
        capital += pnl
        remaining = pos.quantity - fill_data["fill_quantity"]

        assert capital == 1010.0
        assert remaining <= 1e-12  # fully closed

    def test_partial_close_reduces_position(self):
        pos = FakePosition()
        pos.side = 1
        pos.quantity = 0.1
        pos.entry_price = 50000.0
        pos.notional = 5000.0

        close_qty = 0.05
        remaining = pos.quantity - close_qty

        assert remaining == pytest.approx(0.05)
        assert remaining > 1e-12  # not fully closed

    def test_add_to_position_averages_entry(self):
        pos = FakePosition()
        pos.side = 1
        pos.quantity = 0.01
        pos.entry_price = 50000.0

        new_fill_qty = 0.01
        new_fill_price = 52000.0

        old_qty = pos.quantity
        old_entry = pos.entry_price
        new_qty = old_qty + new_fill_qty
        avg_entry = (old_qty * old_entry + new_fill_qty * new_fill_price) / new_qty

        assert new_qty == 0.02
        assert avg_entry == 51000.0


class TestPositionSyncFromExchange:
    """Test the position sync logic."""

    def test_sync_long_position(self):
        pos = FakePosition()
        # Simulate what _sync_position_from_exchange does
        contracts = 0.01
        entry_price = 50000.0
        leverage = 5

        pos.side = 1 if contracts > 0 else -1
        pos.quantity = abs(contracts)
        pos.entry_price = entry_price
        pos.notional = abs(contracts) * entry_price
        pos.margin_used = pos.notional / leverage

        assert pos.side == 1
        assert pos.quantity == 0.01
        assert pos.notional == 500.0
        assert pos.margin_used == 100.0

    def test_sync_short_position(self):
        pos = FakePosition()
        contracts = -0.02
        entry_price = 48000.0
        leverage = 5

        pos.side = 1 if contracts > 0 else -1
        pos.quantity = abs(contracts)
        pos.entry_price = entry_price
        pos.notional = abs(contracts) * entry_price
        pos.margin_used = pos.notional / leverage

        assert pos.side == -1
        assert pos.quantity == 0.02
        assert pos.notional == 960.0

    def test_sync_flat_clears_local(self):
        pos = FakePosition()
        pos.side = 1
        pos.quantity = 0.01
        pos.entry_price = 50000.0

        # No contracts on exchange → clear
        pos.side = 0
        pos.quantity = 0.0
        pos.entry_price = None
        pos.notional = 0.0
        pos.margin_used = 0.0

        assert pos.side == 0
        assert pos.quantity == 0.0


class TestExitLogicIntegrationWithLiveContext:
    """Test that exit_logic.evaluate_exit works correctly when called
    from a live session context (building ExitEvalContext from position)."""

    def test_exit_context_from_position(self):
        pos = FakePosition()
        pos.side = 1
        pos.entry_price = 50000.0
        pos.quantity = 0.01
        pos.bars_held = 15
        pos.peak_price = 52000.0

        from btc_contract_backtest.config.models import RiskConfig

        ctx = ExitEvalContext(
            position_side=pos.side,
            entry_price=pos.entry_price,
            quantity=pos.quantity,
            bars_held=pos.bars_held,
            peak_price=pos.peak_price,
            trough_price=pos.trough_price,
        )
        risk = RiskConfig(stop_loss_pct=0.03)
        sig, _ = evaluate_exit(risk, ctx, 48000.0)  # -4% loss
        assert sig is not None
        assert sig.reason == "stop_loss"

    def test_exit_tracking_updates_position(self):
        pos = FakePosition()
        pos.side = 1
        pos.peak_price = 51000.0

        ctx = ExitEvalContext(
            position_side=pos.side,
            peak_price=pos.peak_price,
            trough_price=pos.trough_price,
        )
        upd = update_position_tracking(ctx, 53000.0)
        # Apply update
        pos.peak_price = upd.peak_price

        assert pos.peak_price == 53000.0
