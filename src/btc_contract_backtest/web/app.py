import asyncio
import os
import logging
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from btc_contract_backtest.web.bot_manager import bot_manager

# Set up logging for the web server
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("btc_contract_backtest.web.server")

app = FastAPI(title="BTC Trading Engine Dashboard")

# Define the root of our web static files
# We'll put them in src/btc_contract_backtest/web/static
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

class BotStartConfig(BaseModel):
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

@app.get("/")
async def get_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>Dashboard Static Files Not Found</h1><p>Please ensure index.html exists in src/btc_contract_backtest/web/static/</p>")

@app.post("/api/bot/start")
async def start_bot(config: BotStartConfig):
    try:
        bot_manager.start_bot(config.dict())
        return {"message": "Bot started successfully", "status": "running"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {str(e)}")

@app.post("/api/bot/stop")
async def stop_bot():
    try:
        bot_manager.stop_bot()
        return {"message": "Bot stopped successfully", "status": "stopped"}
    except Exception as e:
        logger.error(f"Error stopping bot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to stop bot: {str(e)}")

@app.get("/api/bot/status")
async def get_status():
    return bot_manager.get_status()

@app.get("/api/bot/trades")
async def get_trades():
    return bot_manager.get_trades()

@app.get("/api/bot/performance")
async def get_performance():
    return bot_manager.get_performance()

@app.get("/api/strategies")
async def get_strategies():
    # This is a bit of a hack but it gets the registered names from build_strategy
    # by inspecting the function or just returning a curated list.
    # For now, let's return the common ones.
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
        "buy_and_hold_long"
    ]

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established")
    
    # We'll send live data and logs through this channel
    try:
        # Start a broadcaster task for this websocket
        while True:
            # Check for bot status updates
            status = bot_manager.get_status()
            
            # Try to get logs from the queue
            try:
                log_entries = []
                while not bot_manager.log_queue.empty():
                    log_entries.append(await bot_manager.log_queue.get())
                
                if log_entries or status:
                    payload = {
                        "type": "update",
                        "status": status,
                        "logs": log_entries
                    }
                    await websocket.send_json(payload)
            except Exception as e:
                # If we get a "send" error, the socket is likely gone
                logger.error(f"WS error: {e}")
                break
                
            await asyncio.sleep(1) # Frequency of updates
            
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WS error: {e}")

# Mount static files (ensure this is last so it doesn't override other routes)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
