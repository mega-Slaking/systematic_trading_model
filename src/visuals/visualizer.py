import os
import pandas as pd
import matplotlib.pyplot as plt
from config import PROC_DIR

def generate_daily_report(etf_df, macro_df, price_signals, macro_signals, decision):
    os.makedirs("output/reports", exist_ok=True)

    # TLT price vs CPI
    fig, ax1 = plt.subplots()

    tlt = etf_df[etf_df["ticker"] == "TLT"].sort_values("date")
    ax1.plot(tlt["date"], tlt["close"], label="TLT Price")
    ax1.set_ylabel("TLT Price")

    ax2 = ax1.twinx()
    ax2.plot(macro_df["date"], macro_df["cpi_yoy"], linestyle="--", label="CPI YoY")
    ax2.set_ylabel("CPI YoY")

    plt.title("TLT vs CPI YoY")
    fig.tight_layout()
    fig.savefig("output/reports/tlt_vs_cpi.png")
    plt.close(fig)
    #
    fig, ax1 = plt.subplots()

    agg = etf_df[etf_df["ticker"] == "AGG"].sort_values("date")
    ax1.plot(agg["date"], agg["close"], label="AGG Price")
    ax1.set_ylabel("AGG Price")

    ax2 = ax1.twinx()
    ax2.plot(macro_df["date"], macro_df["cpi_yoy"], linestyle="--", label="CPI YoY")
    ax2.set_ylabel("CPI YoY")

    plt.title("AGG vs CPI YoY")
    fig.tight_layout()
    fig.savefig("output/reports/agg_vs_cpi.png")
    plt.close(fig)
    #
    fig, ax1 = plt.subplots()

    shy = etf_df[etf_df["ticker"] == "SHY"].sort_values("date")
    ax1.plot(shy["date"], shy["close"], label="SHY Price")
    ax1.set_ylabel("SHY Price")

    ax2 = ax1.twinx()
    ax2.plot(macro_df["date"], macro_df["cpi_yoy"], linestyle="--", label="CPI YoY")
    ax2.set_ylabel("CPI YoY")

    plt.title("SHY vs CPI YoY")
    fig.tight_layout()
    fig.savefig("output/reports/shy_vs_cpi.png")
    plt.close(fig)

    fig, ax = plt.subplots()
    ax.plot(macro_df["date"], macro_df["gs10"], label="10Y")
    ax.plot(macro_df["date"], macro_df["gs2"], label="2Y")

    ax.fill_between(
        macro_df["date"],
        macro_df["gs10"] - macro_df["gs2"],
        0,
        alpha=0.2,
        label="10Y–2Y Spread"
    )

    ax.axhline(0, color="black", linestyle="--", linewidth=1)
    ax.set_ylabel("Yield (%)")
    ax.set_title("US Yield Curve (10Y vs 2Y)")
    ax.legend()

    fig.tight_layout()
    fig.savefig("output/reports/yield_curve.png")
    plt.close(fig)