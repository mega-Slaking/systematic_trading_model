import matplotlib.pyplot as plt


def plot_etf_vs_macro(etf_df, macro_df, ticker, macro_col, macro_label):
    fig, ax1 = plt.subplots()

    etf = etf_df[etf_df["ticker"] == ticker].sort_values("date")
    ax1.plot(etf["date"], etf["close"], label=f"{ticker} Price")
    ax1.set_ylabel(f"{ticker} Price")

    ax2 = ax1.twinx()
    ax2.plot(
        macro_df["date"],
        macro_df[macro_col],
        linestyle="--",
        label=macro_label
    )
    ax2.set_ylabel(macro_label)

    plt.title(f"{ticker} vs {macro_label}")
    fig.tight_layout()

    return fig


def plot_yield_curve(macro_df):
    fig, ax = plt.subplots()

    ax.plot(macro_df["date"], macro_df["gs10"], label="10Y")
    ax.plot(macro_df["date"], macro_df["gs2"], label="2Y")

    spread = macro_df["gs10"] - macro_df["gs2"]
    ax.fill_between(
        macro_df["date"],
        spread,
        0,
        alpha=0.2,
        label="10Y–2Y Spread"
    )

    ax.axhline(0, color="black", linestyle="--", linewidth=1)
    ax.set_ylabel("Yield (%)")
    ax.set_title("US Yield Curve (10Y vs 2Y)")
    ax.legend()

    fig.tight_layout()
    return fig
