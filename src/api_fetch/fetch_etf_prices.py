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
            auto_adjust=True   
        )
        
        df = df.reset_index()
        df["ticker"] = ticker
        
        df.rename(columns={
            "Date": "date",
            "Close": "close",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Volume": "volume"
        }, inplace=True)

        frames.append(df)

    all_df = pd.concat(frames, ignore_index=True)
    all_df.sort_values(["ticker", "date"], inplace=True)

    os.makedirs(RAW_DIR, exist_ok=True)
    all_df.to_csv(ETF_PRICE_CSV, index=False)

    return all_df
