import numpy as np
import pandas as pd

from config import LOOKBACK_DAYS


def compute_price_signals(etf_df: pd.DataFrame) -> pd.DataFrame:
    df = etf_df.copy()

    # Ensure long format with required columns
    if "ticker" not in df.columns or "close" not in df.columns or "date" not in df.columns:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [
                f"{c[0]}_{c[1]}" if c[1] else c[0]
                for c in df.columns
            ]

        wide_cols = [
            c for c in df.columns
            if "_" in c and c.split("_")[0] in {"close", "open", "high", "low", "volume"}
        ]

        if wide_cols:
            tickers = sorted({c.split("_")[1] for c in wide_cols})

            long_rows = []

            for ticker in tickers:
                sub = df[["date"]].copy()

                for field in ["close", "open", "high", "low", "volume"]:
                    colname = f"{field}_{ticker}"

                    if colname in df.columns:
                        sub[field] = df[colname]
                    else:
                        sub[field] = pd.NA

                sub["ticker"] = ticker
                long_rows.append(sub)

            df = pd.concat(long_rows, ignore_index=True)

        else:
            raise ValueError(
                "Input dataframe must have 'date', 'close', and 'ticker' columns "
                "or wide format columns."
            )

    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"])

    if df.empty:
        raise ValueError("No valid price data after filtering. Check ETF history.")

    df.sort_values(["ticker", "date"], inplace=True)
    df.reset_index(drop=True, inplace=True)

    slope_lookback = max(5, LOOKBACK_DAYS // 2)
    vol_lookback = LOOKBACK_DAYS * 3

    signals = []

    for ticker, group in df.groupby("ticker"):
        g = group.copy()
        g.reset_index(drop=True, inplace=True)

        close = g["close"].astype(float)

        g["daily_ret"] = close.pct_change(fill_method=None)

        g["ret_lookback"] = close.pct_change(
            periods=LOOKBACK_DAYS,
            fill_method=None,
        )

        g["ma_short"] = close.rolling(
            window=LOOKBACK_DAYS,
            min_periods=LOOKBACK_DAYS,
        ).mean()

        g["ma_long"] = close.rolling(
            window=LOOKBACK_DAYS * 3,
            min_periods=LOOKBACK_DAYS * 3,
        ).mean()

        g["trend_up"] = g["ma_short"] > g["ma_long"]

        # Moving-average steepness over a shorter slope window
        g["ma_slope"] = g["ma_short"].pct_change(
            periods=slope_lookback,
            fill_method=None,
        )

        # Recent realised volatility
        g["rolling_vol"] = g["daily_ret"].rolling(
            window=vol_lookback,
            min_periods=vol_lookback,
        ).std()

        # Scale daily volatility to the same horizon as the MA slope
        g["horizon_vol"] = g["rolling_vol"] * np.sqrt(slope_lookback)

        # Vol-normalised MA steepness
        g["ma_slope_z"] = g["ma_slope"] / g["horizon_vol"]

        g["ma_slope_z"] = g["ma_slope_z"].replace([np.inf, -np.inf], np.nan)

        signals.append(g)

    if not signals:
        raise ValueError("No signals generated. Check price data integrity.")

    return pd.concat(signals, ignore_index=True)