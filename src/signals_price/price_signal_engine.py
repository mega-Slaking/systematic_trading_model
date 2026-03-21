import pandas as pd
from config import LOOKBACK_DAYS

def compute_price_signals(etf_df: pd.DataFrame) -> pd.DataFrame:
    
    df = etf_df.copy()

    # Ensure long format with required columns
    if "ticker" not in df.columns or "close" not in df.columns or "date" not in df.columns:
        # Handle wide format
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [
                f"{c[0]}_{c[1]}" if c[1] else c[0]
                for c in df.columns
            ]

        wide_cols = [c for c in df.columns if "_" in c and c.split("_")[0] in {"close","open","high","low","volume"}]

        if wide_cols:
            tickers = sorted({c.split("_")[1] for c in wide_cols})

            long_rows = []
            for t in tickers:
                sub = df[["date"]].copy()

                for field in ["close", "open", "high", "low", "volume"]:
                    colname = f"{field}_{t}"
                    if colname in df.columns:
                        sub[field] = df[colname]
                    else:
                        sub[field] = pd.NA

                sub["ticker"] = t
                long_rows.append(sub)

            df = pd.concat(long_rows, ignore_index=True)
        else:
            raise ValueError("Input dataframe must have 'date', 'close', and 'ticker' columns or wide format columns")

    # Ensure correct dtypes
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"])  # Remove rows with invalid close prices
    
    if df.empty:
        raise ValueError("No valid price data after filtering. Check ETF history.")
    
    df.sort_values(["ticker", "date"], inplace=True)
    df.reset_index(drop=True, inplace=True)

    signals = []
    for ticker, group in df.groupby("ticker"):
        g = group.copy()
        g.reset_index(drop=True, inplace=True)

        close = g["close"].astype(float)

        g["ret_lookback"] = close.pct_change(LOOKBACK_DAYS,fill_method=None)
        g["ma_short"] = close.rolling(LOOKBACK_DAYS).mean()
        g["ma_long"] = close.rolling(LOOKBACK_DAYS * 3).mean()
        g["trend_up"] = g["ma_short"] > g["ma_long"]

        signals.append(g)

    if not signals:
        raise ValueError("No signals generated. Check price data integrity.")
    
    return pd.concat(signals, ignore_index=True)
