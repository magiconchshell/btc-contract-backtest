#!/bin/bash
# Convenient script to start the trading dashboard using the project's virtual environment
# NOTE: --reload is intentionally NOT used here. It kills the bot thread on every file save.

echo "🚀 Starting MAGIC CONCH SHELL Trading Dashboard..."
./.venv/bin/python3 -m uvicorn src.btc_contract_backtest.web.app:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info
