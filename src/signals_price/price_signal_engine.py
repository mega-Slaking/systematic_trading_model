import pandas as pd
from config import LOOKBACK_DAYS

def compute_price_signals(etf_df: pd.DataFrame) -> pd.DataFrame:
    
    df = etf_df.copy()

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

    df["date"] = pd.to_datetime(df["date"])
    df.sort_values(["ticker", "date"], inplace=True)

    signals = []
    for ticker, group in df.groupby("ticker"):
        g = group.copy()

        close = g["close"].astype(float)

        g["ret_lookback"] = close.pct_change(LOOKBACK_DAYS)
        g["ma_short"] = close.rolling(LOOKBACK_DAYS).mean()
        g["ma_long"] = close.rolling(LOOKBACK_DAYS * 3).mean()
        g["trend_up"] = g["ma_short"] > g["ma_long"]

        signals.append(g)

    return pd.concat(signals, ignore_index=True)
