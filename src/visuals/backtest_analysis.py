import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

OUTPUT_DIR = Path("output/reports")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def load_results(path):
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df

def plot_nav(dfs, labels, name):
    plt.figure(figsize=(12,6))
    for df, label in zip(dfs, labels):
        plt.plot(df["date"], df["nav"], label=label)
    plt.legend()
    plt.title("NAV Comparison")
    plt.grid(True)
    plt.savefig(OUTPUT_DIR / f"{name}_nav.png")
    plt.close()

def plot_drawdown(df, name):
    peak = df["nav"].cummax()
    dd = df["nav"] / peak - 1
    plt.figure(figsize=(12,4))
    plt.plot(df["date"], dd)
    plt.title("Drawdown")
    plt.grid(True)
    plt.savefig(OUTPUT_DIR / f"{name}_drawdown.png")
    plt.close()

def plot_exposure(df, name):
    exp = pd.get_dummies(df["asset"])
    exp["date"] = df["date"]
    exp = exp.groupby("date").sum()

    plt.figure(figsize=(12,4))
    plt.stackplot(
        exp.index,
        exp.get("TLT", 0),
        exp.get("AGG", 0),
        exp.get("SHY", 0),
        labels=["TLT", "AGG", "SHY"]
    )
    plt.legend(loc="upper left")
    plt.title("Asset Exposure")
    plt.savefig(OUTPUT_DIR / f"{name}_exposure.png")
    plt.close()
