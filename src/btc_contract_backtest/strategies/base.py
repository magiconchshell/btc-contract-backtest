from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return df with signal column: 1 long, -1 short, 0 flat/hold."""
        raise NotImplementedError
