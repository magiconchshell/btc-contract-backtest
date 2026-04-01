"""Live exit manager for GovernedLiveSession.

Applies shared exit evaluation logic and submits close orders through
the governed execution path (reduce_only=True).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from btc_contract_backtest.config.models import RiskConfig
from btc_contract_backtest.engine.execution_models import (
    Order,
    OrderSide,
    OrderType,
)
from btc_contract_backtest.engine.simulator_core import SimulatorCore
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.event_stream import EventDrivenExecutionSource
from btc_contract_backtest.live.governance import AlertSink
from btc_contract_backtest.live.submit_ledger import SubmitLedger
from btc_contract_backtest.runtime.exit_logic import (
    ExitEvalContext,
    PositionStateUpdate,
    evaluate_exit,
    update_position_tracking,
)

logger = logging.getLogger(__name__)


class LiveExitManager:
    """Manages position exits for live trading sessions.

    Evaluates exit conditions using the shared exit_logic module, then
    submits reduce-only orders through the exchange adapter. Maintains
    audit trail and event recording for all exit actions.
    """

    def __init__(
        self,
        adapter: ExchangeExecutionAdapter,
        risk: RiskConfig,
        alerts: AlertSink,
        audit: AuditLogger,
        submit_ledger: SubmitLedger,
        event_source: EventDrivenExecutionSource,
    ):
        self.adapter = adapter
        self.risk = risk
        self.alerts = alerts
        self.audit = audit
        self.submit_ledger = submit_ledger
        self.event_source = event_source

    def _build_exit_context(self, core: SimulatorCore) -> ExitEvalContext:
        """Build exit evaluation context from the simulator core's position."""
        pos = core.position
        return ExitEvalContext(
            position_side=pos.side,
            entry_price=pos.entry_price,
            quantity=pos.quantity,
            bars_held=pos.bars_held,
            peak_price=pos.peak_price,
            trough_price=pos.trough_price,
            break_even_armed=pos.break_even_armed,
            partial_taken=pos.partial_taken,
            stepped_stop_anchor=pos.stepped_stop_anchor,
            atr_at_entry=pos.atr_at_entry,
        )

    def _apply_state_update(
        self, core: SimulatorCore, update: PositionStateUpdate
    ) -> None:
        """Apply position state mutations from exit evaluation."""
        if update.break_even_armed is not None:
            core.position.break_even_armed = update.break_even_armed
        if update.partial_taken is not None:
            core.position.partial_taken = update.partial_taken
        if update.stepped_stop_anchor is not None:
            core.position.stepped_stop_anchor = update.stepped_stop_anchor
        if update.peak_price is not None:
            core.position.peak_price = update.peak_price
        if update.trough_price is not None:
            core.position.trough_price = update.trough_price

    def update_tracking(self, core: SimulatorCore, price: float) -> None:
        """Update peak/trough tracking and bars held for the open position."""
        if core.position.side == 0:
            return
        core.position.bars_held += 1
        ctx = self._build_exit_context(core)
        update = update_position_tracking(ctx, price)
        self._apply_state_update(core, update)

    def check_and_submit_exit(
        self,
        core: SimulatorCore,
        current_price: float,
        symbol: str,
    ) -> Optional[dict[str, Any]]:
        """Evaluate exit conditions and submit close order if warranted.

        Returns a dict describing the exit action taken, or None if no exit.
        """
        if core.position.side == 0:
            return None

        ctx = self._build_exit_context(core)
        exit_signal, state_update = evaluate_exit(self.risk, ctx, current_price)
        self._apply_state_update(core, state_update)

        if exit_signal is None or not exit_signal.should_close:
            return None

        # Calculate close quantity
        if exit_signal.is_partial:
            close_qty = abs(core.position.quantity) * exit_signal.close_ratio
        else:
            close_qty = abs(core.position.quantity)

        if close_qty <= 0:
            return None

        # Determine order side (opposite of position)
        order_side = "sell" if core.position.side == 1 else "buy"

        now = datetime.now(timezone.utc).isoformat()

        order = Order(
            order_id="exit",
            symbol=symbol,
            side=OrderSide.SELL if core.position.side == 1 else OrderSide.BUY,
            quantity=close_qty,
            order_type=OrderType.MARKET,
            reduce_only=True,
        )

        # Log the exit intent
        exit_payload = {
            "timestamp": now,
            "reason": exit_signal.reason,
            "is_partial": exit_signal.is_partial,
            "close_quantity": close_qty,
            "side": order_side,
            "position_side": core.position.side,
            "current_price": current_price,
            "entry_price": core.position.entry_price,
            "metadata": exit_signal.metadata,
        }

        self.event_source.emit(
            "exit_signal",
            now,
            exit_payload,
            source="runtime",
        )

        self.audit.log("live_exit_signal", exit_payload)

        logger.info(
            "Exit signal: reason=%s side=%s qty=%.6f price=%.2f",
            exit_signal.reason,
            order_side,
            close_qty,
            current_price,
        )

        # Submit via exchange adapter (reduce-only market order)
        result = self.adapter.submit_order(order)

        if result.ok:
            response = result.payload if isinstance(result.payload, dict) else {}
            exchange_order_id = response.get("id")
            submit_result = {
                "status": "exit_submitted",
                "reason": exit_signal.reason,
                "is_partial": exit_signal.is_partial,
                "close_quantity": close_qty,
                "exchange_order_id": exchange_order_id,
                "response": response,
            }
            self.event_source.emit(
                "exit_order_submitted",
                now,
                {**exit_payload, "exchange_order_id": exchange_order_id},
                source="runtime",
            )
            self.audit.log("live_exit_submitted", submit_result)
            logger.info(
                "Exit order submitted: exchange_id=%s reason=%s",
                exchange_order_id,
                exit_signal.reason,
            )
        else:
            submit_result = {
                "status": "exit_failed",
                "reason": exit_signal.reason,
                "error": result.error,
            }
            self.event_source.emit(
                "exit_order_failed",
                now,
                {**exit_payload, "error": result.error},
                source="runtime",
            )
            self.alerts.emit(
                "exit_order_failed",
                {
                    "timestamp": now,
                    "reason": exit_signal.reason,
                    "error": result.error,
                },
                severity="critical",
            )
            self.audit.log("live_exit_failed", submit_result)
            logger.error(
                "Exit order FAILED: reason=%s error=%s",
                exit_signal.reason,
                result.error,
            )

        return submit_result
