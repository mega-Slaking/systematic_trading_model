import requests
import pandas as pd
import os
from config import FRED_API_KEY, MACRO_CPI_CSV, RAW_DIR


#helper
def fetch_fred_series(series_id, name=None):

    url = (
        f"https://api.stlouisfed.org/fred/series/observations?"
        f"series_id={series_id}&api_key={FRED_API_KEY}&file_type=json"
    )

    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json().get("observations", [])

    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    if name:
        df.rename(columns={"value": name}, inplace=True)
    else:
        df.rename(columns={"value": series_id}, inplace=True)

    return df[["date", name or series_id]]


def fetch_macro_data():

    os.makedirs(RAW_DIR, exist_ok=True)

    print("Fetching macro data from FRED...")

    df_cpi = fetch_fred_series("CPIAUCSL", name="cpi")
    df_core = fetch_fred_series("CPILFESL", name="core_cpi")
    df_unrate = fetch_fred_series("UNRATE", name="unemployment")
    df_gs2 = fetch_fred_series("GS2", name="gs2")
    df_gs10 = fetch_fred_series("GS10", name="gs10")
    df_pmi = fetch_fred_series("CFNAI", name="pmi")#should change to composite weighted , this will do for now to give inflation direction

    macro = df_cpi.copy()
    for df in [df_core, df_unrate, df_gs2, df_gs10, df_pmi]:
        macro = macro.merge(df, on="date", how="outer")

    macro.sort_values("date", inplace=True)
    macro.reset_index(drop=True, inplace=True)
    CUTOFF_DATE = pd.to_datetime("2002-01-01") # only care about macroeconomic data from when the etf existed
    macro = macro[macro["date"] >= CUTOFF_DATE].reset_index(drop=True)


    #CPI YoY
    macro["cpi_yoy"] = macro["cpi"].pct_change(12)  #12-month YoY
    macro["core_cpi_yoy"] = macro["core_cpi"].pct_change(12)

    #CPI Derivatives
    macro["cpi_yoy_direction"] = macro["cpi_yoy"].diff()         #1st derivative
    macro["cpi_yoy_acceleration"] = macro["cpi_yoy_direction"].diff()  #2nd derivative

    #Core CPI derivatives
    macro["core_cpi_direction"] = macro["core_cpi_yoy"].diff()
    macro["core_cpi_acceleration"] = macro["core_cpi_direction"].diff()

    #Yield curve slope (10y - 2y)
    macro["yield_curve"] = macro["gs10"] - macro["gs2"]

    #PMI direction
    macro["pmi_direction"] = macro["pmi"].diff()

    #Unemployment direction
    macro["unemployment_direction"] = macro["unemployment"].diff()

    #Disinflation flags
    macro["disinflation"] = (
        (macro["cpi_yoy_direction"] < 0) &
        (macro["cpi_yoy_acceleration"] < 0)
    )

    #Inflation re-acceleration flag
    macro["inflation_rising"] = (
        (macro["cpi_yoy_direction"] > 0)
    )

    #Economic slowdown signal (PMI < 50 or falling)
    macro["econ_slowdown"] = (
        (macro["pmi"] < 50) |
        (macro["pmi_direction"] < 0)
    )

    #Yield curve inversion
    macro["curve_inverted"] = macro["yield_curve"] < 0

    macro.to_csv(MACRO_CPI_CSV, index=False)

    print("Macro data fetched successfully.")
    return macro
