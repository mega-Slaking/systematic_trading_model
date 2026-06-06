import math
import numpy as np
import pandas as pd
from arch import arch_model

from src.volatility.models import (
    VolatilityFeatureConfig,
    VolatilityFeatureSurface,
)


_SURFACE_CACHE: dict[tuple, VolatilityFeatureSurface] = {}


def build_volatility_feature_surface(
    etf_history: pd.DataFrame,
    tickers: list[str],
    config: VolatilityFeatureConfig | None = None,
    price_column: str = "close",
    use_cache: bool = True,
    lag_features_days: int = 1,
) -> VolatilityFeatureSurface:
    config = config or VolatilityFeatureConfig()

    _validate_input(etf_history, price_column)

    cache_key = _build_cache_key(
        etf_history=etf_history,
        tickers=tickers,
        config=config,
        price_column=price_column,
        lag_features_days=lag_features_days,
    )

    if use_cache and cache_key in _SURFACE_CACHE:
        return _SURFACE_CACHE[cache_key]

    returns_wide = _build_returns_wide(
        etf_history=etf_history,
        tickers=tickers,
        price_column=price_column,
    )

    feature_frames = []

    for window in config.rolling_windows:
        rolling = _compute_rolling_volatility_wide(
            returns_wide=returns_wide,
            window=window,
            min_history=config.min_history,
            annualized=config.annualized,
            annualization_factor=config.annualization_factor,
        )

        feature_frames.append(
            _wide_to_long_feature(rolling, f"rolling_{window}")
        )

    for lambda_value in config.ewma_lambdas:
        ewma = _compute_ewma_volatility_wide(
            returns_wide=returns_wide,
            ewma_lambda=lambda_value,
            min_history=config.min_history,
            annualized=config.annualized,
            annualization_factor=config.annualization_factor,
        )

        feature_frames.append(
            _wide_to_long_feature(
                ewma,
                f"ewma_{int(round(lambda_value * 100))}",
            )
        )

    if config.include_garch:
        garch = _compute_garch_volatility_wide(
            returns_wide=returns_wide,
            config=config,
        )

        feature_frames.append(_wide_to_long_feature(garch, "garch"))

    values = _combine_feature_frames(
        returns_wide=returns_wide,
        tickers=tickers,
        feature_frames=feature_frames,
    )

    values = _add_comparison_features(values, config)

    if lag_features_days > 0:
        values = _lag_feature_columns(values, lag_features_days)

    surface = VolatilityFeatureSurface(
        values=values,
        config=config,
        tickers=tickers,
        notes=[
            f"Feature columns lagged by {lag_features_days} day(s) "
            "to avoid lookahead bias."
        ],
    )

    if use_cache:
        _SURFACE_CACHE[cache_key] = surface

    return surface


def _validate_input(etf_history: pd.DataFrame, price_column: str) -> None:
    required = {"date", "ticker", price_column}
    missing = required - set(etf_history.columns)

    if missing:
        raise ValueError(f"ETF history is missing required columns: {sorted(missing)}")

    if etf_history.empty:
        raise ValueError("Cannot build volatility surface from empty ETF history.")


def _build_returns_wide(
    etf_history: pd.DataFrame,
    tickers: list[str],
    price_column: str,
) -> pd.DataFrame:
    df = etf_history.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df = df[df["ticker"].isin(tickers)].copy()

    prices_wide = (
        df.pivot_table(
            index="date",
            columns="ticker",
            values=price_column,
            aggfunc="last",
        )
        .sort_index()
        .ffill()
    )

    return prices_wide.pct_change()


def _compute_rolling_volatility_wide(
    returns_wide: pd.DataFrame,
    window: int,
    min_history: int,
    annualized: bool,
    annualization_factor: int,
) -> pd.DataFrame:
    min_periods = max(2, min(window, min_history))

    vol = returns_wide.rolling(
        window=window,
        min_periods=min_periods,
    ).std(ddof=1)

    if annualized:
        vol = vol * math.sqrt(annualization_factor)

    return vol


def _compute_ewma_volatility_wide(
    returns_wide: pd.DataFrame,
    ewma_lambda: float,
    min_history: int,
    annualized: bool,
    annualization_factor: int,
) -> pd.DataFrame:
    output = pd.DataFrame(index=returns_wide.index, columns=returns_wide.columns)

    for ticker in returns_wide.columns:
        output[ticker] = _compute_ewma_volatility_path(
            returns=returns_wide[ticker],
            ewma_lambda=ewma_lambda,
            min_history=min_history,
            annualized=annualized,
            annualization_factor=annualization_factor,
        )

    return output.astype(float)


