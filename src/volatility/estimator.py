import math
from typing import Dict
from arch import arch_model

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
        return _estimate_ewma(request, config)

    if config.method == "garch":
        return _estimate_garch(request, config)

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
            notes=["No ETF history available before as_of_date."],
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


def _compute_ewma_variance(
    returns: pd.Series,
    ewma_lambda: float,
    min_history: int,
) -> float | None:
    clean_returns = returns.dropna().astype(float)

    if len(clean_returns) < min_history:
        return None

    if not 0.0 < ewma_lambda < 1.0:
        raise ValueError(
            f"ewma_lambda must be between 0 and 1 exclusive, got {ewma_lambda}."
        )

    initial_window = clean_returns.iloc[:min_history]
    variance = float(initial_window.var(ddof=1))

    if pd.isna(variance):
        return None

    for ret in clean_returns.iloc[min_history:]:
        variance = (
            ewma_lambda * variance
            + (1.0 - ewma_lambda) * float(ret) ** 2
        )

    return variance


def _estimate_ewma(
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

    df = df[df["date"] < as_of_date].copy()

    if df.empty:
        return VolatilityEstimate(
            method="ewma",
            as_of_date=pd.Timestamp(request.as_of_date),
            annualized=True,
            vols={},
            notes=["No ETF history available before as_of_date."],
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

        variance = _compute_ewma_variance(
            returns=returns,
            ewma_lambda=config.ewma_lambda,
            min_history=config.min_history,
        )

        if variance is None:
            invalid_tickers.append(ticker)
            notes.append(f"{ticker}: EWMA variance could not be computed.")
            continue

        vol = float(math.sqrt(variance) * annualizer)

        if pd.isna(vol):
            invalid_tickers.append(ticker)
            notes.append(f"{ticker}: EWMA volatility computed as NaN.")
            continue

        vols[ticker] = vol

    if not vols:
        notes.append("No valid volatility estimates produced.")

    return VolatilityEstimate(
        method="ewma",
        as_of_date=pd.Timestamp(request.as_of_date),
        annualized=True,
        vols=vols,
        notes=notes,
        invalid_tickers=invalid_tickers,
    )


def _compute_garch_variance(
    returns: pd.Series,
    min_history: int,
    garch_p: int,
    garch_q: int,
    mean: str,
    dist: str,
    rescale_returns: bool,
    lookback_days: int,
) -> float | None:
    clean_returns = returns.dropna().astype(float).tail(lookback_days)

    if len(clean_returns) < min_history:
        return None

    scale = 100.0 if rescale_returns else 1.0
    model_returns = clean_returns * scale

    try:
        model = arch_model(
            model_returns,
            mean=mean,
            vol="GARCH",
            p=garch_p,
            q=garch_q,
            dist=dist,
            rescale=False,
        )
        result = model.fit(disp="off")
    except Exception:
        return None

    conditional_vol = result.conditional_volatility

    if conditional_vol is None or len(conditional_vol) == 0:
        return None

    latest_vol = float(conditional_vol.iloc[-1])

    if pd.isna(latest_vol):
        return None

    variance = (latest_vol / scale) ** 2
    return variance


def _estimate_garch(
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

    df = df[df["date"] < as_of_date].copy()

    if df.empty:
        return VolatilityEstimate(
            method="garch",
            as_of_date=pd.Timestamp(request.as_of_date),
            annualized=True,
            vols={},
            notes=["No ETF history available before as_of_date."],
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

        variance = _compute_garch_variance(
            returns=returns,
            min_history=config.min_history,
            garch_p=config.garch_p,
            garch_q=config.garch_q,
            mean=config.garch_mean,
            dist=config.garch_dist,
            rescale_returns=config.garch_rescale_returns,
            lookback_days=config.garch_lookback_days,
        )

        if variance is None:
            invalid_tickers.append(ticker)
            notes.append(f"{ticker}: GARCH variance could not be computed.")
            continue

        vol = float(math.sqrt(variance) * annualizer)

        if pd.isna(vol):
            invalid_tickers.append(ticker)
            notes.append(f"{ticker}: GARCH volatility computed as NaN.")
            continue

        vols[ticker] = vol

    if not vols:
        notes.append("No valid volatility estimates produced.")

    return VolatilityEstimate(
        method="garch",
        as_of_date=pd.Timestamp(request.as_of_date),
        annualized=True,
        vols=vols,
        notes=notes,
        invalid_tickers=invalid_tickers,
    )