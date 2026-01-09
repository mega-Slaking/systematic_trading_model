import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import matplotlib.dates as mdates

OUTPUT_DIR = Path("output/reports")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def load_results(path):
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df

def plot_nav(dfs, labels, name=None):
    fig, ax = plt.subplots(figsize=(12,6))

    for df, label in zip(dfs, labels):
        ax.plot(df["date"], df["nav"], label=label)

    ax.legend()
    ax.set_title("NAV Comparison")
    ax.grid(True)

    if name:
        fig.savefig(OUTPUT_DIR / f"{name}_nav.png")

    return fig

def plot_drawdown(df, name=None):
    peak = df["nav"].cummax()
    dd = df["nav"] / peak - 1

    fig, ax = plt.subplots(figsize=(12,4))
    ax.plot(df["date"], dd)
    ax.set_title("Drawdown")
    ax.grid(True)

    if name:
        fig.savefig(OUTPUT_DIR / f"{name}_drawdown.png")

    return fig

def plot_exposure(df, name=None):
    exp = pd.get_dummies(df["asset"])
    exp["date"] = df["date"]
    exp = exp.groupby("date").sum()

    fig, ax = plt.subplots(figsize=(12,4))
    ax.stackplot(
        exp.index,
        exp.get("TLT", 0),
        exp.get("AGG", 0),
        exp.get("SHY", 0),
        labels=["TLT", "AGG", "SHY"]
    )

    ax.legend(loc="upper left")
    ax.set_title("Asset Exposure")

    if name:
        fig.savefig(OUTPUT_DIR / f"{name}_exposure.png")

    return fig

def build_buy_and_hold_nav(etf_df, ticker, initial_nav=1_000_000):
    df = (
        etf_df[etf_df["ticker"] == ticker]
        .sort_values("date")
        .copy()
    )

    returns = df["close"].pct_change().fillna(0)
    df["nav"] = initial_nav * (1 + returns).cumprod()

    return df[["date", "nav"]]


def plot_inflation_regime(regime_df: pd.DataFrame, name: str | None = None):
    df = regime_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df.sort_values("date", inplace=True)
    INFLATION_COLORS = {
        -1: "#03fc5a",   # DIS → green
        0: "tab:blue",  # NEU → blue
        1: "#ff0000"    # INF → red
    }

    series = df["inflation_regime"].map({"DIS": -1, "NEU": 0, "INF": 1})
    df = df.assign(code=series).dropna(subset=["code"])
    df["code"] = df["code"].astype(int)

    fig, ax = plt.subplots(figsize=(12, 2.5))

    # draw segments + transitions
    for i in range(len(df) - 1):
        y0 = df.iloc[i]["code"]
        y1 = df.iloc[i + 1]["code"]
        x0 = df.iloc[i]["date"]
        x1 = df.iloc[i + 1]["date"]

        # horizontal segment
        ax.plot(
            [x0, x1],
            [y0, y0],
            color=INFLATION_COLORS[y0],
            linewidth=2.5,
            solid_capstyle="butt",
            zorder=3
        )

        # vertical connector if state changes
        if y1 != y0:
            ax.plot(
                [x1, x1],
                [y0, y1],
                color=INFLATION_COLORS[y1],
                linewidth=2.5,
                solid_capstyle="butt",
                zorder=3
            )

    ax.axhline(0, linestyle="--", linewidth=1, color="black", alpha=0.4)

    ax.set_yticks([-1, 0, 1])
    ax.set_yticklabels(["DIS", "NEU", "INF"])
    ax.set_title("Inflation Regime (DIS = green, NEU = blue, INF = red)")
    ax.grid(True, axis="x", alpha=0.25)
    ax.set_xlim(df["date"].min(), df["date"].max())

    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    if name:
        fig.savefig(OUTPUT_DIR / f"{name}_inflation_regime.png")

    return fig

#helper for bool plots
def fill_binary_regime(
    ax,
    dates,
    series,
    pos_color="green",
    neg_color="red",
    alpha=0.25
):
    ax.fill_between(
        dates, 0, series,
        where=series > 0,
        step="post",
        color=pos_color,
        alpha=alpha
    )
    ax.fill_between(
        dates, 0, series,
        where=series < 0,
        step="post",
        color=neg_color,
        alpha=alpha
    )

def plot_growth_regime(regime_df: pd.DataFrame, name: str | None = None):
    df = regime_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df.sort_values("date", inplace=True)
    series = df["growth_regime"].map({"SLOW": -1, "OK": 1})

    fig, ax = plt.subplots(figsize=(12, 2.5))
    fill_binary_regime(ax, df["date"], series)
    ax.step(df["date"], series, where="post")
    ax.axhline(0, linestyle="--", linewidth=1)
    ax.set_yticks([-1, 1])
    ax.set_title("Growth Regime (SLOW=-1, OK=+1)")
    ax.grid(True, axis="y")
    ax.set_xlim(df["date"].min(), df["date"].max())

    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    if name:
        fig.savefig(OUTPUT_DIR / f"{name}_growth_regime.png")
    return fig


def plot_labour_regime(regime_df: pd.DataFrame, name: str | None = None):
    df = regime_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df.sort_values("date", inplace=True)
    series = df["labour_regime"].map({"WEAK": -1, "OK": 1})

    fig, ax = plt.subplots(figsize=(12, 2.5))
    fill_binary_regime(ax, df["date"], series)
    ax.step(df["date"], series, where="post")
    ax.axhline(0, linestyle="--", linewidth=1)
    ax.set_yticks([-1, 1])
    ax.set_title("Labour Regime (WEAK=-1, OK=+1)")
    ax.grid(True, axis="y")
    ax.set_xlim(df["date"].min(), df["date"].max())

    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    if name:
        fig.savefig(OUTPUT_DIR / f"{name}_labour_regime.png")
    return fig


def plot_curve_state(regime_df: pd.DataFrame, name: str | None = None):
    df = regime_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df.sort_values("date", inplace=True)
    series = df["curve_state"].map({"INV": -1, "NORM": 1})

    fig, ax = plt.subplots(figsize=(12, 2.5))
    fill_binary_regime(ax, df["date"], series)
    ax.step(df["date"], series, where="post")
    ax.axhline(0, linestyle="--", linewidth=1)
    ax.set_yticks([-1, 1])
    ax.set_title("Curve State (INV=-1, NORM=+1)")
    ax.grid(True, axis="y")
    ax.set_xlim(df["date"].min(), df["date"].max())

    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    if name:
        fig.savefig(OUTPUT_DIR / f"{name}_curve_state.png")
    return fig


def plot_macro_supports_duration(regime_df: pd.DataFrame, name: str | None = None):
    df = regime_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df.sort_values("date", inplace=True)
    series = df["macro_supports_duration"].map({False: -1, True: 1})

    fig, ax = plt.subplots(figsize=(12, 2.5))
    fill_binary_regime(ax, df["date"], series)
    ax.step(df["date"], series, where="post")
    ax.axhline(0, linestyle="--", linewidth=1)
    ax.set_yticks([-1, 1])
    ax.set_title("Macro Supports Duration (False=-1, True=+1)")
    ax.grid(True, axis="y")
    ax.set_xlim(df["date"].min(), df["date"].max())

    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    if name:
        fig.savefig(OUTPUT_DIR / f"{name}_macro_supports_duration.png")
    return fig