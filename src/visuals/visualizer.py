import os
import matplotlib.pyplot as plt

from .plots import plot_etf_vs_macro, plot_yield_curve


# DEPRECATED: no longer wired into the live run (LiveContext.visualize is a no-op).
# Kept for reference/rollback; superseded by the HTML report under output/reports/.
def generate_daily_report(
    etf_df,
    macro_df,
    price_signals,
    macro_signals,
    decision
):
    output_dir = "output/reports"
    os.makedirs(output_dir, exist_ok=True)

    # Plot from macro_signals (raw + derived columns); cpi_yoy/yield_curve only
    # exist there, not in the raw macro_df.
    for ticker in ["TLT", "AGG", "SHY"]:
        fig = plot_etf_vs_macro(
            etf_df,
            macro_signals,
            ticker,
            macro_col="cpi_yoy",
            macro_label="CPI YoY"
        )
        plt.close(fig)
        #fig.write_image(f"{output_dir}/{ticker.lower()}_vs_cpi.png")

    for ticker in ["TLT", "AGG", "SHY"]:
        fig = plot_etf_vs_macro(
            etf_df,
            macro_signals,
            ticker,
            macro_col="pmi",
            macro_label="PMI"
        )
        plt.close(fig)
        #fig.write_image(f"{output_dir}/{ticker.lower()}_vs_pmi.png")

    fig = plot_yield_curve(macro_signals)
    plt.close(fig)
    #fig.write_image(f"{output_dir}/yield_curve.png")
