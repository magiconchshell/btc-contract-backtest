from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import ccxt

from btc_contract_backtest.config.models import AccountConfig, ContractSpec


class PaperTradingSession:
    def __init__(self, contract: ContractSpec, account: AccountConfig, timeframe: str = "1h", state_file: str = "paper_state.json"):
        self.contract = contract
        self.account = account
        self.timeframe = timeframe
        self.state_path = Path(state_file)
        self.exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})
        self.state = self._load()

    def _load(self):
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {"capital": self.account.initial_capital, "positions": [], "trades": []}

    def save(self):
        self.state["updated_at"] = datetime.utcnow().isoformat()
        self.state_path.write_text(json.dumps(self.state, indent=2))

    def summary(self):
        ticker = self.exchange.fetch_ticker(self.contract.symbol)
        return {
            "symbol": self.contract.symbol,
            "market_type": self.contract.market_type,
            "timeframe": self.timeframe,
            "capital": self.state["capital"],
            "open_positions": len(self.state["positions"]),
            "trades": len(self.state["trades"]),
            "mark_price": float(ticker["last"]),
        }
