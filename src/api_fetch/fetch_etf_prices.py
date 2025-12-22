import yfinance as yf
import pandas as pd
from config import TICKERS, ETF_PRICE_CSV,RAW_DIR
import os

def fetch_etf_prices():
    frames = []

    for ticker in TICKERS:
        print(f"Downloading {ticker}…")
        df = yf.download(
            ticker,
            period="max",
            interval="1d",
            auto_adjust=True,
            progress=False
        )

        df = df.reset_index()

        # Handle MultiIndex columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]

        df.columns = [c.lower().replace(" ", "_") for c in df.columns]

        if "adj_close" in df.columns:
            df["close"] = df["adj_close"]
        elif "close" in df.columns:
            df["close"] = df["close"]
        else:
            raise RuntimeError(f"No close column for {ticker}")

        df = df[["date", "close"]]
        df["ticker"] = ticker

        frames.append(df)

    all_df = pd.concat(frames, ignore_index=True)
    all_df.sort_values(["date", "ticker"], inplace=True)
    all_df.to_csv(ETF_PRICE_CSV, index=False)

    return all_df