def _compute_ewma_volatility_path(
    returns: pd.Series,
    ewma_lambda: float,
    min_history: int,
    annualized: bool,
    annualization_factor: int,
) -> pd.Series:
    if not 0.0 < ewma_lambda < 1.0:
        raise ValueError(
            f"ewma_lambda must be between 0 and 1 exclusive, got {ewma_lambda}."
        )

    clean = returns.dropna().astype(float)
    output = pd.Series(index=returns.index, dtype=float)

    if len(clean) < min_history:
        return output

    initial_returns = clean.iloc[:min_history]
    variance = float(initial_returns.var(ddof=1))

    if pd.isna(variance):
        return output

    initial_idx = clean.index[min_history - 1]
    output.loc[initial_idx] = math.sqrt(variance)

    for idx, ret in clean.iloc[min_history:].items():
        variance = ewma_lambda * variance + (1.0 - ewma_lambda) * float(ret) ** 2
        output.loc[idx] = math.sqrt(variance)

    if annualized:
        output = output * math.sqrt(annualization_factor)

    return output


def _compute_garch_volatility_wide(
    returns_wide: pd.DataFrame,
    config: VolatilityFeatureConfig,
) -> pd.DataFrame:
    output = pd.DataFrame(index=returns_wide.index, columns=returns_wide.columns)

    for ticker in returns_wide.columns:
        output[ticker] = _compute_garch_volatility_path(
            returns=returns_wide[ticker],
            config=config,
        )

    return output.astype(float)


def _compute_garch_volatility_path(
    returns: pd.Series,
    config: VolatilityFeatureConfig,
) -> pd.Series:
    """Point-in-time GARCH(1,1) volatility path.

    The expensive optimisation is refit only at the configured frequency
    (e.g. monthly). Between refits the conditional variance is rolled forward
    daily with the held parameters via the GARCH recursion:

        var_t = omega + alpha * eps_{t-1}^2 + beta * var_{t-1}

    so the feature still responds to every day's return. Setting
    garch_refit_frequency="daily" refits every day and reduces exactly to the
    point-in-time estimator in src/volatility/estimator.py.
    """
    if config.garch_p != 1 or config.garch_q != 1:
        raise ValueError(
            "Feature-surface GARCH currently supports GARCH(1,1) roll-forward "
            f"only (got p={config.garch_p}, q={config.garch_q})."
        )

    clean = returns.dropna().astype(float)

    if len(clean) < config.min_history:
        return pd.Series(index=returns.index, dtype=float)

    scale = 100.0 if config.garch_rescale_returns else 1.0
    annualizer = (
        math.sqrt(config.annualization_factor) if config.annualized else 1.0
    )

    clean_values = clean.to_numpy()
    clean_index = clean.index
    refit_keys = _garch_refit_period_keys(clean_index, config.garch_refit_frequency)

    out_values = np.full(len(clean), np.nan)

    omega = alpha = beta = None
    variance_scaled = None  # conditional variance in scaled-return units
    last_refit_key = None

    for i in range(len(clean)):
        if i + 1 < config.min_history:
            continue

        refit_key = refit_keys[i]
        need_refit = omega is None or refit_key != last_refit_key

        if need_refit:
            params = _fit_garch_params(clean.iloc[: i + 1], config, scale)

            if params is not None:
                omega, alpha, beta, variance_scaled = params
                last_refit_key = refit_key
                out_values[i] = math.sqrt(variance_scaled) / scale * annualizer
                continue

            if omega is None:
                # No successful fit yet, nothing to roll forward.
                continue
            # Fit failed but prior params exist -> fall through and roll forward.

        # Roll the conditional variance forward one day with the held params.
        prev_scaled_return = clean_values[i - 1] * scale
        variance_scaled = (
            omega
            + alpha * (prev_scaled_return ** 2)
            + beta * variance_scaled
        )
        out_values[i] = math.sqrt(variance_scaled) / scale * annualizer

    return pd.Series(out_values, index=clean_index).reindex(returns.index)


