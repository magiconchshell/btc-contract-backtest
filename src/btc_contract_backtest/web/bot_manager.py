import asyncio
import logging
import threading
from typing import Any, Optional, Dict
from datetime import datetime, timezone

from btc_contract_backtest.config.models import (
    ContractSpec, AccountConfig, RiskConfig,
    ExecutionConfig, LiveRiskConfig
)
from btc_contract_backtest.live.live_session import GovernedLiveSession
from btc_contract_backtest.live.governance import TradingMode
from btc_contract_backtest.strategies import build_strategy

logger = logging.getLogger("btc_contract_backtest.web.bot_manager")

class QueueHandler(logging.Handler):
    def __init__(self, queue: asyncio.Queue):
        super().__init__()
        self.queue = queue

    def emit(self, record):
        try:
            msg = self.format(record)
            # Use call_soon_threadsafe because loggers can be called from any thread
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(self.queue.put_nowait, {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": record.levelname,
                    "message": msg,
                    "logger": record.name
                })
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
        self.session: Optional[GovernedLiveSession] = None
        self.thread: Optional[threading.Thread] = None
        self.log_queue = asyncio.Queue(maxsize=1000)
        self.is_running = False
        
        # Attach log handler to the root or package logger
        root_logger = logging.getLogger("btc_contract_backtest")
        handler = QueueHandler(self.log_queue)
        handler.setFormatter(logging.Formatter('%(message)s'))
        root_logger.addHandler(handler)

    def start_bot(self, config: Dict[str, Any]):
        if self.is_running:
            raise ValueError("Bot is already running")

        # Extract configs from payload or use defaults
        capital = float(config.get("capital", 1000.0))
        leverage = int(config.get("leverage", 5))
        mode_str = config.get("mode", "PAPER").upper()
        mode = TradingMode[mode_str] if mode_str in TradingMode.__members__ else TradingMode.PAPER
        symbol = config.get("symbol", "BTC/USDT")
        timeframe = config.get("timeframe", "1h")
        interval = int(config.get("interval_seconds", 15))

        # Build objects
        contract = ContractSpec(
            symbol=symbol,
            leverage=leverage,
            exchange_profile="binance_futures_mainnet",
        )
        account = AccountConfig(initial_capital=capital)
        
        # Risk Config
        risk = RiskConfig(
            max_position_notional_pct=float(config.get("max_pos_pct", 0.95)),
            risk_per_trade_pct=float(config.get("risk_per_trade_pct", 0.02)),
            stop_loss_pct=float(config.get("stop_loss_pct", 0.04)),
            take_profit_pct=float(config.get("take_profit_pct", 0.10)),
            atr_stop_mult=float(config.get("atr_stop_mult", 2.5)),
            break_even_trigger_pct=float(config.get("break_even_trigger_pct", 0.03)),
        )
        
        execution = ExecutionConfig(default_order_type="market", enforce_exchange_constraints=True)
        live_risk = LiveRiskConfig(
            max_consecutive_failures=int(config.get("max_retries", 5)), 
            cancel_open_orders_on_shutdown=True
        )
        
        # Strategy
        strategy_name = config.get("strategy", "sparse_meta_portfolio")
        strategy = build_strategy(strategy_name)

        # Instantiate session
        self.session = GovernedLiveSession(
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

        # Run in thread
        self.is_running = True
        self.thread = threading.Thread(
            target=self.session.run_loop,
            kwargs={"interval_seconds": interval},
            daemon=True
        )
        self.thread.start()
        logger.info(f"Bot started via Web UI | Symbol: {symbol} | Mode: {mode_str}")

    def stop_bot(self):
        if not self.is_running or not self.session:
            return
        
        logger.info("Stopping bot via Web UI...")
        self.session._shutdown_event.set()
        if self.thread:
            self.thread.join(timeout=10)
        
        self.is_running = False
        self.session = None
        self.thread = None
        logger.info("Bot stopped.")

    def get_trades(self):
        if not self.session:
            return []
        return self.session.core.trades

    def get_performance(self):
        if not self.session:
            return {}
        
        trades = self.session.core.trades
        if not trades:
            return {
                "win_rate": 0,
                "profit_factor": 0,
                "total_trades": 0,
                "total_pnl": 0,
                "pnl_pct": 0,
                "avg_bars_held": 0
            }
        
        wins = [t for t in trades if (t.get("pnl_after_costs") or 0) > 0]
        losses = [t for t in trades if (t.get("pnl_after_costs") or 0) <= 0]
        
        gross_profit = sum(t.get("pnl_after_costs") or 0 for t in wins)
        gross_loss = abs(sum(t.get("pnl_after_costs") or 0 for t in losses))
        
        initial_capital = self.session.context.account.initial_capital
        total_pnl = sum(t.get("pnl_after_costs") or 0 for t in trades)
        
        return {
            "win_rate": round(len(wins) / len(trades) * 100, 2),
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0),
            "total_trades": len(trades),
            "total_pnl": round(total_pnl, 2),
            "pnl_pct": round((total_pnl / initial_capital) * 100, 2) if initial_capital > 0 else 0,
            "avg_bars_held": round(sum(t.get("bars_held", 0) for t in trades) / len(trades), 1)
        }

    def get_status(self):
        if not self.session:
            return {"status": "stopped"}
        
        # We can leverage the logic from status_server if we want, 
        # but for now let's return basic info or the whole session object if possible
        pos = self.session.core.position
        perf = self.get_performance()
        return {
            "status": "running" if not self.session._shutdown_event.is_set() else "stopping",
            "capital": round(self.session.core.capital, 2),
            "position": {
                "side": pos.side,
                "quantity": round(pos.quantity, 6),
                "entry_price": round(pos.entry_price or 0, 2),
                "pnl": round((pos.notional - (pos.quantity * (pos.entry_price or 0))) if pos.side != 0 else 0, 2)
            },
            "performance": perf,
            "config": {
                "symbol": self.session.context.contract.symbol,
                "mode": self.session.policy.mode.value,
                "leverage": self.session.context.contract.leverage,
                "strategy": self.session.strategy.name() if hasattr(self.session.strategy, 'name') else "Unknown"
            }
        }

bot_manager = BotManager()
