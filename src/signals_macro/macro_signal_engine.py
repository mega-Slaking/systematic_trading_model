import pandas as pd


def compute_macro_signals(macro_df: pd.DataFrame) -> pd.DataFrame:
    df = macro_df.copy()
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # ------------------------------------------------------------
    # Core derived macro fields
    # ------------------------------------------------------------

    df["cpi_yoy"] = df["cpi"].pct_change(periods=12, fill_method=None)
    df["core_cpi_yoy"] = df["core_cpi"].pct_change(periods=12, fill_method=None)

    df["cpi_yoy_direction"] = df["cpi_yoy"].diff()
    df["cpi_yoy_acceleration"] = df["cpi_yoy_direction"].diff()

    df["core_cpi_direction"] = df["core_cpi_yoy"].diff()
    df["core_cpi_acceleration"] = df["core_cpi_direction"].diff()

    df["yield_curve"] = df["gs10"] - df["gs2"]

    # FEDFUNDS is in percent, CPI YoY is decimal, so multiply CPI by 100
    df["real_policy_rate"] = df["fed_funds"] - (df["core_cpi_yoy"] * 100)

    # ------------------------------------------------------------
    # Inflation signals
    # ------------------------------------------------------------

    df["cpi_direction_down"] = df["cpi_yoy_direction"] < 0
    df["cpi_accel_down"] = df["cpi_yoy_acceleration"] < 0

    df["core_cpi_direction_down"] = df["core_cpi_direction"] < 0
    df["core_cpi_accel_down"] = df["core_cpi_acceleration"] < 0

    df["disinflation"] = (
        df["cpi_direction_down"]
        & df["cpi_accel_down"]
        & df["core_cpi_direction_down"]
    )

    df["inflation_rising"] = (
        (df["cpi_yoy_direction"] > 0)
        | (df["core_cpi_direction"] > 0)
    )

    # ------------------------------------------------------------
    # Growth signals
    # ------------------------------------------------------------

    df["pmi_direction"] = df["pmi"].diff()

    #This pmi is actually cfnai -> below 0 suggests below-trend growth, if you use real pmi change level threshold to < 50
    df["growth_slowing"] = (
        (df["pmi"] < 0)
        | (df["pmi_direction"] < 0)
    )

    # Payrolls: use 3-month change and YoY growth as extra labour context
    df["payrolls_3m_change"] = df["payrolls"].diff(3)
    df["payrolls_yoy"] = df["payrolls"].pct_change(periods=12, fill_method=None)

    df["payrolls_weakening"] = df["payrolls_3m_change"] < 0

    # ------------------------------------------------------------
    # Labour signals
    # ------------------------------------------------------------

    df["unemployment_direction"] = df["unemployment"].diff()

    df["labor_weakening"] = (
        (df["unemployment_direction"] > 0)
        | df["payrolls_weakening"]
    )

    df["jobless_claims_ma3"] = df["jobless_claims"].rolling(
        window=3,
        min_periods=3,
    ).mean()

    df["jobless_claims_direction"] = df["jobless_claims_ma3"].diff()

    df["jobless_rising"] = df["jobless_claims_direction"] > 0

    # ------------------------------------------------------------
    # Curve / policy signals
    # ------------------------------------------------------------

    df["curve_inverted"] = df["yield_curve"] < 0

    df["fed_funds_direction"] = df["fed_funds"].diff()

    df["real_policy_rate_direction"] = df["real_policy_rate"].diff()

    df["real_rate_tight"] = (
        (df["real_policy_rate"] > 0)
        & (df["real_policy_rate_direction"] > 0)
    )

    # ------------------------------------------------------------
    # Credit stress signal
    # ------------------------------------------------------------

    # Supports either old hy_oas or replacement credit_spread column.
    if "credit_spread" in df.columns:
        spread_col = "credit_spread"
    elif "hy_oas" in df.columns:
        spread_col = "hy_oas"
    else:
        spread_col = None

    if spread_col is not None:
        df["credit_spread"] = df[spread_col]
        df["credit_spread_direction"] = df["credit_spread"].diff()
        df["credit_spread_widening"] = df["credit_spread_direction"] > 0
    else:
        df["credit_spread"] = pd.NA
        df["credit_spread_direction"] = pd.NA
        df["credit_spread_widening"] = False

    # Keep old downstream name for compatibility
    df["hy_spreading_widening"] = df["credit_spread_widening"]

    # ------------------------------------------------------------
    # Sentiment / confidence signal
    # ------------------------------------------------------------

    # UMCSENT levels move through time, so rolling percentile is better
    # than a hard 90 threshold.
    df["consumer_sentiment_ma12"] = df["consumer_sentiment"].rolling(
        window=12,
        min_periods=6,
    ).mean()

    df["consumer_sentiment_baseline"] = df["consumer_sentiment"].rolling(
        window=120,
        min_periods=24,
    ).median()

    df["confidence_low"] = (
        df["consumer_sentiment_ma12"]
        < df["consumer_sentiment_baseline"]
    )

    # ------------------------------------------------------------
    # Higher-level regime labels for tracing / analytics
    # ------------------------------------------------------------

    df["inflation_regime"] = "NEU"
    df.loc[df["disinflation"], "inflation_regime"] = "DIS"
    df.loc[df["inflation_rising"], "inflation_regime"] = "INF"

    df["growth_regime"] = df["growth_slowing"].map({
        True: "SLOW",
        False: "OK",
    })

    df["labour_regime"] = df["labor_weakening"].map({
        True: "WEAK",
        False: "OK",
    })

    df["curve_state"] = df["curve_inverted"].map({
        True: "INV",
        False: "NORM",
    })

    # ------------------------------------------------------------
    # Duration support flag
    # ------------------------------------------------------------

    df["macro_supports_duration"] = (
        df["disinflation"]
        & (
            df["growth_slowing"]
            | df["labor_weakening"]
            | df["credit_spread_widening"]
            | df["curve_inverted"]
        )
    )

    return df