def _fit_garch_params(
    returns_through_now: pd.Series,
    config: VolatilityFeatureConfig,
    scale: float,
) -> tuple[float, float, float, float] | None:
    """Fit GARCH(1,1) on the trailing window; return (omega, alpha, beta, var)."""
    window = returns_through_now.tail(config.garch_lookback_days)

    if len(window) < config.min_history:
        return None

    model_returns = window * scale

    try:
        model = arch_model(
            model_returns,
            mean=config.garch_mean,
            vol="GARCH",
            p=config.garch_p,
            q=config.garch_q,
            dist=config.garch_dist,
            rescale=False,
        )
        result = model.fit(disp="off")
    except Exception:
        return None

    conditional_vol = result.conditional_volatility

    if conditional_vol is None or len(conditional_vol) == 0:
        return None

    last_vol = float(conditional_vol.iloc[-1])

    if pd.isna(last_vol):
        return None

    params = result.params

    try:
        omega = float(params["omega"])
        alpha = float(params["alpha[1]"])
        beta = float(params["beta[1]"])
    except (KeyError, TypeError):
        return None

    variance_scaled = last_vol ** 2  # already in scaled-return units
    return omega, alpha, beta, variance_scaled


def _garch_refit_period_keys(index: pd.Index, frequency: str) -> list:
    """Map each date to a refit-period key; a new key triggers a refit."""
    if frequency == "daily":
        return list(range(len(index)))

    idx = pd.DatetimeIndex(index)

    if frequency == "monthly":
        return list(idx.to_period("M"))

    if frequency == "weekly":
        return list(idx.to_period("W"))

    raise ValueError(f"Unsupported garch_refit_frequency: {frequency}")


def _combine_feature_frames(
    returns_wide: pd.DataFrame,
    tickers: list[str],
    feature_frames: list[pd.DataFrame],
) -> pd.DataFrame:
    base = pd.MultiIndex.from_product(
        [returns_wide.index, tickers],
        names=["date", "ticker"],
    ).to_frame(index=False)

    surface = base

    for frame in feature_frames:
        surface = surface.merge(
            frame,
            on=["date", "ticker"],
            how="left",
        )

    return surface.sort_values(["ticker", "date"]).reset_index(drop=True)


def _wide_to_long_feature(
    wide: pd.DataFrame,
    feature_name: str,
) -> pd.DataFrame:
    return (
        wide.stack(dropna=False)
        .rename(feature_name)
        .reset_index()
        .rename(columns={"level_1": "ticker"})
    )


def _add_comparison_features(
    values: pd.DataFrame,
    config: VolatilityFeatureConfig,
) -> pd.DataFrame:
    df = values.copy()

    if config.rolling_windows:
        primary_rolling = f"rolling_{config.rolling_windows[0]}"
    else:
        primary_rolling = None

    for lambda_value in config.ewma_lambdas:
        ewma_col = f"ewma_{int(round(lambda_value * 100))}"

        if primary_rolling in df.columns and ewma_col in df.columns:
            df[f"{ewma_col}_to_{primary_rolling}"] = (
                df[ewma_col] / df[primary_rolling]
            )

        if ewma_col in df.columns:
            df[f"{ewma_col}_change_5d"] = (
                df.groupby("ticker")[ewma_col]
                .pct_change(5)
                .replace([np.inf, -np.inf], np.nan)
            )

    return df


def _lag_feature_columns(
    values: pd.DataFrame,
    lag_features_days: int,
) -> pd.DataFrame:
    df = values.copy()
    feature_columns = [c for c in df.columns if c not in {"date", "ticker"}]

    df[feature_columns] = (
        df.sort_values(["ticker", "date"])
        .groupby("ticker")[feature_columns]
        .shift(lag_features_days)
    )

    return df


def _build_cache_key(
    etf_history: pd.DataFrame,
    tickers: list[str],
    config: VolatilityFeatureConfig,
    price_column: str,
    lag_features_days: int,
) -> tuple:
    df = etf_history[etf_history["ticker"].isin(tickers)].copy()
    df["date"] = pd.to_datetime(df["date"])

    return (
        tuple(sorted(tickers)),
        config.cache_key(),
        price_column,
        lag_features_days,
        str(df["date"].min()),
        str(df["date"].max()),
        len(df),
    )


def clear_volatility_feature_surface_cache() -> None:
    _SURFACE_CACHE.clear()