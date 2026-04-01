import asyncio
import logging

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from btc_contract_backtest.web.bot_manager import bot_manager

load_dotenv()

# Set up logging for the web server
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("btc_contract_backtest.web.server")

app = FastAPI(title="BTC Trading Engine Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LiveBotConfig(BaseModel):
    capital: float = 1000.0
    leverage: int = 5
    mode: str = "PAPER"
    symbol: str = "BTC/USDT"
    timeframe: str = "1m"
    interval_seconds: int = 15
    stop_loss_pct: float = 0.04
    take_profit_pct: float = 0.10
    risk_per_trade_pct: float = 0.02
    max_pos_pct: float = 0.95
    atr_stop_mult: float = 2.5
    break_even_trigger_pct: float = 0.03
    max_retries: int = 5
    strategy: str = "sparse_meta_portfolio"


class BacktestBotConfig(BaseModel):
    capital: float = 1000.0
    leverage: int = 5
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    days: int = 30
    strategy: str = "sparse_meta_portfolio"
    stop_loss_pct: float = 0.04
    take_profit_pct: float = 0.10
    risk_per_trade_pct: float = 0.02
    max_pos_pct: float = 0.95
    atr_stop_mult: float = 2.5
    break_even_trigger_pct: float = 0.03


@app.get("/")
async def get_index():
    return {"status": "BTC Trading Engine API is running"}


@app.get("/api/sessions")
async def get_sessions():
    return bot_manager.get_all_sessions()


@app.post("/api/sessions/start")
async def start_session(config: LiveBotConfig):
    try:
        dict_conf = config.dict()
        dict_conf["mode"] = dict_conf.get("mode", "PAPER")
        session_id = bot_manager.start_bot(dict_conf)
        return {
            "message": "Bot started successfully",
            "session_id": session_id,
            "status": "running",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {str(e)}")


@app.post("/api/sessions/backtest")
async def run_backtest_session(config: BacktestBotConfig):
    try:
        dict_conf = config.dict()
        dict_conf["mode"] = "BACKTEST"
        session_id = bot_manager.run_offline_backtest(dict_conf)
        return {
            "message": "Backtest completed",
            "session_id": session_id,
            "status": "completed",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error running backtest: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to run backtest: {str(e)}")


@app.post("/api/sessions/{session_id}/stop")
async def stop_session(session_id: str):
    try:
        bot_manager.stop_bot(session_id)
        return {
            "message": "Bot stopped successfully",
            "session_id": session_id,
            "status": "stopped",
        }
    except Exception as e:
        logger.error(f"Error stopping bot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to stop bot: {str(e)}")


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    try:
        bot_manager.delete_session(session_id)
        return {
            "message": "Session deleted successfully",
            "session_id": session_id,
        }
    except Exception as e:
        logger.error(f"Error deleting session: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to delete session: {str(e)}"
        )


@app.get("/api/sessions/{session_id}/status")
async def get_status(session_id: str):
    res = bot_manager.get_status(session_id)
    if res.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Session not found")
    return res


@app.get("/api/sessions/{session_id}/trades")
async def get_trades(session_id: str):
    return bot_manager.get_trades(session_id)


@app.get("/api/sessions/{session_id}/markers")
async def get_markers(session_id: str):
    return bot_manager.get_markers(session_id)


@app.get("/api/sessions/{session_id}/performance")
async def get_performance(session_id: str):
    return bot_manager.get_performance(session_id)


@app.get("/api/strategies")
async def get_strategies():
    return [
        "sparse_meta_portfolio",
        "sma_cross",
        "macd",
        "rsi",
        "regime_filtered",
        "regime_asymmetric",
        "ema_trend",
        "long_only_regime",
        "short_lite_regime",
        "extreme_downtrend_short",
        "regime_switcher",
        "short_overlay_switcher",
        "strong_bull_long",
        "buy_and_hold_long",
        "high_frequency_test",
    ]


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established")

    bot_manager.ensure_loop(asyncio.get_running_loop())

    try:
        while True:
            sessions_data = {}
            for sid in list(bot_manager.sessions.keys()):
                sessions_data[sid] = bot_manager.get_status(sid)

            log_entries = []
            if bot_manager.log_queue:
                try:
                    while not bot_manager.log_queue.empty():
                        log_entries.append(bot_manager.log_queue.get_nowait())
                except Exception as e:
                    logger.error(f"Error draining log queue: {e}")

            if sessions_data or log_entries:
                payload = {
                    "type": "update",
                    "sessions": sessions_data,
                    "logs": log_entries,
                }
                await websocket.send_json(payload)

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WS error: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
