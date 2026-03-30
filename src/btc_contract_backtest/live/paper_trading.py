from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import ccxt
import pandas as pd

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, ExecutionConfig, LiveRiskConfig, RiskConfig
from btc_contract_backtest.engine.execution_models import OrderSide, OrderType
from btc_contract_backtest.engine.simulator_core import SimulatorCore
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.session_recovery import SessionRecovery
from btc_contract_backtest.live.watchdog import HeartbeatWatchdog
from btc_contract_backtest.strategies.base import BaseStrategy


class PaperTradingSession:
    def __init__(
        self,
        contract: ContractSpec,
        account: AccountConfig,
        risk: RiskConfig,
        strategy: BaseStrategy,
        timeframe: str = "1h",
        state_file: str = "paper_state.json",
        execution: ExecutionConfig | None = None,
        live_risk: LiveRiskConfig | None = None,
    ):
        self.contract = contract
        self.account = account
        self.risk = risk
        self.strategy = strategy
        self.timeframe = timeframe
        self.execution = execution or ExecutionConfig()
        self.live_risk = live_risk or LiveRiskConfig()
        self.state_path = Path(state_file)
        self.exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})
        self.adapter = ExchangeExecutionAdapter(self.exchange, contract.symbol, max_retries=self.live_risk.max_consecutive_failures)
        self.watchdog = HeartbeatWatchdog(self.live_risk.heartbeat_timeout_seconds, self.live_risk.max_consecutive_failures)
        self.core = SimulatorCore(contract, account, risk, self.execution, self.live_risk)
        self.recovery = SessionRecovery(str(self.state_path))
        self.state = self._load()
        self._restore_core_from_state()
        if self.live_risk.reconcile_on_startup:
            self.reconcile_with_exchange()

    def _load(self):
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {
            "capital": self.account.initial_capital,
            "position": None,
            "orders": [],
            "trades": [],
            "risk_events": [],
            "watchdog": None,
            "updated_at": None,
        }

    def _restore_core_from_state(self):
        self.core.capital = self.state.get("capital", self.account.initial_capital)
        pos = self.state.get("position")
        if pos:
            for key, value in pos.items():
                setattr(self.core.position, key, value)
        self.core.orders = self.recovery.restore_orders(self.state)
        duplicates = self.recovery.dedupe_client_order_ids(self.core.orders)
        if duplicates:
            self.core.emit_risk_event("duplicate_client_order_id", "Duplicate client order ids found during recovery", severity="critical", metadata={"duplicates": duplicates})
        self.core.trades = self.state.get("trades", [])
        self.core.risk_events = self.state.get("risk_events", [])
        wd = self.state.get("watchdog") or {}
        self.watchdog.state.last_heartbeat_at = wd.get("last_heartbeat_at")
        self.watchdog.state.consecutive_failures = wd.get("consecutive_failures", 0)
        self.watchdog.state.halted = wd.get("halted", False)
        self.watchdog.state.halt_reason = wd.get("halt_reason")

    def reconcile_with_exchange(self):
        result = self.adapter.reconcile_state(self.core.position.side, len([o for o in self.core.orders.values() if getattr(o, "status", None) not in (None,) and str(o.status) not in {"OrderStatus.CANCELED", "OrderStatus.FILLED", "OrderStatus.REJECTED", "OrderStatus.EXPIRED"}]))
        if result.ok and result.payload and not result.payload.get("ok", True):
            self.core.emit_risk_event("reconcile_mismatch", "Exchange reconciliation detected differences", severity="critical", metadata=result.payload)
        elif not result.ok:
            self.core.emit_risk_event("reconcile_failed", result.error or "Unknown reconcile failure", severity="warning")

    def save(self):
        self.state["capital"] = self.core.capital
        self.state["position"] = {
            "symbol": self.core.position.symbol,
            "side": self.core.position.side,
            "quantity": self.core.position.quantity,
            "entry_price": self.core.position.entry_price,
            "entry_time": self.core.position.entry_time,
            "notional": self.core.position.notional,
            "leverage": self.core.position.leverage,
            "margin_used": self.core.position.margin_used,
            "bars_held": self.core.position.bars_held,
            "peak_price": self.core.position.peak_price,
            "trough_price": self.core.position.trough_price,
            "atr_at_entry": self.core.position.atr_at_entry,
            "break_even_armed": self.core.position.break_even_armed,
            "partial_taken": self.core.position.partial_taken,
            "stepped_stop_anchor": self.core.position.stepped_stop_anchor,
        } if self.core.position.side != 0 else None
        self.state["orders"] = [vars(o) for o in self.core.orders.values()]
        self.state["trades"] = self.core.trades
        self.state["risk_events"] = self.core.risk_events
        self.state["watchdog"] = {
            "last_heartbeat_at": self.watchdog.state.last_heartbeat_at,
            "consecutive_failures": self.watchdog.state.consecutive_failures,
            "halted": self.watchdog.state.halted,
            "halt_reason": self.watchdog.state.halt_reason,
        }
        self.state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.state_path.write_text(json.dumps(self.state, indent=2, default=str))

    def fetch_recent_data(self, limit: int = 300):
        rows = self.exchange.fetch_ohlcv(self.contract.symbol, timeframe=self.timeframe, limit=limit)
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df

    def mark_price(self) -> float:
        ticker = self.exchange.fetch_ticker(self.contract.symbol)
        return float(ticker["last"])

    def _latest_snapshot(self, df: pd.DataFrame):
        latest = df.iloc[-1]
        snapshot = self.core.snapshot_from_bar(df.index[-1], latest)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        bar_ms = int(df.index[-1].timestamp() * 1000)
        snapshot.stale = (now_ms - bar_ms) > (self.risk.stale_data_threshold_seconds * 1000)
        return latest, snapshot

    def step(self):
        if self.watchdog.state.halted:
            self.save()
            return {"event": "halted", "reason": self.watchdog.state.halt_reason, "summary": self.summary()}

        df = self.fetch_recent_data()
        signal_df = self.strategy.generate_signals(df)
        latest, snapshot = self._latest_snapshot(signal_df)
        signal = int(latest.get("signal", 0))
        atr = None if pd.isna(latest.get("atr")) else float(latest.get("atr"))

        self.watchdog.beat()

        if not self.core.check_snapshot_safety(snapshot):
            self.save()
            return {"event": "blocked", "reason": "stale_data", "summary": self.summary()}

        if self.core.position.side != 0:
            self.core.position.bars_held += 1
            self.core.position.peak_price = snapshot.close if self.core.position.peak_price is None else max(self.core.position.peak_price, snapshot.close)
            self.core.position.trough_price = snapshot.close if self.core.position.trough_price is None else min(self.core.position.trough_price, snapshot.close)
            self.core.apply_periodic_funding(snapshot)
            pnl_pct = ((snapshot.close - self.core.position.entry_price) / self.core.position.entry_price) * self.core.position.side if self.core.position.entry_price else 0.0
            should_close = None

            if self.risk.partial_take_profit_pct is not None and not self.core.position.partial_taken and pnl_pct >= self.risk.partial_take_profit_pct:
                qty = abs(self.core.position.quantity) * self.risk.partial_close_ratio
                order = self.core.create_order(OrderSide.SELL if self.core.position.side == 1 else OrderSide.BUY, qty, OrderType.MARKET, reduce_only=True)
                for fill in self.core.try_fill_order(order, snapshot):
                    self.core.apply_fill(fill)
                self.core.position.partial_taken = True
                self.save()
                return {"event": "partial_close", "summary": self.summary()}

            if self.risk.break_even_trigger_pct is not None and pnl_pct >= self.risk.break_even_trigger_pct:
                self.core.position.break_even_armed = True
            if self.risk.atr_stop_mult is not None and self.core.position.atr_at_entry is not None:
                if self.core.position.side == 1 and snapshot.close <= self.core.position.entry_price - (self.core.position.atr_at_entry * self.risk.atr_stop_mult):
                    should_close = "atr_stop"
                if self.core.position.side == -1 and snapshot.close >= self.core.position.entry_price + (self.core.position.atr_at_entry * self.risk.atr_stop_mult):
                    should_close = "atr_stop"
            if self.core.position.break_even_armed and should_close is None:
                if self.core.position.side == 1 and snapshot.close <= self.core.position.entry_price:
                    should_close = "break_even_stop"
                if self.core.position.side == -1 and snapshot.close >= self.core.position.entry_price:
                    should_close = "break_even_stop"
            if self.risk.stepped_trailing_stop_pct is not None and should_close is None:
                if self.core.position.side == 1:
                    anchor = self.core.position.peak_price if self.core.position.stepped_stop_anchor is None else max(self.core.position.stepped_stop_anchor, self.core.position.peak_price)
                    self.core.position.stepped_stop_anchor = anchor
                    if snapshot.close <= anchor * (1 - self.risk.stepped_trailing_stop_pct):
                        should_close = "stepped_trailing_stop"
                if self.core.position.side == -1:
                    anchor = self.core.position.trough_price if self.core.position.stepped_stop_anchor is None else min(self.core.position.stepped_stop_anchor, self.core.position.trough_price)
                    self.core.position.stepped_stop_anchor = anchor
                    if snapshot.close >= anchor * (1 + self.risk.stepped_trailing_stop_pct):
                        should_close = "stepped_trailing_stop"
            if self.risk.stop_loss_pct is not None and should_close is None and pnl_pct <= -self.risk.stop_loss_pct:
                should_close = "stop_loss"
            if self.risk.take_profit_pct is not None and should_close is None and pnl_pct >= self.risk.take_profit_pct:
                should_close = "take_profit"
            if self.risk.trailing_stop_pct is not None and should_close is None:
                if self.core.position.side == 1 and snapshot.close <= self.core.position.peak_price * (1 - self.risk.trailing_stop_pct):
                    should_close = "trailing_stop"
                if self.core.position.side == -1 and snapshot.close >= self.core.position.trough_price * (1 + self.risk.trailing_stop_pct):
                    should_close = "trailing_stop"
            if self.risk.max_holding_bars is not None and should_close is None and self.core.position.bars_held >= self.risk.max_holding_bars:
                should_close = "time_exit"
            if signal == 0 and should_close is None:
                should_close = "flat_signal"
            if signal != 0 and signal != self.core.position.side and should_close is None:
                should_close = "reverse_signal"

            if should_close is not None:
                order = self.core.create_order(OrderSide.SELL if self.core.position.side == 1 else OrderSide.BUY, abs(self.core.position.quantity), OrderType.MARKET, reduce_only=True)
                for fill in self.core.try_fill_order(order, snapshot):
                    self.core.apply_fill(fill)
                if self.core.trades:
                    self.core.trades[-1]["reason"] = should_close
                if should_close == "reverse_signal" and signal != 0:
                    notional = self.core.determine_notional(snapshot.close, atr)
                    qty = 0.0 if snapshot.close <= 0 else notional / snapshot.close
                    open_order = self.core.create_order(OrderSide.BUY if signal == 1 else OrderSide.SELL, qty, OrderType.MARKET)
                    for fill in self.core.try_fill_order(open_order, snapshot):
                        self.core.apply_fill(fill)
                        self.core.position.atr_at_entry = atr
                    self.save()
                    return {"event": "reverse", "summary": self.summary()}
                self.save()
                return {"event": "close", "reason": should_close, "summary": self.summary()}

        if self.core.check_daily_loss_kill(self.core.capital):
            self.watchdog.record_failure("daily_loss_kill")
            self.save()
            return {"event": "kill_switch", "summary": self.summary()}

        if self.core.position.side == 0 and signal != 0:
            notional = self.core.determine_notional(snapshot.close, atr)
            qty = 0.0 if snapshot.close <= 0 else notional / snapshot.close
            order = self.core.create_order(OrderSide.BUY if signal == 1 else OrderSide.SELL, qty, OrderType.MARKET)
            for fill in self.core.try_fill_order(order, snapshot):
                self.core.apply_fill(fill)
                self.core.position.atr_at_entry = atr
            self.save()
            return {"event": "open", "summary": self.summary()}

        self.save()
        return {"event": "hold", "summary": self.summary()}

    def summary(self):
        current = self.mark_price()
        unrealized = 0.0
        if self.core.position.side != 0 and self.core.position.entry_price is not None:
            unrealized = ((current - self.core.position.entry_price) / self.core.position.entry_price) * self.core.position.notional * self.core.position.leverage * self.core.position.side
        return {
            "symbol": self.contract.symbol,
            "market_type": self.contract.market_type,
            "timeframe": self.timeframe,
            "capital": self.core.capital,
            "position_side": self.core.position.side,
            "position_qty": self.core.position.quantity,
            "trades": len(self.core.trades),
            "mark_price": current,
            "unrealized_pnl": unrealized,
            "risk_events": len(self.core.risk_events),
            "watchdog_halted": self.watchdog.state.halted,
        }

    def run_loop(self, interval_seconds: int = 60, iterations: Optional[int] = None):
        count = 0
        while True:
            if self.watchdog.check_timeout():
                self.save()
                print(json.dumps({"event": "halted", "reason": "heartbeat_timeout", "summary": self.summary()}, indent=2, default=str))
                break
            event = self.step()
            print(json.dumps(event, indent=2, default=str))
            count += 1
            if iterations is not None and count >= iterations:
                break
            time.sleep(interval_seconds)
