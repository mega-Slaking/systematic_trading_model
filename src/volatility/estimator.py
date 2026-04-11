import math
from typing import Dict

import pandas as pd

from src.volatility.models import (
    VolatilityConfig,
    VolatilityEstimate,
    VolatilityRequest,
)


def estimate_volatility(
    request: VolatilityRequest,
    config: VolatilityConfig | None = None,
) -> VolatilityEstimate:
    config = config or VolatilityConfig()

    if config.method == "rolling_std":
        return _estimate_rolling_std(request, config)

    if config.method == "ewma":
        raise NotImplementedError("EWMA volatility is not implemented yet.") #create hlpers that apply said logic

    if config.method == "garch":
        raise NotImplementedError("GARCH volatility is not implemented yet.") #create hlpers that apply said logic

    raise ValueError(f"Unsupported volatility method: {config.method}")


def _estimate_rolling_std(
    request: VolatilityRequest,
    config: VolatilityConfig,
) -> VolatilityEstimate:
    df = request.etf_history.copy()

    required_columns = {"date", "ticker", "close"}
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        raise ValueError(
            f"ETF history is missing required columns: {sorted(missing_columns)}"
        )

    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    as_of_date = pd.Timestamp(request.as_of_date).tz_localize(None)

    df = df[df["date"] < as_of_date].copy() #can't use =<, that results in look-ahead bias

    if df.empty:
        return VolatilityEstimate(
            method="rolling_std",
            as_of_date=pd.Timestamp(request.as_of_date),
            annualized=True,
            vols={},
            notes=["No ETF history available on or before as_of_date."],
            invalid_tickers=list(request.tickers),
        )

    df = df.sort_values(["ticker", "date"]).copy()
    df["return"] = df.groupby("ticker")["close"].pct_change()

    vols: Dict[str, float] = {}
    invalid_tickers: list[str] = []
    notes: list[str] = []

    annualizer = math.sqrt(config.annualization_factor)

    for ticker in request.tickers:
        g = df[df["ticker"] == ticker].copy()

        if g.empty:
            invalid_tickers.append(ticker)
            notes.append(f"{ticker}: no price history available.")
            continue

        returns = g["return"].dropna()

        if len(returns) < config.min_history:
            invalid_tickers.append(ticker)
            notes.append(
                f"{ticker}: insufficient return history "
                f"({len(returns)} < {config.min_history})."
            )
            continue

        window_returns = returns.tail(config.lookback_days)

        if len(window_returns) < config.min_history:
            invalid_tickers.append(ticker)
            notes.append(
                f"{ticker}: insufficient lookback history after tail selection "
                f"({len(window_returns)} < {config.min_history})."
            )
            continue

        vol = float(window_returns.std(ddof=1) * annualizer) #computes here

        if pd.isna(vol):
            invalid_tickers.append(ticker)
            notes.append(f"{ticker}: rolling volatility computed as NaN.")
            continue

        vols[ticker] = vol

    if not vols:
        notes.append("No valid volatility estimates produced.")

    return VolatilityEstimate(
        method="rolling_std",
        as_of_date=pd.Timestamp(request.as_of_date),
        annualized=True,
        vols=vols,
        notes=notes,
        invalid_tickers=invalid_tickers,
    )