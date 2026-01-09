import os
import matplotlib.pyplot as plt

from .plots import plot_etf_vs_macro, plot_yield_curve


def generate_daily_report(
    etf_df,
    macro_df,
    price_signals,
    macro_signals,
    decision
):
    output_dir = "output/reports"
    os.makedirs(output_dir, exist_ok=True)

    for ticker in ["TLT", "AGG", "SHY"]:
        fig = plot_etf_vs_macro(
            etf_df,
            macro_df,
            ticker,
            macro_col="cpi_yoy",
            macro_label="CPI YoY"
        )
        fig.savefig(f"{output_dir}/{ticker.lower()}_vs_cpi.png")
        plt.close(fig)

    for ticker in ["TLT", "AGG", "SHY"]:
        fig = plot_etf_vs_macro(
            etf_df,
            macro_df,
            ticker,
            macro_col="pmi",
            macro_label="PMI"
        )
        fig.savefig(f"{output_dir}/{ticker.lower()}_vs_pmi.png")
        plt.close(fig)

    fig = plot_yield_curve(macro_df)
    fig.savefig(f"{output_dir}/yield_curve.png")
    plt.close(fig)
