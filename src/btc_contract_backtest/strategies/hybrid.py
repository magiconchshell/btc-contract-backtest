import pandas as pd
from .base import BaseStrategy


class VotingHybridStrategy(BaseStrategy):
    def __init__(self, strategies, required_votes=1):
        self.strategies = strategies
        self.required_votes = required_votes

    def name(self) -> str:
        return "voting_hybrid"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["long_votes"] = 0
        df["short_votes"] = 0
        for strategy in self.strategies:
            out = strategy.generate_signals(df.copy())
            df.loc[out["signal"] == 1, "long_votes"] += 1
            df.loc[out["signal"] == -1, "short_votes"] += 1
        df["signal"] = 0
        df.loc[df["long_votes"] >= self.required_votes, "signal"] = 1
        df.loc[df["short_votes"] >= self.required_votes, "signal"] = -1
        return df
