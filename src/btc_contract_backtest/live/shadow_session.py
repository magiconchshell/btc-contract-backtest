from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Optional

import ccxt
import pandas as pd

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, ExecutionConfig, LiveRiskConfig, RiskConfig
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.shadow_recovery import ShadowRecovery
from btc_contract_backtest.runtime.runtime_state_store import JsonRuntimeStateStore
from btc_contract_backtest.runtime.trading_runtime import TradingRuntime
from btc_contract_backtest.strategies.base import BaseStrategy


class ShadowTradingSession(TradingRuntime):
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
        state_file: str = "shadow_state.json",
    ):
        super().__init__(contract, account, risk, strategy, timeframe, execution, live_risk, persistence=JsonRuntimeStateStore(state_file))
        self.exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})
        self.adapter = ExchangeExecutionAdapter(self.exchange, contract.symbol, max_retries=self.context.live_risk.max_consecutive_failures)
        self.audit = AuditLogger(audit_log)
        self.recovery = ShadowRecovery(state_file)
        self.state = self.recovery.load()
        self._restore_state()

    def _restore_state(self):
        self.watchdog.state.last_heartbeat_at = self.state.get("last_heartbeat_at")
        self.watchdog.state.consecutive_failures = self.state.get("consecutive_failures", 0)
        self.watchdog.state.halted = self.state.get("halted", False)
        self.watchdog.state.halt_reason = self.state.get("halt_reason")
        self.core.risk_events = self.state.get("risk_events", [])

    def save_state(self, last_payload: dict | None = None):
        payload = {
            "last_heartbeat_at": self.watchdog.state.last_heartbeat_at,
            "consecutive_failures": self.watchdog.state.consecutive_failures,
            "halted": self.watchdog.state.halted,
            "halt_reason": self.watchdog.state.halt_reason,
            "last_payload": last_payload,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.persist_runtime_state(**payload)

    def fetch_recent_data(self, limit: int = 300):
        rows = self.exchange.fetch_ohlcv(self.context.contract.symbol, timeframe=self.context.timeframe, limit=limit)
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df

    def enrich_snapshot(self, signal_df: pd.DataFrame, latest):
        snapshot = super().enrich_snapshot(signal_df, latest)
        ticker = self.exchange.fetch_ticker(self.context.contract.symbol)
        snapshot.mark_price = float(ticker.get("last") or snapshot.close)
        if ticker.get("bid") is not None:
            snapshot.bid = float(ticker["bid"])
        if ticker.get("ask") is not None:
            snapshot.ask = float(ticker["ask"])
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        bar_ms = int(signal_df.index[-1].timestamp() * 1000)
        snapshot.stale = (now_ms - bar_ms) > (self.context.risk.stale_data_threshold_seconds * 1000)
        return snapshot

    def reconcile(self):
        result = self.adapter.reconcile_state(self.core.position.side, 0)
        self.audit.log("reconcile", {"timestamp": self.now_iso(), "result": result.payload if result.ok else {"error": result.error}})
        return result

    def on_blocked_snapshot(self, payload: dict):
        payload["risk_events"] = self.core.risk_events[-3:]
        self.audit.log("shadow_blocked", payload)
        self.save_state(payload)
        return payload

    def on_hold(self, payload: dict):
        self.audit.log("shadow_hold", payload)
        self.save_state(payload)
        return payload

    def on_decision(self, payload: dict):
        reconcile_result = self.reconcile()
        payload["local_position"] = {
            "side": self.core.position.side,
            "quantity": self.core.position.quantity,
            "entry_price": self.core.position.entry_price,
        }
        payload["reconcile"] = reconcile_result.payload if reconcile_result.ok else {"error": reconcile_result.error}
        self.audit.log("shadow_decision", payload)
        self.save_state(payload)
        return payload

    def run_loop(self, interval_seconds: int = 60, iterations: Optional[int] = None):
        count = 0
        while True:
            if self.watchdog.check_timeout():
                payload = {"timestamp": self.now_iso(), "event": "halted", "reason": "heartbeat_timeout"}
                self.audit.log("shadow_halt", payload)
                self.save_state(payload)
                print(json.dumps(payload, indent=2, default=str))
                break
            payload = self.step()
            print(json.dumps(payload, indent=2, default=str))
            count += 1
            if iterations is not None and count >= iterations:
                break
            time.sleep(interval_seconds)
