from dataclasses import dataclass, field

import numpy as np
import pandas as pd

'''
This exists so covariance methods don't create returns_wide everytime they're called. Instead, returns_wide
is called once and the result is passed to methods to use making computation speed faster.
I have also added covariance caching to avoid recomputing covariance if the same window is 
requested multiple times to speed up computation.
'''


@dataclass
class CovarianceReturnsView:
    returns_wide: pd.DataFrame
    dates: pd.DatetimeIndex
    tickers: list[str]
    covariance_cache: dict[tuple, object] = field(default_factory=dict, init=False, repr=False)
    covariance_cache_hits: int = field(default=0, init=False)
    covariance_cache_misses: int = field(default=0, init=False)

    @classmethod
    def from_etf_history(
        cls,
        *,
        etf_history: pd.DataFrame,
        tickers: list[str],
    ) -> "CovarianceReturnsView":
        required_columns = {"date", "ticker", "close"}
        missing_columns = required_columns.difference(etf_history.columns)

        if missing_columns:
            raise ValueError(
                f"ETF history is missing required columns: {sorted(missing_columns)}"
            )

        df = etf_history[["date", "ticker", "close"]].copy()

        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df = df[df["ticker"].isin(tickers)]
        df = df.sort_values(["ticker", "date"])

        df["return"] = df.groupby("ticker")["close"].pct_change()

        returns_wide = df.pivot(
            index="date",
            columns="ticker",
            values="return",
        )

        available_tickers = [
            ticker for ticker in tickers
            if ticker in returns_wide.columns
        ]

        returns_wide = returns_wide[available_tickers]
        returns_wide = returns_wide.dropna()
        returns_wide = returns_wide.sort_index()

        return cls(
            returns_wide=returns_wide,
            dates=returns_wide.index,
            tickers=available_tickers,
        )

    def get_window(
        self,
        *,
        as_of_date,
        tickers: list[str],
        lookback_days: int,
    ) -> tuple[pd.DataFrame, list[str], list[str]]:
        as_of_date = pd.Timestamp(as_of_date).tz_localize(None)

        available_tickers = [
            ticker for ticker in tickers
            if ticker in self.returns_wide.columns
        ]

        invalid_tickers = [
            ticker for ticker in tickers
            if ticker not in self.returns_wide.columns
        ]

        if not available_tickers:
            return pd.DataFrame(), [], invalid_tickers

        end_idx = self.dates.searchsorted(as_of_date, side="left")

        window_returns = self.returns_wide.iloc[:end_idx]
        window_returns = window_returns[available_tickers]
        window_returns = window_returns.tail(lookback_days)

        return window_returns, available_tickers, invalid_tickers

    def get_window_np(
        self,
        *,
        as_of_date,
        tickers: list[str],
        lookback_days: int,
    ) -> tuple[np.ndarray, list[str], list[str]]:
        window_returns, available_tickers, invalid_tickers = self.get_window(
            as_of_date=as_of_date,
            tickers=tickers,
            lookback_days=lookback_days,
        )

        if window_returns.empty:
            return (
                np.empty((0, 0), dtype=np.float64),
                available_tickers,
                invalid_tickers,
            )

        returns_np = np.ascontiguousarray(
            window_returns.to_numpy(dtype=np.float64)
        )

        return returns_np, available_tickers, invalid_tickers
    

    def get_cached_covariance(self, cache_key: tuple):
        cached = self.covariance_cache.get(cache_key)

        if cached is not None:
            self.covariance_cache_hits += 1
        else:
            self.covariance_cache_misses += 1

        return cached

    def set_cached_covariance(self, cache_key: tuple, estimate) -> None:
        self.covariance_cache[cache_key] = estimate

    def clear_covariance_cache(self) -> None:
        self.covariance_cache.clear()
        self.covariance_cache_hits = 0
        self.covariance_cache_misses = 0