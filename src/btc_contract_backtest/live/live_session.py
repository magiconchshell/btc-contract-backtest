from __future__ import annotations

import json
import logging
import signal
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from btc_contract_backtest.config.models import (
    AccountConfig,
    ContractSpec,
    ExecutionConfig,
    LiveRiskConfig,
    RiskConfig,
)
from btc_contract_backtest.engine.execution_models import (
    FillEvent,
    MarketSnapshot,
    OrderSide,
    OrderType,
)
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.binance_futures import (
    BinanceFuturesMetadataSync,
    build_binance_futures_runtime_paths,
    create_binance_futures_exchange,
    require_binance_profile_enabled,
    with_binance_symbol_rules,
)
from btc_contract_backtest.live.binance_futures_stream import (
    BinanceFuturesStreamConfig,
    BinanceFuturesUserDataEventSource,
)
from btc_contract_backtest.live.event_stream import (
    EventDrivenExecutionSource,
    EventRecorder,
)
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.governance import (
    AlertSink,
    GovernancePolicy,
    GovernanceState,
    OperatorApprovalQueue,
    TradingMode,
)
from btc_contract_backtest.live.ws_transport import websocket_transport_factory
from btc_contract_backtest.live.guarded_live import GuardedLiveExecutor
from btc_contract_backtest.live.incident_store import (
    IncidentRecord,
    IncidentStore,
)
from btc_contract_backtest.live.live_recovery import LiveSessionRecovery
from btc_contract_backtest.live.order_monitor import OrderLifecycleMonitor
from btc_contract_backtest.live.recovery_orchestrator import RecoveryOrchestrator
from btc_contract_backtest.live.submit_ledger import SubmitLedger
from btc_contract_backtest.runtime.calibration_engine import sample_from_execution
from btc_contract_backtest.runtime.calibration_store import CalibrationSampleStore
from btc_contract_backtest.runtime.order_state_bridge import (
    apply_local_submit,
    apply_remote_status,
    canonical_record_from_order,
    propagate_replace_chain,
)
from btc_contract_backtest.runtime.runtime_state_store import JsonRuntimeStateStore
from btc_contract_backtest.live.live_exit_manager import LiveExitManager
from btc_contract_backtest.live.log_config import configure_logging
from btc_contract_backtest.runtime.exit_logic import (
    ExitEvalContext,
    evaluate_exit,
    update_position_tracking,
)
from btc_contract_backtest.runtime.trading_runtime import TradingRuntime
from btc_contract_backtest.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class GovernedLiveSession(TradingRuntime):
    def __init__(
        self,
        contract: ContractSpec,
        account: AccountConfig,
        risk: RiskConfig,
        strategy: BaseStrategy,
        timeframe: str = "1h",
        execution: Optional[ExecutionConfig] = None,
        live_risk: Optional[LiveRiskConfig] = None,
        mode: TradingMode = TradingMode.APPROVAL_REQUIRED,
        audit_log: str = "live_governance_audit.jsonl",
        approval_file: str = "operator_approvals.json",
        governance_state_file: str = "governance_state.json",
        alerts_file: str = "live_alerts.jsonl",
        state_file: str = "live_session_state.json",
        metadata_cache_file: str = "var/binance_futures_exchange_info.json",
        allow_mainnet: bool = False,
        exchange: Optional[Any] = None,
    ):
        require_binance_profile_enabled(
            contract.exchange_profile, allow_mainnet=allow_mainnet
        )
        runtime_paths = build_binance_futures_runtime_paths(
            contract.exchange_profile, contract.symbol
        )
        metadata_cache_file = metadata_cache_file or runtime_paths.metadata_cache_file
        approval_file = approval_file or runtime_paths.approval_file
        governance_state_file = (
            governance_state_file or runtime_paths.governance_state_file
        )
        alerts_file = alerts_file or runtime_paths.alerts_file
        state_file = state_file or runtime_paths.live_state_file
        audit_log = audit_log or runtime_paths.live_audit_log
        metadata_sync = BinanceFuturesMetadataSync(
            profile=contract.exchange_profile,
            cache_path=metadata_cache_file,
        )
        try:
            symbol_rules = metadata_sync.get_symbol_rules(
                contract.symbol, allow_stale=True, refresh_on_miss=True
            )
            contract = with_binance_symbol_rules(contract, symbol_rules)
        except Exception:  # noqa: BLE001
            pass
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
                mode="governed_live",
                symbol=contract.symbol,
                leverage=contract.leverage,
            ),
        )
        self.exchange = exchange or create_binance_futures_exchange(
            contract.exchange_profile,
            allow_mainnet=allow_mainnet,
        )
        self.metadata_sync = metadata_sync
        self.adapter = ExchangeExecutionAdapter(
            self.exchange,
            contract.symbol,
            max_retries=self.context.live_risk.max_consecutive_failures,
        )
        self.adapter.configure_binance_futures_mode(
            use_testnet=bool(
                getattr(contract, "exchange_profile", "").endswith("testnet")
            )
        )
        self.audit = AuditLogger(audit_log)
        self.alerts = AlertSink(alerts_file)
        self.approvals = OperatorApprovalQueue(approval_file)
        self.gov_state = GovernanceState(governance_state_file)
        self.incidents = IncidentStore()
        self.recovery = LiveSessionRecovery(state_file)
        self.calibration_store = CalibrationSampleStore()
        loader = getattr(self.persistence, "load_normalized_state", None)
        recovered = loader() if callable(loader) else self.recovery.load()
        wd = recovered.get("watchdog") or {}
        self.watchdog.state.last_heartbeat_at = wd.get("last_heartbeat_at")
        self.watchdog.state.consecutive_failures = wd.get("consecutive_failures", 0)
        self.watchdog.state.halted = wd.get("halted", False)
        self.watchdog.state.halt_reason = wd.get("halt_reason")
        state = self.gov_state.load()
        current_mode = TradingMode(state.get("mode", mode.value))
        self.submit_ledger = SubmitLedger(runtime_paths.submit_ledger_file)
        self.exchange_events = BinanceFuturesUserDataEventSource(
            self.adapter,
            BinanceFuturesStreamConfig(
                symbol=contract.symbol,
                use_testnet=bool(
                    getattr(contract, "exchange_profile", "").endswith("testnet")
                ),
            ),
            transport_factory=websocket_transport_factory,
        )
        self.event_source = EventDrivenExecutionSource(
            EventRecorder(runtime_paths.execution_events_file),
            upstream=self.exchange_events,
        )
        replayed_events = self.event_source.replay()
        self.policy = GovernancePolicy(
            risk,
            self.context.live_risk,
            current_mode,
            contract=contract,
        )
        self.executor = GuardedLiveExecutor(
            self.adapter,
            self.policy,
            self.approvals,
            self.alerts,
            self.audit,
            submit_ledger=self.submit_ledger,
            event_source=self.event_source,
        )
        self.order_monitor = OrderLifecycleMonitor(
            self.adapter, self.alerts, self.audit
        )
        self.recovery_orchestrator = RecoveryOrchestrator(
            self.adapter, self.submit_ledger
        )
        self._recovery_report = self.recovery_orchestrator.recover(
            local_orders=recovered.get("orders", []),
            local_position=recovered.get("position", {}),
            events=replayed_events,
            event_boundary=self.event_source.boundary_state(),
            environment=(
                "testnet"
                if bool(getattr(contract, "exchange_profile", "").endswith("testnet"))
                else "mainnet"
            ),
        )

        # --- Phase 1 additions ---

        # Exit manager for position close/exit logic
        self.exit_manager = LiveExitManager(
            adapter=self.adapter,
            risk=risk,
            alerts=self.alerts,
            audit=self.audit,
            submit_ledger=self.submit_ledger,
            event_source=self.event_source,
        )

        # Sync position from exchange on startup
        self._sync_position_from_exchange()

        # Threading and shutdown state
        self._shutdown_event = threading.Event()
        self._ws_thread: Optional[threading.Thread] = None
        self._ws_lock = threading.Lock()
        self._pending_fills: list[dict[str, Any]] = []
        self._use_testnet = bool(
            getattr(contract, "exchange_profile", "").endswith("testnet")
        )

    def save_state(self, payload: Optional[dict] = None):
        store = self.state_store()
        if hasattr(store, "set_mode"):
            store.set_mode("governed_live")
            store.set_governance_state(self.gov_state.load())
            store.set_last_runtime_snapshot(payload or {})
            store.set_reconcile_report((payload or {}).get("reconcile_report") or {})
            store.set_submit_ledger(self.submit_ledger.load())
            recovery_report = (
                self._recovery_report.to_dict()
                if hasattr(self._recovery_report, "to_dict")
                else self._recovery_report
            )
            recovery_report_payload = (
                recovery_report if isinstance(recovery_report, dict) else {}
            )
            store.set_state_fields(
                recovery_report=recovery_report,
                startup_report=recovery_report_payload.get("startup_convergence") or {},
                execution_events=self.event_source.replay(),
                event_stream_boundary=self.event_source.boundary_state(),
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

    def enrich_snapshot(self, signal_df: pd.DataFrame, latest) -> MarketSnapshot:
        snapshot = super().enrich_snapshot(signal_df, latest)
        ticker = self.exchange.fetch_ticker(self.context.contract.symbol)
        snapshot.mark_price = float(ticker.get("last") or snapshot.close)
        snapshot.bid = float(ticker.get("bid") or snapshot.bid or snapshot.close)
        snapshot.ask = float(ticker.get("ask") or snapshot.ask or snapshot.close)
        return snapshot

    # ── Position sync from exchange ──────────────────────────────────

    def _sync_position_from_exchange(self) -> None:
        """Adopt exchange position truth into core.position.

        Called on startup (after recovery) and on reconciliation mismatch.
        This ensures core.position always reflects exchange reality.
        """
        result = self.adapter.fetch_positions()
        if not result.ok:
            logger.warning(
                "Position sync failed: %s", result.error
            )
            return

        remote_positions = (
            result.payload if isinstance(result.payload, list) else []
        )
        for pos in remote_positions:
            contracts = float(
                pos.get("contracts") or pos.get("positionAmt") or 0.0
            )
            if contracts != 0:
                self.core.position.side = 1 if contracts > 0 else -1
                self.core.position.quantity = abs(contracts)
                entry = pos.get("entryPrice") or pos.get("entry_price")
                if entry is not None:
                    self.core.position.entry_price = float(entry)
                self.core.position.symbol = self.context.contract.symbol
                self.core.position.leverage = self.context.contract.leverage
                self.core.position.notional = (
                    abs(contracts) * (self.core.position.entry_price or 0.0)
                )
                self.core.position.margin_used = (
                    self.core.position.notional / self.context.contract.leverage
                    if self.context.contract.leverage > 0
                    else 0.0
                )
                logger.info(
                    "Position synced from exchange: side=%d qty=%.6f entry=%.2f",
                    self.core.position.side,
                    self.core.position.quantity,
                    self.core.position.entry_price or 0.0,
                )
                return

        # No open position on exchange
        if self.core.position.side != 0:
            logger.info(
                "Exchange shows no position, clearing local position (was side=%d)",
                self.core.position.side,
            )
            self.core.position.side = 0
            self.core.position.quantity = 0.0
            self.core.position.entry_price = None
            self.core.position.notional = 0.0
            self.core.position.margin_used = 0.0

    # ── WebSocket event loop ─────────────────────────────────────────

    def _ws_consumer_loop(self) -> None:
        """Background thread that consumes WebSocket user-data events.

        Processes ORDER_TRADE_UPDATE and ACCOUNT_UPDATE events to maintain
        real-time awareness of fills and position changes.
        """
        logger.info("WebSocket consumer thread started")
        while not self._shutdown_event.is_set():
            try:
                events = self.exchange_events.ingest_once(self.event_source)
                for event in events:
                    event_type = event.get("event_type", "")
                    payload = event.get("payload") or {}

                    if event_type == "order_trade_update":
                        execution_type = str(
                            payload.get("execution_type") or ""
                        ).lower()
                        if execution_type == "trade":
                            fill_data = {
                                "order_id": payload.get("order_id"),
                                "client_order_id": payload.get("client_order_id"),
                                "exchange_order_id": payload.get("order_id"),
                                "fill_price": float(
                                    payload.get("last_fill_price") or 0.0
                                ),
                                "fill_quantity": float(
                                    payload.get("last_fill_quantity") or 0.0
                                ),
                                "total_filled": float(
                                    payload.get("filled_quantity") or 0.0
                                ),
                                "average_price": float(
                                    payload.get("average_price") or 0.0
                                ),
                                "side": payload.get("side"),
                                "status": payload.get("status"),
                                "realized_pnl": payload.get("realized_pnl"),
                                "reduce_only": payload.get("reduce_only"),
                                "timestamp": event.get("timestamp"),
                            }
                            with self._ws_lock:
                                self._pending_fills.append(fill_data)
                            logger.info(
                                "Fill received: qty=%.6f price=%.2f side=%s order=%s",
                                fill_data["fill_quantity"],
                                fill_data["fill_price"],
                                fill_data["side"],
                                fill_data["client_order_id"],
                            )

                    elif event_type == "account_update":
                        # Position state is updated by execution_state.observe()
                        # already called in ingest_once. We just log it.
                        positions = payload.get("positions") or []
                        if positions:
                            logger.info(
                                "Account update received: %d positions",
                                len(positions),
                            )

            except Exception as exc:  # noqa: BLE001
                logger.error("WebSocket consumer error: %s", exc)
                if self._shutdown_event.is_set():
                    break
                time.sleep(1)

        logger.info("WebSocket consumer thread stopped")

    def _process_pending_fills(self) -> list[dict[str, Any]]:
        """Process fills received from WebSocket thread.

        Called from the main loop thread to update core state with
        real fill data from the exchange.
        """
        with self._ws_lock:
            fills = list(self._pending_fills)
            self._pending_fills.clear()

        processed = []
        for fill_data in fills:
            fill_price = fill_data["fill_price"]
            fill_qty = fill_data["fill_quantity"]
            side = str(fill_data.get("side") or "").lower()
            is_reduce = bool(fill_data.get("reduce_only"))
            realized_pnl = fill_data.get("realized_pnl")

            if fill_qty <= 0 or fill_price <= 0:
                continue

            if is_reduce and self.core.position.side != 0:
                # Close/reduce fill — apply PnL to capital
                if realized_pnl is not None:
                    try:
                        pnl = float(realized_pnl)
                        self.core.capital += pnl
                        logger.info(
                            "Applied reduce fill PnL: %.4f capital=%.4f",
                            pnl, self.core.capital,
                        )
                    except (TypeError, ValueError):
                        pass

                # Update position size
                remaining = abs(self.core.position.quantity) - fill_qty
                if remaining <= 1e-12:
                    # Fully closed
                    self.core.trades.append({
                        "entry_time": self.core.position.entry_time,
                        "exit_time": fill_data.get("timestamp"),
                        "entry_price": self.core.position.entry_price,
                        "exit_price": fill_price,
                        "position": self.core.position.side,
                        "bars_held": self.core.position.bars_held,
                        "notional_closed": self.core.position.notional,
                        "remaining_notional": 0.0,
                        "reason": "live_fill",
                        "is_partial": False,
                        "pnl_after_costs": (
                            float(realized_pnl) if realized_pnl is not None else None
                        ),
                    })
                    self.core.position.side = 0
                    self.core.position.quantity = 0.0
                    self.core.position.entry_price = None
                    self.core.position.notional = 0.0
                    self.core.position.margin_used = 0.0
                    self.core.position.bars_held = 0
                    self.core.position.peak_price = None
                    self.core.position.trough_price = None
                    self.core.position.break_even_armed = False
                    self.core.position.partial_taken = False
                    self.core.position.stepped_stop_anchor = None
                    logger.info("Position fully closed at %.2f", fill_price)
                else:
                    self.core.position.quantity = remaining
                    self.core.position.notional = (
                        remaining * (self.core.position.entry_price or fill_price)
                    )
                    self.core.position.margin_used = (
                        self.core.position.notional / self.context.contract.leverage
                        if self.context.contract.leverage > 0
                        else 0.0
                    )
                    logger.info(
                        "Position partially reduced: remaining=%.6f", remaining
                    )
            else:
                # Open fill — set position
                fill_side = 1 if side == "buy" else -1
                if self.core.position.side == 0:
                    self.core.position.side = fill_side
                    self.core.position.quantity = fill_qty
                    self.core.position.entry_price = fill_price
                    self.core.position.entry_time = fill_data.get("timestamp")
                    self.core.position.notional = fill_qty * fill_price
                    self.core.position.leverage = self.context.contract.leverage
                    self.core.position.margin_used = (
                        self.core.position.notional / self.context.contract.leverage
                        if self.context.contract.leverage > 0
                        else 0.0
                    )
                    self.core.position.symbol = self.context.contract.symbol
                    self.core.position.bars_held = 0
                    self.core.position.peak_price = None
                    self.core.position.trough_price = None
                    self.core.position.break_even_armed = False
                    self.core.position.partial_taken = False
                    self.core.position.stepped_stop_anchor = None
                    logger.info(
                        "Position opened: side=%d qty=%.6f entry=%.2f",
                        fill_side, fill_qty, fill_price,
                    )
                elif self.core.position.side == fill_side:
                    # Adding to position
                    old_qty = self.core.position.quantity
                    old_entry = self.core.position.entry_price or fill_price
                    new_qty = old_qty + fill_qty
                    self.core.position.entry_price = (
                        (old_qty * old_entry + fill_qty * fill_price) / new_qty
                    )
                    self.core.position.quantity = new_qty
                    self.core.position.notional = (
                        new_qty * self.core.position.entry_price
                    )
                    self.core.position.margin_used = (
                        self.core.position.notional / self.context.contract.leverage
                        if self.context.contract.leverage > 0
                        else 0.0
                    )
                    logger.info(
                        "Position increased: total_qty=%.6f avg_entry=%.2f",
                        new_qty, self.core.position.entry_price,
                    )

            processed.append(fill_data)

        return processed

    # ── Graceful shutdown ────────────────────────────────────────────

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle SIGTERM/SIGINT for graceful shutdown."""
        sig_name = signal.Signals(signum).name
        logger.info("Received %s, initiating shutdown...", sig_name)
        self._shutdown_event.set()

    def shutdown(self) -> None:
        """Graceful shutdown: cancel orders, save state, close connections."""
        logger.info("Shutdown initiated")

        # Cancel open orders if configured
        if self.context.live_risk.cancel_open_orders_on_shutdown:
            logger.info("Cancelling open orders on shutdown...")
            open_orders_result = self.adapter.fetch_open_orders()
            if open_orders_result.ok and isinstance(open_orders_result.payload, list):
                for order in open_orders_result.payload:
                    order_id = order.get("id")
                    if order_id:
                        cancel_result = self.adapter.cancel_order(order_id)
                        if cancel_result.ok:
                            logger.info("Cancelled order %s", order_id)
                        else:
                            logger.warning(
                                "Failed to cancel order %s: %s",
                                order_id, cancel_result.error,
                            )

        # Save final state
        self.save_state({
            "event": "shutdown",
            "timestamp": self.now_iso(),
            "reason": "graceful_shutdown",
        })

        # Stop WebSocket thread
        self._shutdown_event.set()
        if self._ws_thread is not None and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=5)

        # Close WebSocket connection and listen key
        self.exchange_events.detach_transport(error="shutdown")
        self.exchange_events.close_listen_key()

        logger.info("Shutdown complete")

    def on_blocked_snapshot(self, payload: dict):
        # Process any pending fills even when blocked
        fills = self._process_pending_fills()
        if fills:
            payload["live_fills"] = fills
        self.audit.log("live_session_blocked", payload)
        self.save_state(payload)
        return payload

    def on_hold(self, payload: dict):
        # Process pending fills from WebSocket
        fills = self._process_pending_fills()
        if fills:
            payload["live_fills"] = fills

        # Check exit conditions on current position
        if self.core.position.side != 0:
            current_price = None
            try:
                ticker = self.exchange.fetch_ticker(self.context.contract.symbol)
                current_price = float(ticker.get("last") or 0.0)
            except Exception:  # noqa: BLE001
                pass

            if current_price and current_price > 0:
                # Update position tracking (peak/trough/bars)
                self.exit_manager.update_tracking(self.core, current_price)

                # Check and submit exit if warranted
                exit_result = self.exit_manager.check_and_submit_exit(
                    self.core,
                    current_price,
                    self.context.contract.symbol,
                    use_testnet=self._use_testnet,
                )
                if exit_result is not None:
                    payload["exit_action"] = exit_result

        self.audit.log("live_session_hold", payload)
        self.save_state(payload)
        return payload

    def on_decision(self, payload: dict):
        # Process pending fills from WebSocket
        fills = self._process_pending_fills()
        if fills:
            payload["live_fills"] = fills

        # Check exit conditions before processing new signals
        if self.core.position.side != 0:
            snapshot_close = float(
                (payload.get("snapshot") or {}).get("close") or 0.0
            )
            if snapshot_close > 0:
                self.exit_manager.update_tracking(self.core, snapshot_close)
                exit_result = self.exit_manager.check_and_submit_exit(
                    self.core,
                    snapshot_close,
                    self.context.contract.symbol,
                    use_testnet=self._use_testnet,
                )
                if exit_result is not None:
                    payload["exit_action"] = exit_result
                    # If exit submitted, don't open new position this cycle
                    self.audit.log("live_session_decision", payload)
                    self.save_state(payload)
                    return payload

        state = self.gov_state.load()
        self.event_source.emit(
            "runtime_decision",
            self.now_iso(),
            {
                "signal": payload.get("signal"),
                "snapshot": payload.get("snapshot") or {},
                "intended_order": payload.get("intended_order") or {},
            },
            source="runtime",
        )
        if state.get("emergency_stop"):
            halted = {
                "event": "halted",
                "reason": "emergency_stop",
                "timestamp": self.now_iso(),
            }
            self.audit.log("live_session_halt", halted)
            self.alerts.emit(
                "pilot_blocking",
                {
                    "timestamp": self.now_iso(),
                    "reason": "emergency_stop",
                },
                severity="critical",
            )
            self.incidents.append(
                IncidentRecord(
                    incident_id=f"incident-{int(time.time())}",
                    incident_type="governance",
                    severity="critical",
                    state="detected",
                    timestamp=self.now_iso(),
                    summary="Emergency stop active",
                    metadata=halted,
                )
            )
            self.save_state(halted)
            return halted
        if state.get("maintenance"):
            halted = {
                "event": "halted",
                "reason": "maintenance_mode",
                "timestamp": self.now_iso(),
            }
            self.audit.log("live_session_halt", halted)
            self.alerts.emit(
                "pilot_blocking",
                {
                    "timestamp": self.now_iso(),
                    "reason": "maintenance_mode",
                },
                severity="critical",
            )
            self.incidents.append(
                IncidentRecord(
                    incident_id=f"incident-{int(time.time())}",
                    incident_type="maintenance",
                    severity="warning",
                    state="detected",
                    timestamp=self.now_iso(),
                    summary="Maintenance mode active",
                    metadata=halted,
                )
            )
            self.save_state(halted)
            return halted

        intended = payload.get("intended_order") or {}
        store = self.state_store()
        canonical_state = self.exchange_events.execution_state
        local_orders = canonical_state.active_orders() or []
        balance = self.adapter.fetch_balance()
        available_margin = None
        if balance.ok and isinstance(balance.payload, dict):
            usdt_raw = balance.payload.get("USDT")
            usdt = usdt_raw if isinstance(usdt_raw, dict) else {}
            available_margin = usdt.get("free")
        local_position = canonical_state.derived_position()
        open_local_orders = len(local_orders)
        reconcile = self.adapter.reconcile_state(
            local_position.get("side", self.core.position.side),
            open_local_orders,
            local_position=local_position,
            local_orders=local_orders,
        )
        reconcile_payload = (
            reconcile.payload if isinstance(reconcile.payload, dict) else {}
        )
        reconcile_ok = bool(reconcile.ok and reconcile_payload.get("ok", False))
        payload["reconcile_report"] = (
            reconcile.payload
            if reconcile.ok
            else {"ok": False, "error": reconcile.error}
        )
        result = self.executor.submit_intended_order(
            symbol=self.context.contract.symbol,
            signal=payload["signal"],
            quantity=float(intended.get("quantity", 0.0)),
            notional=float(intended.get("notional", 0.0)),
            stale=payload["snapshot"].get("stale", False),
            reconcile_ok=reconcile_ok,
            watchdog_halted=self.watchdog.state.halted,
            available_margin=(
                None if available_margin is None else float(available_margin)
            ),
            leverage=self.context.contract.leverage,
            position_side=self.core.position.side,
            account_mode="one_way",
            current_open_positions=0 if local_position.get("side", 0) == 0 else 1,
            emergency_stop=state.get("emergency_stop", False),
            maintenance=state.get("maintenance", False),
            current_daily_loss_pct=0.0,
        )
        if hasattr(store, "append_operator_action"):
            store.append_operator_action(
                {
                    "timestamp": self.now_iso(),
                    "action": "submit_intended_order",
                    "signal": payload["signal"],
                    "quantity": float(intended.get("quantity", 0.0)),
                    "notional": float(intended.get("notional", 0.0)),
                    "result": result.get("status"),
                }
            )
        order = result.get("order") if isinstance(result, dict) else None
        if order is not None and hasattr(store, "upsert_order"):
            record = canonical_record_from_order(order, submission_mode="governed_live")
            record = apply_local_submit(
                record,
                timestamp=order.created_at,
                payload={
                    "signal": payload["signal"],
                    "quantity": float(intended.get("quantity", 0.0)),
                },
            )
            remote_status = "new"
            if result.get("status") in {"submitted_recovered", "submitted"}:
                remote_status = "new"
            record = apply_remote_status(
                record,
                status=remote_status,
                timestamp=self.now_iso(),
                payload=result.get("response") or {},
                exchange_order_id=(result.get("response") or {}).get("id"),
            )
            store.upsert_order(record.to_dict())
            monitor_result = self.order_monitor.inspect(order, record=record)
            if monitor_result.get("record") is not None:
                store.upsert_order(monitor_result["record"].to_dict())
            payload["post_submit_monitor"] = {
                k: v for k, v in monitor_result.items() if k != "record"
            }
            if monitor_result.get("status") in {"stuck_open", "partial_fill"}:
                replace_result = self.executor.governed_cancel_replace(
                    order.order_id,
                    symbol=self.context.contract.symbol,
                    new_signal=payload["signal"],
                    quantity=float(intended.get("quantity", 0.0)),
                    notional=float(intended.get("notional", 0.0)),
                    record=monitor_result.get("record"),
                )
                payload["cancel_replace"] = {
                    k: v
                    for k, v in replace_result.items()
                    if k not in {"record", "new_order"}
                }
                if replace_result.get("record") is not None:
                    store.upsert_order(replace_result["record"].to_dict())
                new_order = replace_result.get("new_order")
                if new_order is not None:
                    parent_record = replace_result.get("record") or monitor_result.get(
                        "record"
                    )
                    replacement_record = canonical_record_from_order(
                        new_order,
                        submission_mode="governed_live",
                    )
                    if parent_record is not None:
                        replacement_record = propagate_replace_chain(
                            parent_record, replacement_record
                        )
                    replacement_record = apply_local_submit(
                        replacement_record,
                        timestamp=new_order.created_at,
                        payload={"replaces": order.order_id},
                    )
                    store.upsert_order(replacement_record.to_dict())
            sample = sample_from_execution(
                timestamp=self.now_iso(),
                symbol=self.context.contract.symbol,
                mode="governed_live",
                side=order.side.value,
                order_type=order.order_type.value,
                quantity=order.quantity,
                notional=float(intended.get("notional", 0.0)),
                reference_price=float(payload["snapshot"]["close"]),
                executed_price=float(
                    payload["snapshot"]["ask"]
                    if order.side.value == "buy"
                    else payload["snapshot"]["bid"] or payload["snapshot"]["close"]
                ),
                fill_quantity=order.quantity,
                spread_bps=(
                    abs(
                        (payload["snapshot"].get("ask") or payload["snapshot"]["close"])
                        - (
                            payload["snapshot"].get("bid")
                            or payload["snapshot"]["close"]
                        )
                    )
                    / payload["snapshot"]["close"]
                    * 10000
                    if payload["snapshot"]["close"] > 0
                    else None
                ),
                depth_notional=self.context.execution.simulated_depth_notional,
                queue_model=self.context.execution.queue_priority_model,
                funding_rate=payload["snapshot"].get("funding_rate"),
                funding_cost=None,
                volatility_bucket="normal",
                latency_ms=self.context.execution.latency_ms,
                stale=payload["snapshot"].get("stale", False),
                metadata={
                    "calibration_version": "t4-v1",
                    "request_id": result.get("request_id"),
                },
            )
            self.calibration_store.append(sample)
        payload["result"] = result
        self.audit.log("live_session_decision", payload)
        self.save_state(payload)
        return payload

    def step(self):
        state = self.gov_state.load()
        if state.get("emergency_stop"):
            payload = {
                "event": "halted",
                "reason": "emergency_stop",
                "timestamp": self.now_iso(),
            }
            self.audit.log("live_session_halt", payload)
            self.save_state(payload)
            return payload
        if state.get("maintenance"):
            payload = {
                "event": "halted",
                "reason": "maintenance_mode",
                "timestamp": self.now_iso(),
            }
            self.audit.log("live_session_halt", payload)
            self.save_state(payload)
            return payload
        return super().step()

    def run_loop(self, interval_seconds: int = 60, iterations: Optional[int] = None):
        # Register signal handlers for graceful shutdown
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Start WebSocket consumer thread if transport factory available
        if self.exchange_events.transport_factory is not None:
            self._ws_thread = threading.Thread(
                target=self._ws_consumer_loop,
                name="ws-consumer",
                daemon=True,
            )
            self._ws_thread.start()
            logger.info("WebSocket consumer thread launched")
        else:
            logger.info(
                "No WebSocket transport factory configured, running poll-only mode"
            )

        logger.info(
            "Live trading loop started: interval=%ds symbol=%s mode=%s",
            interval_seconds,
            self.context.contract.symbol,
            self.policy.mode.value,
        )

        count = 0
        try:
            while not self._shutdown_event.is_set():
                if self.watchdog.check_timeout():
                    payload = {
                        "event": "halted",
                        "reason": "heartbeat_timeout",
                        "timestamp": self.now_iso(),
                    }
                    self.audit.log("live_session_halt", payload)
                    self.save_state(payload)
                    logger.warning("Heartbeat timeout, halting")
                    break
                # Check for WebSocket reconnects requiring sync
                if self.exchange_events.execution_state.needs_rest_reconciliation:
                    logger.info("WebSocket reconnected: triggering REST position sync")
                    self._sync_position_from_exchange()
                    self.exchange_events.execution_state.needs_rest_reconciliation = False

                # Handle watchdog halts (Error Recovery Policy)
                if self.watchdog.state.halted:
                    # Upgrade to governance emergency_stop
                    state = self.gov_state.load()
                    if not state.get("emergency_stop"):
                        logger.critical("Error Recovery Policy: Max failures exceeded. Triggering emergency_stop.")
                        state["emergency_stop"] = True
                        self.gov_state.save(state)
                        # Try to cancel open orders to protect capital
                        self.adapter.cancel_all_orders(self.context.contract.symbol)
                    
                    # Stay halted until user intervention
                    self._shutdown_event.wait(timeout=interval_seconds)
                    continue

                try:
                    payload = self.step()
                    logger.info(
                        "Step %d: event=%s",
                        count + 1,
                        payload.get("event", "unknown"),
                    )
                    # Reset failures on success
                    if self.watchdog.state.consecutive_failures > 0:
                        logger.info("Step succeeded, resetting failure count")
                        self.watchdog.beat()
                        
                except Exception as exc:  # noqa: BLE001
                    logger.error("Step error: %s", exc)
                    self.watchdog.record_failure(str(exc))
                    self.alerts.emit(
                        "step_error",
                        {"timestamp": self.now_iso(), "error": str(exc)},
                        severity="critical",
                    )
                    
                    if not self.watchdog.state.halted:
                        # Exponential backoff sleep
                        backoff = min(2 ** self.watchdog.state.consecutive_failures, interval_seconds)
                        logger.warning("Error Recovery Policy: Backing off for %ds", backoff)
                        self._shutdown_event.wait(timeout=backoff)
                        continue

                count += 1
                if iterations is not None and count >= iterations:
                    logger.info("Iteration limit reached (%d)", iterations)
                    break
                # Interruptible sleep
                self._shutdown_event.wait(timeout=interval_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error in run_loop: %s", exc)
        finally:
            self.shutdown()
            # Restore original signal handlers
            signal.signal(signal.SIGINT, original_sigint)
            signal.signal(signal.SIGTERM, original_sigterm)
            logger.info("Live trading loop exited")
