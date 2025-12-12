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
