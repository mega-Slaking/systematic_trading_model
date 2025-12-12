import pandas as pd

def compute_macro_signals(macro_df: pd.DataFrame) -> pd.DataFrame:

    df = macro_df.copy()
    df.sort_values("date", inplace=True)

    df["cpi_yoy_change"] = df["cpi_yoy"].diff()
    df["cpi_yoy_accel"] = df["cpi_yoy_change"].diff()

    # Simple classifications (refine thresholds later)
    df["cpi_direction_down"] = df["cpi_yoy_change"] < 0
    df["cpi_accel_down"] = df["cpi_yoy_accel"] < 0

    # PMI (growth)
    df["pmi_change"] = df["pmi"].diff()
    df["growth_slowing"] = df["pmi_change"] < 0

    # Unemployment (labor)
    df["unemployment_change"] = df["unemployment"].diff()
    df["labor_weakening"] = df["unemployment_change"] > 0

    # Yield curve
    df["curve_inverted"] = df["yield_curve"] < 0


    return df
