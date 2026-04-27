from dotenv import load_dotenv
import os

load_dotenv()

FMP_API_KEY = os.getenv("FMP_API_KEY")

if FMP_API_KEY is None:
    raise RuntimeError("Missing FMP_API_KEY in .env file")

FRED_API_KEY = os.getenv("FRED_API_KEY")

if FRED_API_KEY is None:
    raise RuntimeError("Missing FRED_API_KEY in .env file")


TICKERS = ["SHY", "AGG", "TLT"]

DATA_DIR = "data"
RAW_DIR = f"{DATA_DIR}/raw"
PROC_DIR = f"{DATA_DIR}/processed"

LOOKBACK_DAYS = 30
SLIPPAGE_BPS = {
    "SHY": 0.0,
    "AGG": 0.0,
    "TLT": 0.0,
} #for now, I'm going to set these to 0 - fees depend heavily on a broker and could dismiss strategies that have potential

FEE_BPS = {
    "SHY": 0.0,
    "AGG": 0.0,
    "TLT": 0.0,
}
#for now, I'm going to set these to 0 - fees depend heavily on a broker and could dismiss strategies that have potential

MIN_TRADE_NOTIONAL = 10.0 #this changes relative to your capital - probably shouldnt hardcode; consideration for later
#NORMASL/STRRESS MODE
DRIFT_TOL = 0.02 #5% drift tolerance before rebalancing; consideration for later - could make dynamic for volatility