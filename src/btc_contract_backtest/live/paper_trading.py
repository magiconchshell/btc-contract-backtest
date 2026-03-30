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
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.session_recovery import SessionRecovery
from btc_contract_backtest.runtime.runtime_state_store import JsonRuntimeStateStore
from btc_contract_backtest.runtime.trading_runtime import TradingRuntime
from btc_contract_backtest.strategies.base import BaseStrategy


class PaperTradingSession(TradingRuntime):
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
        super().__init__(contract, account, risk, strategy, timeframe, execution, live_risk, persistence=JsonRuntimeStateStore(state_file))
        self.state_path = Path(state_file)
        self.exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})
        self.adapter = ExchangeExecutionAdapter(self.exchange, contract.symbol, max_retries=self.context.live_risk.max_consecutive_failures)
        self.recovery = SessionRecovery(str(self.state_path))
        self.state = self._load()
        self._restore_core_from_state()
        if self.context.live_risk.reconcile_on_startup:
            self.reconcile_with_exchange()

    def _load(self):
        loaded = self.recovery.load_state()
        if loaded:
            return loaded
        return {
            "capital": self.context.account.initial_capital,
            "position": None,
            "orders": [],
            "trades": [],
            "risk_events": [],
            "watchdog": None,
            "updated_at": None,
        }

    def _restore_core_from_state(self):
        self.core.capital = self.state.get("capital", self.context.account.initial_capital)
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
        self.persist_runtime_state(
            capital=self.core.capital,
            position={
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
            } if self.core.position.side != 0 else None,
            orders=[vars(o) for o in self.core.orders.values()],
            trades=self.core.trades,
            risk_events=self.core.risk_events,
            watchdog={
                "last_heartbeat_at": self.watchdog.state.last_heartbeat_at,
                "consecutive_failures": self.watchdog.state.consecutive_failures,
                "halted": self.watchdog.state.halted,
                "halt_reason": self.watchdog.state.halt_reason,
            },
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def fetch_recent_data(self, limit: int = 300):
        rows = self.exchange.fetch_ohlcv(self.context.contract.symbol, timeframe=self.context.timeframe, limit=limit)
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df

    def mark_price(self) -> float:
        ticker = self.exchange.fetch_ticker(self.context.contract.symbol)
        return float(ticker["last"])

    def enrich_snapshot(self, signal_df: pd.DataFrame, latest):
        snapshot = super().enrich_snapshot(signal_df, latest)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        bar_ms = int(signal_df.index[-1].timestamp() * 1000)
        snapshot.stale = (now_ms - bar_ms) > (self.context.risk.stale_data_threshold_seconds * 1000)
        return snapshot

    def on_blocked_snapshot(self, payload: dict):
        self.save()
        return payload

    def on_hold(self, payload: dict):
        self.save()
        return payload

    def on_decision(self, payload: dict):
        signal = payload["signal"]
        snapshot_close = float(payload["snapshot"]["close"])
        atr = None
        if self.core.check_daily_loss_kill(self.core.capital):
            self.watchdog.record_failure("daily_loss_kill")
            self.save()
            return {"event": "kill_switch", "summary": self.summary()}

        if self.core.position.side == 0 and signal != 0:
            intended = payload["intended_order"] or {}
            qty = float(intended.get("quantity", 0.0))
            order = self.core.create_order(OrderSide.BUY if signal == 1 else OrderSide.SELL, qty, OrderType.MARKET)
            snapshot = type("Snapshot", (), payload["snapshot"])()
            for fill in self.core.try_fill_order(order, snapshot):
                self.core.apply_fill(fill)
                self.core.position.atr_at_entry = atr
            self.save()
            return {"event": "open", "summary": self.summary()}

        self.save()
        return payload

    def summary(self):
        current = self.mark_price()
        unrealized = 0.0
        if self.core.position.side != 0 and self.core.position.entry_price is not None:
            unrealized = ((current - self.core.position.entry_price) / self.core.position.entry_price) * self.core.position.notional * self.core.position.leverage * self.core.position.side
        return {
            "symbol": self.context.contract.symbol,
            "market_type": self.context.contract.market_type,
            "timeframe": self.context.timeframe,
            "capital": self.core.capital,
            "position_side": self.core.position.side,
            "position_qty": self.core.position.quantity,
            "trades": len(self.core.trades),
            "mark_price": current,
            "unrealized_pnl": unrealized,
            "risk_events": len(self.core.risk_events),
        }

    def run_loop(self, interval_seconds: int = 60, iterations: Optional[int] = None):
        count = 0
        while True:
            payload = self.step()
            print(json.dumps(payload, indent=2, default=str))
            count += 1
            if iterations is not None and count >= iterations:
                break
            time.sleep(interval_seconds)
