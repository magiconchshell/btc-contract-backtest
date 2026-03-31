from __future__ import annotations
from typing import Optional

from dataclasses import asdict

import pandas as pd

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, ExecutionConfig, LiveRiskConfig, RiskConfig
from btc_contract_backtest.engine.execution_models import OrderSide, OrderType
from btc_contract_backtest.runtime.calibration_engine import sample_from_execution
from btc_contract_backtest.runtime.calibration_store import CalibrationSampleStore
from btc_contract_backtest.runtime.trading_runtime import TradingRuntime
from btc_contract_backtest.strategies.base import BaseStrategy


class BacktestRuntime(TradingRuntime):
    def __init__(
        self,
        market_data: pd.DataFrame,
        contract: ContractSpec,
        account: AccountConfig,
        risk: RiskConfig,
        strategy: BaseStrategy,
        timeframe: str = "1h",
        execution: Optional[ExecutionConfig] = None,
        live_risk: Optional[LiveRiskConfig] = None,
    ):
        super().__init__(contract, account, risk, strategy, timeframe, execution, live_risk)
        self.market_data = market_data.copy()
        self.cursor = 0
        self.equity_curve: list[dict] = []
        self.liquidation_events = 0
        self.calibration_store = CalibrationSampleStore()

    def fetch_recent_data(self, limit: int = 300):
        end = min(self.cursor + 1, len(self.market_data))
        start = max(0, end - limit)
        frame = self.market_data.iloc[start:end].copy()
        if frame.empty:
            raise ValueError("No market data available for current cursor")
        return frame

    def current_row(self):
        if self.market_data.empty:
            raise ValueError("market_data is empty")
        idx = min(self.cursor, len(self.market_data) - 1)
        return self.market_data.iloc[idx]

    def current_timestamp(self):
        if self.market_data.empty:
            raise ValueError("market_data is empty")
        idx = min(self.cursor, len(self.market_data) - 1)
        return self.market_data.index[idx]

    def _current_equity(self, price: float) -> float:
        unrealized = 0.0
        if self.core.position.side != 0 and self.core.position.entry_price is not None and self.core.position.quantity != 0:
            unrealized = ((price - self.core.position.entry_price) / self.core.position.entry_price) * self.core.position.notional * self.context.contract.leverage * self.core.position.side
        return self.core.capital + unrealized

    def _record_equity(self, snapshot):
        self.equity_curve.append(
            {
                "timestamp": self.current_timestamp(),
                "equity": self._current_equity(snapshot.close),
                "close": snapshot.close,
                "position": self.core.position.side,
            }
        )

    def _update_open_position_state(self, snapshot):
        if self.core.position.side == 0:
            return
        self.core.position.bars_held += 1
        self.core.position.peak_price = snapshot.close if self.core.position.peak_price is None else max(self.core.position.peak_price, snapshot.close)
        self.core.position.trough_price = snapshot.close if self.core.position.trough_price is None else min(self.core.position.trough_price, snapshot.close)
        self.core.apply_periodic_funding(snapshot)

    def _check_liquidation(self, snapshot) -> bool:
        if self.core.position.side == 0 or self.core.position.entry_price is None or self.core.position.quantity == 0:
            return False
        unrealized = self._current_equity(snapshot.close) - self.core.capital
        maintenance = self.core.position.notional * self.context.risk.maintenance_margin_ratio
        if self.core.capital + unrealized > maintenance:
            return False
        self.core.emit_risk_event("liquidation", "Maintenance margin breached", severity="critical")
        self.core.trades.append(
            {
                "entry_time": self.core.position.entry_time,
                "exit_time": str(self.current_timestamp()),
                "entry_price": self.core.position.entry_price,
                "exit_price": snapshot.close,
                "position": self.core.position.side,
                "bars_held": self.core.position.bars_held,
                "notional_closed": self.core.position.notional,
                "remaining_notional": 0.0,
                "reason": "liquidation",
                "is_partial": False,
                "pnl_after_costs": -(self.core.position.margin_used),
            }
        )
        self.core.capital -= self.core.position.margin_used
        self.liquidation_events += 1
        self.core.position.quantity = 0.0
        self.core.position.side = 0
        self.core.position.entry_price = None
        self.core.position.notional = 0.0
        self.core.position.margin_used = 0.0
        return True

    def _maybe_close_position(self, snapshot) -> Optional[str]:
        if self.core.position.side == 0 or self.core.position.entry_price is None:
            return None
        price = snapshot.close
        pnl_pct = ((price - self.core.position.entry_price) / self.core.position.entry_price) * self.core.position.side
        should_close = None
        if self.context.risk.partial_take_profit_pct is not None and not self.core.position.partial_taken and pnl_pct >= self.context.risk.partial_take_profit_pct:
            close_qty = abs(self.core.position.quantity) * self.context.risk.partial_close_ratio
            order = self.core.create_order(OrderSide.SELL if self.core.position.side == 1 else OrderSide.BUY, close_qty, OrderType.MARKET, reduce_only=True)
            for fill in self.core.try_fill_order(order, snapshot):
                self.core.apply_fill(fill)
            self.core.position.partial_taken = True
        if self.context.risk.break_even_trigger_pct is not None and pnl_pct >= self.context.risk.break_even_trigger_pct:
            self.core.position.break_even_armed = True
        if self.context.risk.atr_stop_mult is not None and self.core.position.atr_at_entry is not None:
            if self.core.position.side == 1 and price <= self.core.position.entry_price - (self.core.position.atr_at_entry * self.context.risk.atr_stop_mult):
                should_close = "atr_stop"
            if self.core.position.side == -1 and price >= self.core.position.entry_price + (self.core.position.atr_at_entry * self.context.risk.atr_stop_mult):
                should_close = "atr_stop"
        if self.core.position.break_even_armed and should_close is None:
            if self.core.position.side == 1 and price <= self.core.position.entry_price:
                should_close = "break_even_stop"
            if self.core.position.side == -1 and price >= self.core.position.entry_price:
                should_close = "break_even_stop"
        if self.context.risk.stepped_trailing_stop_pct is not None and should_close is None:
            if self.core.position.side == 1:
                anchor = self.core.position.peak_price if self.core.position.stepped_stop_anchor is None else max(self.core.position.stepped_stop_anchor, self.core.position.peak_price)
                self.core.position.stepped_stop_anchor = anchor
                if price <= anchor * (1 - self.context.risk.stepped_trailing_stop_pct):
                    should_close = "stepped_trailing_stop"
            if self.core.position.side == -1:
                anchor = self.core.position.trough_price if self.core.position.stepped_stop_anchor is None else min(self.core.position.stepped_stop_anchor, self.core.position.trough_price)
                self.core.position.stepped_stop_anchor = anchor
                if price >= anchor * (1 + self.context.risk.stepped_trailing_stop_pct):
                    should_close = "stepped_trailing_stop"
        if self.context.risk.stop_loss_pct is not None and should_close is None and pnl_pct <= -self.context.risk.stop_loss_pct:
            should_close = "stop_loss"
        if self.context.risk.take_profit_pct is not None and should_close is None and pnl_pct >= self.context.risk.take_profit_pct:
            should_close = "take_profit"
        if self.context.risk.trailing_stop_pct is not None and should_close is None:
            if self.core.position.side == 1 and self.core.position.peak_price is not None and price <= self.core.position.peak_price * (1 - self.context.risk.trailing_stop_pct):
                should_close = "trailing_stop"
            if self.core.position.side == -1 and self.core.position.trough_price is not None and price >= self.core.position.trough_price * (1 + self.context.risk.trailing_stop_pct):
                should_close = "trailing_stop"
        if self.context.risk.max_holding_bars is not None and should_close is None and self.core.position.bars_held >= self.context.risk.max_holding_bars:
            should_close = "time_exit"
        if should_close is not None:
            order = self.core.create_order(OrderSide.SELL if self.core.position.side == 1 else OrderSide.BUY, abs(self.core.position.quantity), OrderType.MARKET, reduce_only=True)
            for fill in self.core.try_fill_order(order, snapshot):
                self.core.apply_fill(fill)
            if self.core.trades:
                self.core.trades[-1]["reason"] = should_close
        return should_close

    def on_hold(self, payload: dict):
        snapshot = self.core.last_snapshot
        if snapshot is not None:
            self._update_open_position_state(snapshot)
            if self._check_liquidation(snapshot):
                self._record_equity(snapshot)
                payload["event"] = "liquidated"
                payload["reason"] = "maintenance_margin_breached"
                self.persist_payload(payload, {"stage": "hold_liquidation"})
                return payload
            close_reason = self._maybe_close_position(snapshot)
            if close_reason is not None:
                payload["close_reason"] = close_reason
            self._record_equity(snapshot)
        return payload

    def on_decision(self, payload: dict):
        snapshot = self.core.last_snapshot
        if snapshot is None:
            return payload
        self._update_open_position_state(snapshot)
        if self._check_liquidation(snapshot):
            liquidated = {
                "event": "liquidated",
                "timestamp": payload["timestamp"],
                "reason": "maintenance_margin_breached",
                "snapshot": payload.get("snapshot", {}),
            }
            self._record_equity(snapshot)
            self.persist_payload(liquidated, {"stage": "decision_liquidation"})
            return liquidated

        close_reason = self._maybe_close_position(snapshot)
        if close_reason is not None:
            payload["close_reason"] = close_reason

        if self.core.check_daily_loss_kill(self._current_equity(snapshot.close)):
            halted = {"event": "kill_switch", "timestamp": payload["timestamp"], "reason": "daily_loss_kill", "snapshot": payload.get("snapshot", {})}
            self._record_equity(snapshot)
            self.persist_payload(halted, {"stage": "daily_loss"})
            return halted

        signal = payload["signal"]
        intended = payload.get("intended_order") or {}
        qty = float(intended.get("quantity", 0.0))
        atr = self.current_row().get("atr")
        atr = None if pd.isna(atr) else float(atr)

        if self.core.position.side == 0 and signal != 0 and qty > 0:
            order = self.core.create_order(OrderSide.BUY if signal == 1 else OrderSide.SELL, qty, OrderType.MARKET)
            fills = []
            for fill in self.core.try_fill_order(order, snapshot):
                self.core.apply_fill(fill)
                self.core.position.atr_at_entry = atr
                fills.append(asdict(fill))
                self.calibration_store.append(sample_from_execution(
                    timestamp=fill.timestamp or payload["timestamp"],
                    symbol=self.context.contract.symbol,
                    mode="backtest",
                    side=order.side.value,
                    order_type=order.order_type.value,
                    quantity=order.quantity,
                    notional=order.quantity * snapshot.close,
                    reference_price=snapshot.close,
                    executed_price=fill.fill_price,
                    fill_quantity=fill.fill_quantity,
                    spread_bps=(abs((snapshot.ask or snapshot.close) - (snapshot.bid or snapshot.close)) / snapshot.close * 10000) if snapshot.close > 0 else None,
                    depth_notional=self.context.execution.simulated_depth_notional,
                    queue_model=self.context.execution.queue_priority_model,
                    funding_rate=snapshot.funding_rate,
                    funding_cost=None,
                    volatility_bucket="normal",
                    latency_ms=self.context.execution.latency_ms,
                    stale=snapshot.stale,
                    metadata={"calibration_version": "t4-v1"},
                ))
            payload["fills"] = fills
            payload["event"] = "open"
        elif self.core.position.side != 0 and signal != self.core.position.side and qty > 0:
            close_order = self.core.create_order(OrderSide.SELL if self.core.position.side == 1 else OrderSide.BUY, abs(self.core.position.quantity), OrderType.MARKET, reduce_only=True)
            close_fills = []
            for fill in self.core.try_fill_order(close_order, snapshot):
                self.core.apply_fill(fill)
                close_fills.append(asdict(fill))
            open_order = self.core.create_order(OrderSide.BUY if signal == 1 else OrderSide.SELL, qty, OrderType.MARKET)
            open_fills = []
            for fill in self.core.try_fill_order(open_order, snapshot):
                self.core.apply_fill(fill)
                self.core.position.atr_at_entry = atr
                open_fills.append(asdict(fill))
            if self.core.trades:
                self.core.trades[-1]["reason"] = "reverse_signal"
            payload["fills"] = {"close": close_fills, "open": open_fills}
            payload["event"] = "reverse"

        self._record_equity(snapshot)
        self.persist_payload(payload, {"stage": "execution", "cursor": self.cursor})
        return payload

    def run(self):
        if self.market_data.empty:
            return {
                "equity_curve": pd.DataFrame(),
                "trades": pd.DataFrame(self.core.trades),
                "initial_capital": self.context.account.initial_capital,
                "final_capital": self.core.capital,
                "liquidation_events": self.liquidation_events,
                "risk_events": pd.DataFrame(self.core.risk_events),
            }
        while True:
            self.step()
            if not self.advance():
                break
        return {
            "equity_curve": pd.DataFrame(self.equity_curve),
            "trades": pd.DataFrame(self.core.trades),
            "initial_capital": self.context.account.initial_capital,
            "final_capital": self.equity_curve[-1]["equity"] if self.equity_curve else self.core.capital,
            "liquidation_events": self.liquidation_events,
            "risk_events": pd.DataFrame(self.core.risk_events),
        }

    def advance(self):
        self.cursor += 1
        return self.cursor < len(self.market_data)
