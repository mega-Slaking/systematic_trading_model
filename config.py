from dotenv import load_dotenv
import os

load_dotenv()

# API keys are read lazily (no import-time raise) so the package imports without
# a .env present. The consumer validates the key when it actually fetches.
# (FMP_API_KEY removed — yfinance replaced FMP, so the key is no longer used.)
FRED_API_KEY = os.getenv("FRED_API_KEY")


from src.universe import UNIVERSE
TICKERS = list(UNIVERSE)

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
#NORMAL/STRESS MODE
DRIFT_TOL = 0.02 #5% drift tolerance before rebalancing; consideration for later - could make dynamic for volatility