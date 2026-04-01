import asyncio
import logging
import threading
import uuid
import pandas as pd
from typing import Any, Optional, Dict
from datetime import datetime, timezone

from btc_contract_backtest.config.models import (
    ContractSpec,
    AccountConfig,
    RiskConfig,
    ExecutionConfig,
    LiveRiskConfig,
)
from btc_contract_backtest.live.live_session import GovernedLiveSession
from btc_contract_backtest.live.governance import TradingMode
from btc_contract_backtest.strategies import build_strategy

logger = logging.getLogger("btc_contract_backtest.web.bot_manager")
thread_local = threading.local()


class QueueHandler(logging.Handler):
    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.queue = queue
        self.loop = loop

    def emit(self, record):
        try:
            msg = self.format(record)
            session_id = getattr(thread_local, "session_id", "system")
            if self.loop.is_running():
                self.loop.call_soon_threadsafe(
                    self.queue.put_nowait,
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "level": record.levelname,
                        "message": msg,
                        "logger": record.name,
                        "session_id": session_id,
                    },
                )
        except Exception:
            self.handleError(record)


class BotManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BotManager, cls).__new__(cls)
                cls._instance._init_manager()
            return cls._instance

    def _init_manager(self):
        # session_id -> { "session": GovernedLiveSession, "thread": Thread, "is_running": bool, "mode", "symbol", "strategy", "type": "live"|"backtest", "result": dict }
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.log_queue: Optional[asyncio.Queue] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._handler_attached = False

    def ensure_loop(self, loop: asyncio.AbstractEventLoop):
        """Ensures the manager is bound to the correct running event loop."""
        with self._lock:
            if self.loop is None:
                self.loop = loop
                self.log_queue = asyncio.Queue(maxsize=2000)

                # Attach log handler to the package logger
                root_logger = logging.getLogger("btc_contract_backtest")
                handler = QueueHandler(self.log_queue, self.loop)
                handler.setFormatter(logging.Formatter("%(message)s"))
                root_logger.addHandler(handler)
                self._handler_attached = True
                logger.info("BotManager bound to event loop and log handler attached.")

    def _run_bot_thread(self, session_id: str, interval: int):
        """Wrapper for the bot loop to ensure state cleanup on exit."""
        thread_local.session_id = session_id
        try:
            session_state = self.sessions.get(session_id)
            if session_state and session_state.get("session"):
                session_state["session"].run_loop(interval_seconds=interval)
        except Exception as e:
            logger.error(
                f"Bot loop exception [Session {session_id[:8]}]: {e}", exc_info=True
            )
        finally:
            with self._lock:
                if session_id in self.sessions:
                    self.sessions[session_id]["is_running"] = False
            logger.info(f"Bot thread exited [Session {session_id[:8]}].")

    def start_bot(self, config: Dict[str, Any]) -> str:
        with self._lock:
            session_id = str(uuid.uuid4())

            capital = float(config.get("capital", 1000.0))
            leverage = int(config.get("leverage", 5))
            mode_str = config.get("mode", "PAPER").upper()
            mode = (
                TradingMode[mode_str]
                if mode_str in TradingMode.__members__
                else TradingMode.PAPER
            )
            symbol = config.get("symbol", "BTC/USDT")
            timeframe = config.get("timeframe", "1h")
            interval = int(config.get("interval_seconds", 15))

            profile = "binance_futures_mainnet"
            logger.info(
                f"Selected exchange profile: {profile} for session {session_id[:8]}"
            )

            contract = ContractSpec(
                symbol=symbol,
                leverage=leverage,
                exchange_profile=profile,
            )
            account = AccountConfig(initial_capital=capital)

            risk = RiskConfig(
                max_position_notional_pct=float(config.get("max_pos_pct", 0.95)),
                risk_per_trade_pct=float(config.get("risk_per_trade_pct", 0.02)),
                stop_loss_pct=float(config.get("stop_loss_pct", 0.04)),
                take_profit_pct=float(config.get("take_profit_pct", 0.10)),
                atr_stop_mult=float(config.get("atr_stop_mult", 2.5)),
                break_even_trigger_pct=float(
                    config.get("break_even_trigger_pct", 0.03)
                ),
            )

            execution = ExecutionConfig(
                default_order_type="market",
                enforce_exchange_constraints=True,
                allow_partial_fills=False,  # Hardcoded as requested previously
            )
            live_risk = LiveRiskConfig(
                max_consecutive_failures=int(config.get("max_retries", 5)),
                cancel_open_orders_on_shutdown=True,
            )

            strategy_name = config.get("strategy", "sparse_meta_portfolio")
            strategy = build_strategy(strategy_name)

            session = GovernedLiveSession(
                contract=contract,
                account=account,
                risk=risk,
                strategy=strategy,
                timeframe=timeframe,
                execution=execution,
                live_risk=live_risk,
                mode=mode,
                allow_mainnet=True,
            )

            thread = threading.Thread(
                target=self._run_bot_thread,
                args=(session_id, interval),
                name=f"bot-{session_id[:8]}",
                daemon=True,
            )

            self.sessions[session_id] = {
                "session": session,
                "thread": thread,
                "is_running": True,
                "mode": mode_str,
                "symbol": symbol,
                "strategy": strategy_name,
                "type": "live",
                "peak_equity": capital,
                "max_realtime_drawdown": 0.0,
            }

            thread.start()
            logger.info(
                f"Bot started | Session: {session_id[:8]} | Symbol: {symbol} | Mode: {mode_str}"
            )
            return session_id

    def stop_bot(self, session_id: str):
        session_state = self.sessions.get(session_id)
        if not session_state or not session_state.get("is_running"):
            return

        logger.info(f"Stopping bot... [Session {session_id[:8]}]")
        session_obj = session_state.get("session")
        if session_obj:
            if hasattr(session_obj, "shutdown"):
                session_obj.shutdown()
            else:
                session_obj._shutdown_event.set()

    def get_trades(self, session_id: str):
        session_state = self.sessions.get(session_id)
        if not session_state:
            return []

        # If it's a backtest, return from payload
        if session_state["type"] == "backtest":
            return session_state["result"].get("trades", [])

        # If live/paper
        session_obj = session_state.get("session")
        if not session_obj:
            return []
        return session_obj.core.trades

    def get_markers(self, session_id: str):
        session_state = self.sessions.get(session_id)
        if not session_state:
            return []

        if session_state["type"] == "backtest":
            return session_state["result"].get("markers", [])

        session_obj = session_state.get("session")
        if not session_obj:
            return []

        core = session_obj.core
        markers = []

        def to_unix(ts):
            if ts is None:
                return 0
            if isinstance(ts, (int, float)):
                return int(ts)
            try:
                import pandas as pd

                return int(pd.to_datetime(ts).timestamp())
            except Exception:
                return 0

        # 1. Add markers from completed trades
        for t in core.trades:
            # Entry
            markers.append(
                {
                    "time": to_unix(t["entry_time"]),
                    "price": t["entry_price"],
                    "qty": t.get("notional_closed", 0) / t["entry_price"]
                    if t["entry_price"] > 0
                    else 0,
                    "type": "BUY" if t["position"] == 1 else "SELL",
                    "side": t["position"],
                    "is_entry": True,
                }
            )
            # Exit
            markers.append(
                {
                    "time": to_unix(t["exit_time"]),
                    "price": t["exit_price"],
                    "qty": t.get("notional_closed", 0) / t["exit_price"]
                    if t["exit_price"] > 0
                    else 0,
                    "type": "SELL" if t["position"] == 1 else "BUY",
                    "side": t["position"],
                    "is_entry": False,
                    "pnl": t.get("pnl_after_costs"),
                }
            )

        # 2. Add marker for current open position entry
        pos = core.position
        if pos.side != 0 and pos.entry_time:
            markers.append(
                {
                    "time": to_unix(pos.entry_time),
                    "price": pos.entry_price,
                    "qty": abs(pos.quantity),
                    "type": "BUY" if pos.side == 1 else "SELL",
                    "side": pos.side,
                    "is_entry": True,
                }
            )

        return markers

    def get_performance(self, session_id: str):
        session_state = self.sessions.get(session_id)
        if not session_state:
            return {}

        if session_state["type"] == "backtest":
            return session_state["result"].get("metrics", {})

        session_obj = session_state.get("session")
        if not session_obj:
            return {}

        trades = session_obj.core.trades
        if not trades:
            return {
                "win_rate": 0,
                "profit_factor": 0,
                "total_trades": 0,
                "total_pnl": 0,
                "pnl_pct": 0,
                "avg_bars_held": 0,
            }

        wins = [t for t in trades if (t.get("pnl_after_costs") or 0) > 0]
        losses = [t for t in trades if (t.get("pnl_after_costs") or 0) <= 0]

        gross_profit = sum(t.get("pnl_after_costs") or 0 for t in wins)
        gross_loss = abs(sum(t.get("pnl_after_costs") or 0 for t in losses))

        initial_capital = session_obj.context.account.initial_capital
        total_pnl = sum(t.get("pnl_after_costs") or 0 for t in trades)

        return {
            "win_rate": round(len(wins) / len(trades) * 100, 2),
            "profit_factor": round(gross_profit / gross_loss, 2)
            if gross_loss > 0
            else (gross_profit if gross_profit > 0 else 0),
            "total_trades": len(trades),
            "total_pnl": round(total_pnl, 2),
            "pnl_pct": round((total_pnl / initial_capital) * 100, 2)
            if initial_capital > 0
            else 0,
            "avg_bars_held": round(
                sum(t.get("bars_held", 0) for t in trades) / len(trades), 1
            ),
        }

    def get_status(self, session_id: str) -> Dict[str, Any]:
        session_state = self.sessions.get(session_id)
        if not session_state:
            return {"status": "not_found", "session_id": session_id}

        if session_state["type"] == "backtest":
            res = session_state["result"]
            return {
                "status": "completed",
                "mode": "BACKTEST",
                "capital": res.get("capital", 0),
                "unrealized_pnl": 0.0,
                "position": {
                    "side": 0,
                    "quantity": 0,
                    "entry_price": 0,
                    "notional": 0,
                    "pnl": 0,
                },
                "performance": res.get("metrics", {}),
                "latest_decision": {
                    "action": "COMPLETED",
                    "current_price": 0,
                    "intended_qty": 0,
                },
                "config": {
                    "symbol": session_state.get("symbol", "UNKNOWN"),
                    "mode": "BACKTEST",
                    "strategy": session_state.get("strategy", "Unknown"),
                },
                "ohlcv": res.get("ohlcv", []),
                "equity_curve": res.get("equity_curve", []),
            }

        session_obj = session_state.get("session")
        if not session_obj:
            return {"status": "stopped"}

        # 1. Calculate Mark-to-Market (MTM) Equity for Paper Trading
        pos = session_obj.core.position
        capital = float(session_obj.core.capital)
        unrealized_pnl = 0.0

        current_price = 0.0
        if session_obj.core.last_snapshot:
            current_price = float(session_obj.core.last_snapshot.close)

        if pos.side != 0 and pos.entry_price and current_price > 0:
            price_diff_pct = (current_price - pos.entry_price) / pos.entry_price
            unrealized_pnl = (
                pos.side
                * price_diff_pct
                * (abs(pos.quantity) * pos.entry_price)
                * pos.leverage
            )

        mtm_equity = capital + unrealized_pnl

        # 2. Update Peak Equity and Calculate Real-time Max Drawdown
        session_state["peak_equity"] = max(session_state["peak_equity"], mtm_equity)
        max_drawdown_pct = 0.0
        if session_state["peak_equity"] > 0:
            current_drawdown = (
                (session_state["peak_equity"] - mtm_equity)
                / session_state["peak_equity"]
                * 100
            )
            session_state["max_realtime_drawdown"] = max(
                session_state["max_realtime_drawdown"], current_drawdown
            )
            max_drawdown_pct = session_state["max_realtime_drawdown"]

        # 3. Performance Stats
        perf = self.get_performance(session_id)
        perf["max_drawdown_pct"] = round(max_drawdown_pct, 2)

        # 4. Final Payload
        last_decision = getattr(session_obj, "last_decision", {})
        if not last_decision.get("action"):
            signal = last_decision.get("signal", 0)
            if signal == 1:
                action_label = "OPEN LONG"
            elif signal == -1:
                action_label = "OPEN SHORT"
            else:
                action_label = "MONITORING"
            last_decision["action"] = action_label

        return {
            "status": "running"
            if session_state.get("is_running")
            and not session_obj._shutdown_event.is_set()
            else "stopped",
            "capital": round(mtm_equity, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "position": {
                "side": pos.side,
                "quantity": abs(pos.quantity),
                "entry_price": pos.entry_price,
                "notional": round(abs(pos.quantity) * current_price, 2),
                "pnl": round(unrealized_pnl, 2),
            },
            "performance": perf,
            "latest_decision": {
                **last_decision,
                "current_price": round(current_price, 2),
                "intended_qty": abs(pos.quantity) if pos.side != 0 else 0,
            },
            "config": {
                "symbol": session_obj.context.contract.symbol,
                "mode": session_obj.policy.mode.value,
                "leverage": session_obj.context.contract.leverage,
                "strategy": session_obj.strategy.name()
                if hasattr(session_obj.strategy, "name")
                else "Unknown",
            },
            "ohlcv": self._get_ohlcv_data(session_obj),
        }

    def _get_ohlcv_data(self, session_obj):
        if not session_obj or session_obj._last_df is None:
            return []

        df = session_obj._last_df
        # Ensure we are not sending more than 500 bars to keep payload reasonable
        if len(df) > 500:
            df = df.iloc[-500:]

        ohlcv = []
        for timestamp, row in df.iterrows():
            if hasattr(timestamp, "timestamp"):
                t = int(timestamp.timestamp())
            elif isinstance(timestamp, (int, float)):
                t = int(timestamp) if timestamp > 1e10 else int(timestamp / 1000)
            else:
                try:
                    t = int(pd.to_datetime(timestamp).timestamp())
                except Exception:
                    continue

            ohlcv.append(
                {
                    "time": t,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                }
            )

        ohlcv.sort(key=lambda x: x["time"])
        unique_ohlcv = []
        last_t = -1
        for bar in ohlcv:
            if bar["time"] > last_t:
                unique_ohlcv.append(bar)
                last_t = bar["time"]

        return unique_ohlcv

    def run_offline_backtest(self, config: Dict[str, Any]) -> str:
        """Runs a synchronous historical backtest and saves the result payload as a session. Returns session_id."""
        from btc_contract_backtest.config.models import (
            ContractSpec,
            AccountConfig,
            RiskConfig,
            ExecutionConfig,
            LiveRiskConfig,
        )
        from btc_contract_backtest.strategies import build_strategy
        from btc_contract_backtest.engine.futures_engine import FuturesBacktestEngine
        from datetime import timedelta

        session_id = str(uuid.uuid4())
        thread_local.session_id = session_id

        capital = float(config.get("capital", 1000.0))
        leverage = int(config.get("leverage", 5))
        symbol = config.get("symbol", "BTC/USDT")
        timeframe = config.get("timeframe", "1h")
        days = int(config.get("days", 30))
        strategy_name = config.get("strategy", "sparse_meta_portfolio")

        contract = ContractSpec(
            symbol=symbol, leverage=leverage, exchange_profile="binance_futures_mainnet"
        )
        account = AccountConfig(initial_capital=capital)

        risk = RiskConfig(
            stop_loss_pct=float(config.get("stop_loss_pct", 0.04)),
            take_profit_pct=float(config.get("take_profit_pct", 0.10)),
            risk_per_trade_pct=float(config.get("risk_per_trade_pct", 0.02)),
            max_position_notional_pct=float(config.get("max_pos_pct", 0.95)),
            atr_stop_mult=float(config.get("atr_stop_mult", 2.5)),
            break_even_trigger_pct=float(config.get("break_even_trigger_pct", 0.03)),
        )
        execution = ExecutionConfig()
        live_risk = LiveRiskConfig()

        strategy = build_strategy(strategy_name)

        engine = FuturesBacktestEngine(
            contract,
            account,
            risk,
            timeframe=timeframe,
            execution=execution,
            live_risk=live_risk,
        )

        start_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%d"
        )
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        df = engine.fetch_historical_data(start_date, end_date)
        signal_df = strategy.generate_signals(df)
        results = engine.simulate(signal_df)
        metrics = engine.calculate_metrics(results)

        trades_df = results.get("trades", pd.DataFrame())

        def to_unix(ts):
            if ts is None:
                return 0
            if hasattr(ts, "timestamp"):
                return int(ts.timestamp())
            if isinstance(ts, (int, float)):
                return int(ts) if ts > 1e10 else int(ts / 1000)
            try:
                return int(pd.to_datetime(ts).timestamp())
            except Exception:
                return 0

        markers = []
        trades_payload = []

        if not trades_df.empty:
            for idx, t in trades_df.iterrows():
                entry_time = t.get("entry_time")
                exit_time = t.get("exit_time")
                entry_price = float(t.get("entry_price", 0))
                exit_price = float(t.get("exit_price", 0))
                side = int(t.get("position", 1))
                pnl = float(t.get("pnl_after_costs", 0))
                notional = float(t.get("notional_closed", 0.0))
                qty = notional / exit_price if exit_price > 0 else 0

                trades_payload.append(
                    {
                        "entry_time": to_unix(entry_time),
                        "exit_time": to_unix(exit_time),
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "position": side,
                        "pnl_after_costs": pnl,
                        "notional_closed": notional,
                    }
                )

                if entry_time:
                    markers.append(
                        {
                            "time": to_unix(entry_time),
                            "price": entry_price,
                            "qty": qty,
                            "type": "BUY" if side == 1 else "SELL",
                            "side": side,
                            "is_entry": True,
                        }
                    )
                if exit_time:
                    markers.append(
                        {
                            "time": to_unix(exit_time),
                            "price": exit_price,
                            "qty": qty,
                            "type": "SELL" if side == 1 else "BUY",
                            "side": side,
                            "is_entry": False,
                            "pnl": pnl,
                        }
                    )

        ohlcv = []
        for timestamp, row in df.iterrows():
            ohlcv.append(
                {
                    "time": to_unix(timestamp),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                }
            )
        ohlcv.sort(key=lambda x: x["time"])

        unique_ohlcv = []
        last_t = -1
        for bar in ohlcv:
            if bar["time"] > last_t:
                unique_ohlcv.append(bar)
                last_t = bar["time"]

        equity_df = results.get("equity_curve", pd.DataFrame())
        equity_curve = []
        if not equity_df.empty:
            for idx, row in equity_df.iterrows():
                try:
                    actual_ts = row.get("timestamp")
                    if actual_ts is None:
                        continue
                    val = float(row.get("equity", capital))
                    equity_curve.append({"time": to_unix(actual_ts), "value": val})
                except Exception:
                    continue

        self.sessions[session_id] = {
            "session": None,
            "thread": None,
            "is_running": False,
            "mode": "BACKTEST",
            "symbol": symbol,
            "strategy": strategy_name,
            "type": "backtest",
            "result": {
                "status": "completed",
                "metrics": metrics,
                "trades": trades_payload,
                "markers": markers,
                "ohlcv": unique_ohlcv,
                "equity_curve": equity_curve,
                "capital": metrics.get("final_capital", capital),
            },
        }

        thread_local.session_id = "system"
        return session_id

    def get_all_sessions(self) -> Dict[str, Any]:
        result = {}
        for sid, state in self.sessions.items():
            result[sid] = {
                "mode": state["mode"],
                "symbol": state["symbol"],
                "strategy": state["strategy"],
                "is_running": state["is_running"],
                "type": state["type"],
            }
        return result


bot_manager = BotManager()
