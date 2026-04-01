"""Live trading health & status API.

Provides HTTP endpoints for monitoring a running GovernedLiveSession:
  GET /health     — liveness check
  GET /status     — full system status
  GET /position   — current position
  GET /trades     — recent trades
  GET /orders     — active orders
  GET /metrics    — aggregated metrics
  GET /config     — current configuration

Usage:
    from btc_contract_backtest.cli.status_server import create_status_app
    app = create_status_app(session)
    uvicorn.run(app, host="0.0.0.0", port=8080)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

_SESSION = None  # Will be set via create_status_app


def create_status_app(session: Any) -> FastAPI:
    """Create a FastAPI app wired to a GovernedLiveSession."""
    global _SESSION  # noqa: PLW0603
    _SESSION = session

    app = FastAPI(
        title="BTC Trading Engine — Live Status",
        description="Health and status endpoints for the live trading engine",
        version="1.0.0",
    )

    @app.get("/health", tags=["health"])
    def health():
        """Liveness check. Returns 200 if the process is running."""
        up = _SESSION is not None
        halted = False
        if up and hasattr(_SESSION, "watchdog"):
            halted = _SESSION.watchdog.state.halted
        return JSONResponse(
            status_code=200 if up and not halted else 503,
            content={
                "status": "ok" if up and not halted else "degraded",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "halted": halted,
                "halt_reason": (
                    _SESSION.watchdog.state.halt_reason if halted else None
                ),
            },
        )

    @app.get("/status", tags=["status"])
    def status():
        """Full system status snapshot."""
        if _SESSION is None:
            return JSONResponse(
                status_code=503,
                content={"error": "session not initialized"},
            )
        s = _SESSION
        pos = s.core.position
        gov_state = s.gov_state.load() if hasattr(s, "gov_state") else {}

        # Execution state from WebSocket
        exec_state = {}
        if hasattr(s, "exchange_events"):
            exec_state = s.exchange_events.execution_state.snapshot()

        event_boundary = {}
        if hasattr(s, "event_source"):
            event_boundary = s.event_source.boundary_state()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": s.context.contract.symbol,
            "exchange_profile": s.context.contract.exchange_profile,
            "timeframe": s.context.timeframe,
            "mode": gov_state.get("mode", "unknown"),
            "governance": {
                "emergency_stop": gov_state.get("emergency_stop", False),
                "maintenance": gov_state.get("maintenance", False),
            },
            "watchdog": {
                "halted": s.watchdog.state.halted,
                "halt_reason": s.watchdog.state.halt_reason,
                "consecutive_failures": s.watchdog.state.consecutive_failures,
                "last_heartbeat_at": s.watchdog.state.last_heartbeat_at,
            },
            "position": {
                "side": pos.side,
                "quantity": pos.quantity,
                "entry_price": pos.entry_price,
                "notional": pos.notional,
                "margin_used": pos.margin_used,
                "bars_held": pos.bars_held,
                "leverage": pos.leverage,
            },
            "capital": s.core.capital,
            "trades_count": len(s.core.trades),
            "risk_events_count": len(s.core.risk_events),
            "execution_state": exec_state,
            "event_boundary": event_boundary,
        }

    @app.get("/position", tags=["trading"])
    def position():
        """Current position details."""
        if _SESSION is None:
            return JSONResponse(
                status_code=503,
                content={"error": "session not initialized"},
            )
        pos = _SESSION.core.position
        # Get mark price for unrealized PnL
        unrealized_pnl = 0.0
        mark_price = None
        try:
            ticker = _SESSION.exchange.fetch_ticker(_SESSION.context.contract.symbol)
            mark_price = float(ticker.get("last") or 0.0)
            if pos.side != 0 and pos.entry_price is not None and mark_price > 0:
                unrealized_pnl = (
                    (mark_price - pos.entry_price)
                    / pos.entry_price
                    * pos.notional
                    * pos.leverage
                    * pos.side
                )
        except Exception:  # noqa: BLE001
            pass

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "side": pos.side,
            "side_label": {0: "flat", 1: "long", -1: "short"}.get(pos.side, "unknown"),
            "quantity": pos.quantity,
            "entry_price": pos.entry_price,
            "entry_time": pos.entry_time,
            "notional": pos.notional,
            "margin_used": pos.margin_used,
            "leverage": pos.leverage,
            "bars_held": pos.bars_held,
            "peak_price": pos.peak_price,
            "trough_price": pos.trough_price,
            "break_even_armed": pos.break_even_armed,
            "partial_taken": pos.partial_taken,
            "mark_price": mark_price,
            "unrealized_pnl": unrealized_pnl,
        }

    @app.get("/trades", tags=["trading"])
    def trades(limit: int = 50):
        """Recent closed trades."""
        if _SESSION is None:
            return JSONResponse(
                status_code=503,
                content={"error": "session not initialized"},
            )
        all_trades = _SESSION.core.trades or []
        recent = all_trades[-limit:] if len(all_trades) > limit else all_trades
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_trades": len(all_trades),
            "showing": len(recent),
            "trades": recent,
        }

    @app.get("/orders", tags=["trading"])
    def orders():
        """Active orders from execution state."""
        if _SESSION is None:
            return JSONResponse(
                status_code=503,
                content={"error": "session not initialized"},
            )
        active = []
        if hasattr(_SESSION, "exchange_events"):
            active = _SESSION.exchange_events.execution_state.active_orders()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "active_orders": active,
            "count": len(active),
        }

    @app.get("/metrics", tags=["metrics"])
    def metrics():
        """Aggregated trading metrics."""
        if _SESSION is None:
            return JSONResponse(
                status_code=503,
                content={"error": "session not initialized"},
            )
        trades_list = _SESSION.core.trades or []
        total_pnl = sum(
            float(t.get("pnl_after_costs") or 0.0)
            for t in trades_list
            if t.get("pnl_after_costs") is not None
        )
        win_count = sum(1 for t in trades_list if (t.get("pnl_after_costs") or 0) > 0)
        loss_count = sum(1 for t in trades_list if (t.get("pnl_after_costs") or 0) < 0)
        total_count = len(trades_list)
        win_rate = (win_count / total_count * 100) if total_count > 0 else 0.0

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "capital": _SESSION.core.capital,
            "initial_capital": _SESSION.context.account.initial_capital,
            "total_return_pct": (
                (_SESSION.core.capital - _SESSION.context.account.initial_capital)
                / _SESSION.context.account.initial_capital
                * 100
                if _SESSION.context.account.initial_capital > 0
                else 0.0
            ),
            "total_pnl": total_pnl,
            "total_trades": total_count,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "win_rate_pct": win_rate,
            "risk_events": len(_SESSION.core.risk_events),
        }

    @app.get("/config", tags=["config"])
    def config():
        """Current engine configuration."""
        if _SESSION is None:
            return JSONResponse(
                status_code=503,
                content={"error": "session not initialized"},
            )
        ctx = _SESSION.context
        return {
            "contract": {
                "symbol": ctx.contract.symbol,
                "leverage": ctx.contract.leverage,
                "exchange_profile": ctx.contract.exchange_profile,
                "market_type": ctx.contract.market_type,
                "tick_size": ctx.contract.tick_size,
                "lot_size": ctx.contract.lot_size,
            },
            "risk": {
                "stop_loss_pct": ctx.risk.stop_loss_pct,
                "take_profit_pct": ctx.risk.take_profit_pct,
                "trailing_stop_pct": ctx.risk.trailing_stop_pct,
                "max_holding_bars": ctx.risk.max_holding_bars,
                "max_daily_loss_pct": ctx.risk.max_daily_loss_pct,
            },
            "live_risk": {
                "enable_kill_switch": ctx.live_risk.enable_kill_switch,
                "max_consecutive_failures": ctx.live_risk.max_consecutive_failures,
                "heartbeat_timeout_seconds": ctx.live_risk.heartbeat_timeout_seconds,
                "cancel_open_orders_on_shutdown": ctx.live_risk.cancel_open_orders_on_shutdown,
            },
            "timeframe": ctx.timeframe,
        }

    return app
