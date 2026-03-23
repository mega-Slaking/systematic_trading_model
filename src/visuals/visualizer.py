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
        plt.close(fig)
        #fig.write_image(f"{output_dir}/{ticker.lower()}_vs_cpi.png")

    for ticker in ["TLT", "AGG", "SHY"]:
        fig = plot_etf_vs_macro(
            etf_df,
            macro_df,
            ticker,
            macro_col="pmi",
            macro_label="PMI"
        )
        plt.close(fig)
        #fig.write_image(f"{output_dir}/{ticker.lower()}_vs_pmi.png")

    fig = plot_yield_curve(macro_df)
    plt.close(fig)
    #fig.write_image(f"{output_dir}/yield_curve.png")
