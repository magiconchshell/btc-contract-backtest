from __future__ import annotations

import pandas as pd

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, ExecutionConfig, LiveRiskConfig, RiskConfig
from btc_contract_backtest.runtime.trading_runtime import TradingRuntime
from btc_contract_backtest.strategies.base import BaseStrategy


class BacktestRuntime(TradingRuntime):
    def __init__(
        self,
        market_data: pd.DataFrame,
        contract: ContractSpec,
        account: AccountConfig,
        risk: RiskConfig,
        strategy: BaseStrategy,
        timeframe: str = "1h",
        execution: ExecutionConfig | None = None,
        live_risk: LiveRiskConfig | None = None,
    ):
        super().__init__(contract, account, risk, strategy, timeframe, execution, live_risk)
        self.market_data = market_data.copy()
        self.cursor = 0

    def fetch_recent_data(self, limit: int = 300):
        end = min(self.cursor + 1, len(self.market_data))
        return self.market_data.iloc[:end].copy()

    def advance(self):
        self.cursor += 1
        return self.cursor < len(self.market_data)
