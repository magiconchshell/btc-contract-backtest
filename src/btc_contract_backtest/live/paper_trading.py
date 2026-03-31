from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from btc_contract_backtest.config.models import (
    AccountConfig,
    ContractSpec,
    ExecutionConfig,
    LiveRiskConfig,
    RiskConfig,
)
from btc_contract_backtest.engine.execution_models import OrderSide, OrderType
from btc_contract_backtest.live.binance_futures import (
    create_binance_futures_exchange,
    require_binance_profile_enabled,
)
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.session_recovery import SessionRecovery
from btc_contract_backtest.runtime.calibration_engine import sample_from_execution
from btc_contract_backtest.runtime.calibration_store import CalibrationSampleStore
from btc_contract_backtest.runtime.order_state_bridge import (
    apply_local_submit,
    apply_remote_status,
    canonical_record_from_order,
)
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
        execution: Optional[ExecutionConfig] = None,
        live_risk: Optional[LiveRiskConfig] = None,
        allow_mainnet: bool = False,
        exchange: Optional[Any] = None,
    ):
        require_binance_profile_enabled(
            contract.exchange_profile, allow_mainnet=allow_mainnet
        )
        super().__init__(
            contract,
            account,
            risk,
            strategy,
            timeframe,
            execution,
            live_risk,
            persistence=JsonRuntimeStateStore(
                state_file,
                mode="paper",
                symbol=contract.symbol,
                leverage=contract.leverage,
            ),
        )
        self.state_path = Path(state_file)
        self.exchange = exchange or create_binance_futures_exchange(
            contract.exchange_profile,
            allow_mainnet=allow_mainnet,
        )
        self.adapter = ExchangeExecutionAdapter(
            self.exchange,
            contract.symbol,
            max_retries=self.context.live_risk.max_consecutive_failures,
        )
        self.recovery = SessionRecovery(str(self.state_path))
        self.calibration_store = CalibrationSampleStore()
        self.state = self._load()
        self._restore_core_from_state()
        if self.context.live_risk.reconcile_on_startup:
            self.reconcile_with_exchange()

    def _load(self):
        loader = getattr(self.persistence, "load_normalized_state", None)
        if callable(loader):
            return loader()
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
        self.core.capital = self.state.get(
            "capital", self.context.account.initial_capital
        )
        if self.core.capital is None:
            self.core.capital = self.context.account.initial_capital
        pos = self.state.get("position")
        if pos:
            for key, value in pos.items():
                setattr(self.core.position, key, value)
        self.core.orders = self.recovery.restore_orders(self.state)
        duplicates = self.recovery.dedupe_client_order_ids(self.core.orders)
        if duplicates:
            self.core.emit_risk_event(
                "duplicate_client_order_id",
                "Duplicate client order ids found during recovery",
                severity="critical",
                metadata={"duplicates": duplicates},
            )
        self.core.trades = self.state.get("trades", [])
        self.core.risk_events = self.state.get("risk_events", [])
        wd = self.state.get("watchdog") or {}
        self.watchdog.state.last_heartbeat_at = wd.get("last_heartbeat_at")
        self.watchdog.state.consecutive_failures = wd.get("consecutive_failures", 0)
        self.watchdog.state.halted = wd.get("halted", False)
        self.watchdog.state.halt_reason = wd.get("halt_reason")

    def reconcile_with_exchange(self):
        open_order_count = len(
            [
                o
                for o in self.core.orders.values()
                if getattr(o, "status", None) not in (None,)
                and str(o.status)
                not in {
                    "OrderStatus.CANCELED",
                    "OrderStatus.FILLED",
                    "OrderStatus.REJECTED",
                    "OrderStatus.EXPIRED",
                }
            ]
        )
        result = self.adapter.reconcile_state(
            self.core.position.side,
            open_order_count,
        )
        if result.ok and result.payload and not result.payload.get("ok", True):
            self.core.emit_risk_event(
                "reconcile_mismatch",
                "Exchange reconciliation detected differences",
                severity="critical",
                metadata=result.payload,
            )
        elif not result.ok:
            self.core.emit_risk_event(
                "reconcile_failed",
                result.error or "Unknown reconcile failure",
                severity="warning",
            )

    def save(self):
        store = self.state_store()
        if hasattr(store, "set_mode"):
            store.set_mode("paper")
            store.set_capital(self.core.capital)
            store.set_position(
                {
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
                }
                if self.core.position.side != 0
                else None
            )
            store.set_orders([vars(o) for o in self.core.orders.values()])
            store.set_trades(self.core.trades)
            store.set_governance_state({})
            store.set_last_runtime_snapshot(
                store.get_state().get("last_runtime_snapshot", {})
            )
            store.set_watchdog(
                {
                    "last_heartbeat_at": self.watchdog.state.last_heartbeat_at,
                    "consecutive_failures": self.watchdog.state.consecutive_failures,
                    "halted": self.watchdog.state.halted,
                    "halt_reason": self.watchdog.state.halt_reason,
                }
            )
            store.set_state_fields(updated_at=datetime.now(timezone.utc).isoformat())
            store.flush()
            return
        self.persist_runtime_state(updated_at=datetime.now(timezone.utc).isoformat())

    def fetch_recent_data(self, limit: int = 300):
        rows = self.exchange.fetch_ohlcv(
            self.context.contract.symbol,
            timeframe=self.context.timeframe,
            limit=limit,
        )
        df = pd.DataFrame(
            rows, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
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
        snapshot.stale = (now_ms - bar_ms) > (
            self.context.risk.stale_data_threshold_seconds * 1000
        )
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
            order = self.core.create_order(
                OrderSide.BUY if signal == 1 else OrderSide.SELL,
                qty,
                OrderType.MARKET,
            )
            store = self.state_store()
            if hasattr(store, "upsert_order"):
                record = canonical_record_from_order(
                    order,
                    submission_mode="paper",
                )
                record = apply_local_submit(
                    record,
                    timestamp=order.created_at,
                    payload={"signal": signal, "quantity": qty},
                )
                store.upsert_order(record.to_dict())
            snapshot = type("Snapshot", (), payload["snapshot"])()
            fills = []
            for fill in self.core.try_fill_order(order, snapshot):
                self.core.apply_fill(fill)
                self.core.position.atr_at_entry = atr
                fills.append(vars(fill))
                if hasattr(store, "append_fill"):
                    store.append_fill(vars(fill))
                sample = sample_from_execution(
                    timestamp=fill.timestamp or payload["timestamp"],
                    symbol=self.context.contract.symbol,
                    mode="paper",
                    side=order.side.value,
                    order_type=order.order_type.value,
                    quantity=order.quantity,
                    notional=order.quantity * snapshot_close,
                    reference_price=snapshot_close,
                    executed_price=fill.fill_price,
                    fill_quantity=fill.fill_quantity,
                    spread_bps=(
                        abs(
                            (payload["snapshot"].get("ask") or snapshot_close)
                            - (payload["snapshot"].get("bid") or snapshot_close)
                        )
                        / snapshot_close
                        * 10000
                        if snapshot_close > 0
                        else None
                    ),
                    depth_notional=self.context.execution.simulated_depth_notional,
                    queue_model=self.context.execution.queue_priority_model,
                    funding_rate=payload["snapshot"].get("funding_rate"),
                    funding_cost=None,
                    volatility_bucket="normal",
                    latency_ms=self.context.execution.latency_ms,
                    stale=payload["snapshot"].get("stale", False),
                    metadata={"calibration_version": "t4-v1"},
                )
                self.calibration_store.append(sample)
                if hasattr(store, "upsert_order"):
                    record = canonical_record_from_order(
                        order,
                        submission_mode="paper",
                    )
                    remote_status = (
                        order.status.value
                        if hasattr(order.status, "value")
                        else str(order.status)
                    )
                    record = apply_remote_status(
                        record,
                        status=remote_status,
                        timestamp=fill.timestamp,
                        payload=vars(fill),
                        filled_quantity=order.filled_quantity,
                        avg_fill_price=order.avg_fill_price,
                        exchange_order_id=order.exchange_order_id,
                    )
                    store.upsert_order(record.to_dict())
            self.save()
            return {"event": "open", "fills": fills, "summary": self.summary()}

        self.save()
        return payload

    def summary(self):
        current = self.mark_price()
        unrealized = 0.0
        if self.core.position.side != 0 and self.core.position.entry_price is not None:
            unrealized = (
                (
                    (current - self.core.position.entry_price)
                    / self.core.position.entry_price
                )
                * self.core.position.notional
                * self.core.position.leverage
                * self.core.position.side
            )
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
