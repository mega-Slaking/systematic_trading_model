import pandas as pd

def ensure_long(etf_df: pd.DataFrame) -> pd.DataFrame:
    df = etf_df.copy()

    if {"date", "ticker", "close"}.issubset(df.columns) and isinstance(df["close"], pd.Series):
        return df

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            f"{price}_{ticker}" if ticker else price
            for price, ticker in df.columns
        ]

    wide_cols = [
        c for c in df.columns
        if "_" in c and c.split("_", 1)[0] in {"close","open","high","low","volume"}
    ]

    if not wide_cols:
        raise ValueError(f"Cannot normalize ETF data, columns={df.columns}")

    tickers = sorted({c.split("_", 1)[1] for c in wide_cols})
    rows = []

    for t in tickers:
        sub = df[["date"]].copy()
        for field in ["close","open","high","low","volume"]:
            col = f"{field}_{t}"
            sub[field] = df[col] if col in df.columns else pd.NA
        sub["ticker"] = t
        rows.append(sub)

    out = pd.concat(rows, ignore_index=True)

    # FINAL HARD GUARARDS
    assert {"date", "ticker", "close"}.issubset(out.columns)
    assert isinstance(out["close"], pd.Series)

    return out
