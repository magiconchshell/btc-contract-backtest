#!/bin/bash
# Convenient script to start the trading dashboard using the project's virtual environment

echo "🚀 Starting MAGIC CONCH SHELL Trading Dashboard..."
./.venv/bin/python3 -m uvicorn src.btc_contract_backtest.web.app:app --host 0.0.0.0 --port 8000 --reload
