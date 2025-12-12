import requests
import pandas as pd
from config import FRED_API_KEY


def fetch_fred(series_id):
    url = (
        f"https://api.stlouisfed.org/fred/series/observations?"
        f"series_id={series_id}&api_key={FRED_API_KEY}&file_type=json"
    )
    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()["observations"]

    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df[["date", "value"]]

# Test CPI
df_cpi = fetch_fred("CPIAUCSL")
print(df_cpi.head())
