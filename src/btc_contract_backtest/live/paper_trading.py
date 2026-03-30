from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import ccxt

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, RiskConfig
from btc_contract_backtest.strategies.base import BaseStrategy


class PaperTradingSession:
    def __init__(
        self,
        contract: ContractSpec,
        account: AccountConfig,
        risk: RiskConfig,
        strategy: BaseStrategy,
        timeframe: str = "1h",
        state_file: str = "paper_state.json",
    ):
        self.contract = contract
        self.account = account
        self.risk = risk
        self.strategy = strategy
        self.timeframe = timeframe
        self.state_path = Path(state_file)
        self.exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})
        self.state = self._load()

    def _load(self):
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {
            "capital": self.account.initial_capital,
            "positions": [],
            "trades": [],
            "updated_at": None,
        }

    def save(self):
        self.state["updated_at"] = datetime.utcnow().isoformat()
        self.state_path.write_text(json.dumps(self.state, indent=2))

    def fetch_recent_data(self, limit: int = 300):
        rows = self.exchange.fetch_ohlcv(self.contract.symbol, timeframe=self.timeframe, limit=limit)
        import pandas as pd
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df

    def mark_price(self) -> float:
        ticker = self.exchange.fetch_ticker(self.contract.symbol)
        return float(ticker["last"])

    def _maintenance_margin(self, notional: float) -> float:
        return notional * self.risk.maintenance_margin_ratio

    def _open_position(self, side: int, price: float):
        capital = self.state["capital"]
        notional = capital * self.risk.max_position_notional_pct
        position = {
            "side": side,
            "entry_price": price,
            "entry_time": datetime.utcnow().isoformat(),
            "notional": notional,
            "leverage": self.contract.leverage,
            "margin_used": notional / self.contract.leverage,
            "bars_held": 0,
            "peak_price": price,
            "trough_price": price,
        }
        self.state["positions"] = [position]
        self.save()
        return position

    def _close_position(self, price: float, reason: str):
        if not self.state["positions"]:
            return None
        pos = self.state["positions"].pop(0)
        side = pos["side"]
        gross = ((price - pos["entry_price"]) / pos["entry_price"]) * pos["notional"] * pos["leverage"] * side
        fees = pos["notional"] * self.account.taker_fee_rate * 2
        funding = pos["notional"] * (self.account.funding_rate_annual / 365)
        pnl = gross - fees - funding
        self.state["capital"] += pnl
        trade = {
            "entry_time": pos["entry_time"],
            "exit_time": datetime.utcnow().isoformat(),
            "entry_price": pos["entry_price"],
            "exit_price": price,
            "side": side,
            "notional": pos["notional"],
            "leverage": pos["leverage"],
            "bars_held": pos.get("bars_held", 0),
            "gross_pnl": gross,
            "fees": fees,
            "funding": funding,
            "pnl": pnl,
            "reason": reason,
        }
        self.state["trades"].append(trade)
        self.save()
        return trade

    def _check_liquidation(self, price: float) -> Optional[dict]:
        if not self.state["positions"]:
            return None
        pos = self.state["positions"][0]
        side = pos["side"]
        unrealized = ((price - pos["entry_price"]) / pos["entry_price"]) * pos["notional"] * pos["leverage"] * side
        equity = self.state["capital"] + unrealized
        maintenance = self._maintenance_margin(pos["notional"])
        if equity <= maintenance:
            trade = self._close_position(price, reason="liquidation")
            return trade
        return None

    def step(self):
        df = self.fetch_recent_data()
        signal_df = self.strategy.generate_signals(df)
        latest = signal_df.iloc[-1]
        price = float(latest["close"])
        signal = int(latest.get("signal", 0))

        liquidated = self._check_liquidation(price)
        if liquidated:
            return {"event": "liquidation", "trade": liquidated, "summary": self.summary()}

        current_pos = self.state["positions"][0] if self.state["positions"] else None
        if current_pos is None and signal != 0:
            pos = self._open_position(signal, price)
            return {"event": "open", "position": pos, "summary": self.summary()}

        if current_pos is not None:
            current_pos["bars_held"] = current_pos.get("bars_held", 0) + 1
            current_pos["peak_price"] = max(current_pos.get("peak_price", price), price)
            current_pos["trough_price"] = min(current_pos.get("trough_price", price), price)
            current_side = current_pos["side"]
            pnl_pct = ((price - current_pos["entry_price"]) / current_pos["entry_price"]) * current_side

            if self.risk.stop_loss_pct is not None and pnl_pct <= -self.risk.stop_loss_pct:
                trade = self._close_position(price, reason="stop_loss")
                return {"event": "close", "trade": trade, "summary": self.summary()}

            if self.risk.take_profit_pct is not None and pnl_pct >= self.risk.take_profit_pct:
                trade = self._close_position(price, reason="take_profit")
                return {"event": "close", "trade": trade, "summary": self.summary()}

            if self.risk.trailing_stop_pct is not None:
                if current_side == 1 and price <= current_pos["peak_price"] * (1 - self.risk.trailing_stop_pct):
                    trade = self._close_position(price, reason="trailing_stop")
                    return {"event": "close", "trade": trade, "summary": self.summary()}
                if current_side == -1 and price >= current_pos["trough_price"] * (1 + self.risk.trailing_stop_pct):
                    trade = self._close_position(price, reason="trailing_stop")
                    return {"event": "close", "trade": trade, "summary": self.summary()}

            if self.risk.max_holding_bars is not None and current_pos["bars_held"] >= self.risk.max_holding_bars:
                trade = self._close_position(price, reason="time_exit")
                return {"event": "close", "trade": trade, "summary": self.summary()}

            if signal == 0:
                trade = self._close_position(price, reason="flat_signal")
                return {"event": "close", "trade": trade, "summary": self.summary()}
            if signal != current_side:
                closed = self._close_position(price, reason="reverse_signal")
                opened = self._open_position(signal, price)
                return {"event": "reverse", "closed": closed, "opened": opened, "summary": self.summary()}

        self.save()
        return {"event": "hold", "summary": self.summary()}

    def summary(self):
        current = self.mark_price()
        unrealized = 0.0
        if self.state["positions"]:
            pos = self.state["positions"][0]
            unrealized = ((current - pos["entry_price"]) / pos["entry_price"]) * pos["notional"] * pos["leverage"] * pos["side"]
        return {
            "symbol": self.contract.symbol,
            "market_type": self.contract.market_type,
            "timeframe": self.timeframe,
            "capital": self.state["capital"],
            "open_positions": len(self.state["positions"]),
            "trades": len(self.state["trades"]),
            "mark_price": current,
            "unrealized_pnl": unrealized,
        }

    def run_loop(self, interval_seconds: int = 60, iterations: Optional[int] = None):
        count = 0
        while True:
            event = self.step()
            print(json.dumps(event, indent=2, default=str))
            count += 1
            if iterations is not None and count >= iterations:
                break
            time.sleep(interval_seconds)
