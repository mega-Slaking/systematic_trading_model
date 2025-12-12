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

ETF_PRICE_CSV = f"{RAW_DIR}/etf_prices.csv"
MACRO_CPI_CSV = f"{RAW_DIR}/macro_cpi.csv"

LOOKBACK_DAYS = 30