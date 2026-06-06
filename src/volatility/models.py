from dataclasses import dataclass, field
from typing import Dict, List, Literal, Tuple
import pandas as pd


VolatilityMethod = Literal["rolling_std", "ewma", "garch"]


@dataclass(frozen=True)
class VolatilityConfig:
    method: VolatilityMethod = "rolling_std"
    lookback_days: int = 20
    annualization_factor: int = 252
    min_history: int = 20
    ewma_lambda: float = 0.94
    garch_p: int = 1
    garch_q: int = 1
    garch_mean: str = "zero"
    garch_dist: str = "normal"
    garch_rescale_returns: bool = True
    garch_lookback_days: int = 756


@dataclass
class VolatilityRequest:
    etf_history: pd.DataFrame
    as_of_date: pd.Timestamp
    tickers: List[str]


@dataclass
class VolatilityEstimate:
    method: VolatilityMethod
    as_of_date: pd.Timestamp
    annualized: bool
    vols: Dict[str, float]
    notes: List[str] = field(default_factory=list)
    invalid_tickers: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class VolatilityFeatureConfig:
    rolling_windows: Tuple[int, ...] = (20, 60)
    ewma_lambdas: Tuple[float, ...] = (0.94, 0.97)

    include_garch: bool = False
    garch_p: int = 1
    garch_q: int = 1
    garch_mean: str = "zero"
    garch_dist: str = "normal"
    garch_rescale_returns: bool = True
    garch_lookback_days: int = 756
    garch_refit_frequency: str = "monthly"

    annualized: bool = True
    annualization_factor: int = 252
    min_history: int = 20

    def cache_key(self) -> tuple:
        return (
            self.rolling_windows,
            self.ewma_lambdas,
            self.include_garch,
            self.garch_p,
            self.garch_q,
            self.garch_mean,
            self.garch_dist,
            self.garch_rescale_returns,
            self.garch_lookback_days,
            self.garch_refit_frequency,
            self.annualized,
            self.annualization_factor,
            self.min_history,
        )


@dataclass
class VolatilityFeatureSurface:
    values: pd.DataFrame
    config: VolatilityFeatureConfig
    tickers: List[str]
    notes: List[str] = field(default_factory=list)

    def get_snapshot(self, as_of_date: pd.Timestamp) -> pd.DataFrame:
        if self.values.empty:
            return pd.DataFrame()

        as_of_date = pd.to_datetime(as_of_date)

        return (
            self.values[self.values["date"] == as_of_date]
            .copy()
            .reset_index(drop=True)
        )

    def get_ticker_snapshot(
        self,
        as_of_date: pd.Timestamp,
        ticker: str,
    ) -> pd.Series | None:
        snapshot = self.get_snapshot(as_of_date)

        if snapshot.empty:
            return None

        ticker_rows = snapshot[snapshot["ticker"] == ticker]

        if ticker_rows.empty:
            return None

        return ticker_rows.iloc[0]