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
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.watchdog import HeartbeatWatchdog
from btc_contract_backtest.strategies.base import BaseStrategy


class ShadowTradingSession:
    def __init__(
        self,
        contract: ContractSpec,
        account: AccountConfig,
        risk: RiskConfig,
        strategy: BaseStrategy,
        timeframe: str = "1h",
        execution: ExecutionConfig | None = None,
        live_risk: LiveRiskConfig | None = None,
        audit_log: str = "shadow_audit.jsonl",
    ):
        self.contract = contract
        self.account = account
        self.risk = risk
        self.strategy = strategy
        self.timeframe = timeframe
        self.execution = execution or ExecutionConfig()
        self.live_risk = live_risk or LiveRiskConfig()
        self.exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})
        self.adapter = ExchangeExecutionAdapter(self.exchange, contract.symbol, max_retries=self.live_risk.max_consecutive_failures)
        self.watchdog = HeartbeatWatchdog(self.live_risk.heartbeat_timeout_seconds, self.live_risk.max_consecutive_failures)
        self.core = SimulatorCore(contract, account, risk, self.execution, self.live_risk)
        self.audit = AuditLogger(audit_log)

    def fetch_recent_data(self, limit: int = 300):
        rows = self.exchange.fetch_ohlcv(self.contract.symbol, timeframe=self.timeframe, limit=limit)
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df

    def latest_snapshot(self, signal_df: pd.DataFrame):
        latest = signal_df.iloc[-1]
        snapshot = self.core.snapshot_from_bar(signal_df.index[-1], latest)
        ticker = self.exchange.fetch_ticker(self.contract.symbol)
        snapshot.mark_price = float(ticker.get("last") or snapshot.close)
        if ticker.get("bid") is not None:
            snapshot.bid = float(ticker["bid"])
        if ticker.get("ask") is not None:
            snapshot.ask = float(ticker["ask"])
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        bar_ms = int(signal_df.index[-1].timestamp() * 1000)
        snapshot.stale = (now_ms - bar_ms) > (self.risk.stale_data_threshold_seconds * 1000)
        return latest, snapshot

    def intended_order_payload(self, signal: int, snapshot, atr: Optional[float]):
        if signal == 0:
            return None
        notional = self.core.determine_notional(snapshot.close, atr)
        qty = 0.0 if snapshot.close <= 0 else notional / snapshot.close
        return {
            "symbol": self.contract.symbol,
            "side": "buy" if signal == 1 else "sell",
            "order_type": OrderType.MARKET.value,
            "quantity": qty,
            "notional": notional,
            "price_reference": snapshot.close,
        }

    def reconcile(self):
        result = self.adapter.reconcile_state(self.core.position.side, 0)
        self.audit.log("reconcile", {"timestamp": datetime.now(timezone.utc).isoformat(), "result": result.payload if result.ok else {"error": result.error}})
        return result

    def step(self):
        if self.watchdog.state.halted:
            payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": "halted", "reason": self.watchdog.state.halt_reason}
            self.audit.log("shadow_halt", payload)
            return payload

        self.watchdog.beat()
        df = self.fetch_recent_data()
        signal_df = self.strategy.generate_signals(df)
        latest, snapshot = self.latest_snapshot(signal_df)

        if not self.core.check_snapshot_safety(snapshot):
            payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": "blocked", "reason": "snapshot_safety_failed", "risk_events": self.core.risk_events[-3:]}
            self.audit.log("shadow_blocked", payload)
            return payload

        signal = int(latest.get("signal", 0))
        atr = None if pd.isna(latest.get("atr")) else float(latest.get("atr"))
        intended = self.intended_order_payload(signal, snapshot, atr)
        reconcile_result = self.reconcile()

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signal": signal,
            "snapshot": {
                "close": snapshot.close,
                "bid": snapshot.bid,
                "ask": snapshot.ask,
                "mark_price": snapshot.mark_price,
                "stale": snapshot.stale,
            },
            "intended_order": intended,
            "local_position": {
                "side": self.core.position.side,
                "quantity": self.core.position.quantity,
                "entry_price": self.core.position.entry_price,
            },
            "reconcile": reconcile_result.payload if reconcile_result.ok else {"error": reconcile_result.error},
        }
        self.audit.log("shadow_decision", payload)
        return payload

    def run_loop(self, interval_seconds: int = 60, iterations: Optional[int] = None):
        count = 0
        while True:
            if self.watchdog.check_timeout():
                payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": "halted", "reason": "heartbeat_timeout"}
                self.audit.log("shadow_halt", payload)
                print(json.dumps(payload, indent=2, default=str))
                break
            payload = self.step()
            print(json.dumps(payload, indent=2, default=str))
            count += 1
            if iterations is not None and count >= iterations:
                break
            time.sleep(interval_seconds)
