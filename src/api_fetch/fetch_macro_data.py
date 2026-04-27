import os
import sqlite3
import requests
import pandas as pd

from config import FRED_API_KEY, RAW_DIR
from src.storage.db_writer import insert_macro_data


CUTOFF_DATE = pd.to_datetime("2002-01-01")


FRED_SERIES = {
    "CPIAUCSL": "cpi",
    "CPILFESL": "core_cpi",
    "UNRATE": "unemployment",
    "PAYEMS": "payrolls",
    "GS2": "gs2",
    "GS10": "gs10",
    "CFNAI": "pmi",
    "FEDFUNDS": "fed_funds",
    "BAA10Y": "hy_oas", #credit_spread - proxy for true hy_oas
    "UMCSENT": "consumer_sentiment",
    "ICSA": "jobless_claims",
}


def fetch_fred_series(series_id: str, name: str) -> pd.DataFrame:
    url = (
        "https://api.stlouisfed.org/fred/series/observations?"
        f"series_id={series_id}&api_key={FRED_API_KEY}&file_type=json"
    )

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    data = resp.json().get("observations", [])
    df = pd.DataFrame(data)

    if df.empty:
        raise ValueError(f"No data returned for FRED series: {series_id}")

    df["date"] = pd.to_datetime(df["date"])
    df[name] = pd.to_numeric(df["value"], errors="coerce")

    return df[["date", name]]


def to_monthly(df: pd.DataFrame, value_col: str, method: str = "last") -> pd.DataFrame:
    df = df.copy()
    df = df.dropna(subset=[value_col])
    df = df.sort_values("date")
    df = df.set_index("date")

    if method == "mean":
        out = df[value_col].resample("MS").mean()
    elif method == "last":
        out = df[value_col].resample("MS").last()
    else:
        raise ValueError(f"Unsupported monthly aggregation method: {method}")

    return out.reset_index()


def fetch_macro_data() -> pd.DataFrame:
    os.makedirs(RAW_DIR, exist_ok=True)

    print("Fetching macro data from FRED...")

    series_frames = []

    for series_id, name in FRED_SERIES.items():
        df = fetch_fred_series(series_id, name)

        if name in {"hy_oas", "jobless_claims"}:
            df = to_monthly(df, name, method="mean")
        else:
            df = to_monthly(df, name, method="last")

        series_frames.append(df)

    macro = series_frames[0]

    for df in series_frames[1:]:
        macro = macro.merge(df, on="date", how="outer")

    macro = macro.sort_values("date").reset_index(drop=True)
    macro = macro[macro["date"] >= CUTOFF_DATE].reset_index(drop=True)

    macro["yield_curve"] = macro["gs10"] - macro["gs2"]

    macro["cpi_yoy"] = macro["cpi"].pct_change(periods=12, fill_method=None)
    macro["core_cpi_yoy"] = macro["core_cpi"].pct_change(periods=12, fill_method=None)

    macro["real_policy_rate"] = macro["fed_funds"] - (macro["core_cpi_yoy"] * 100)

    conn = sqlite3.connect("data/database.db")
    try:
        rows = macro.to_dict(orient="records")
        insert_macro_data(conn, rows)
        conn.commit()
    finally:
        conn.close()

    print("Macro data fetched successfully.")
    return macro