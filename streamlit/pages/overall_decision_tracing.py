import streamlit as st
import sys
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

st.header("Decision Analytics Dashboard")
col1, col2 = st.columns(2)
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
BASE_DIR = Path(__file__).resolve().parents[2]
@st.cache_data
def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df.sort_values("date", inplace=True)
    return df
decisions= load_csv(BASE_DIR / "output" / "backtests" / "decision_trace.csv")

rule_counts = (
    decisions
    .groupby("rule_id")
    .size()
    .rename("count")
    .reset_index()
    .sort_values("count", ascending=False)
)

rule_counts["pct_time"] = rule_counts["count"] / rule_counts["count"].sum()
st.subheader("Rule Usage Summary")

st.dataframe(
    rule_counts.style.format(
        {
            "count": "{:,}",
            "pct_time": "{:.2%}"
        }
    ),
    use_container_width=True
)

#timeline trace
asset_map = {
    "SHY": 0,
    "AGG": 1,
    "TLT": 2
}

timeline = decisions.copy()
timeline["asset_code"] = timeline["chosen_asset"].map(asset_map)
ASSET_COLORS = {
    0: "tab:blue",   # SHY
    1: "#11d6cc",  # AGG
    2: "#03fc5a"   # TLT
}

ASSET_ORDER = ["SHY", "AGG", "TLT"]

def plot_decision_timeline(decisions):
    fig, ax = plt.subplots(figsize=(12, 2.5))

    for i in range(len(decisions) - 1):
        y0 = int(decisions.iloc[i]["asset_code"])
        y1 = int(decisions.iloc[i + 1]["asset_code"])
        x0 = decisions.iloc[i]["date"]
        x1 = decisions.iloc[i + 1]["date"]

        #Horizontal segment
        ax.plot(
            [x0, x1],
            [y0, y0],
            color=ASSET_COLORS[y0],
            linewidth=2.5,
            solid_capstyle="butt",
            zorder=3
        )

        # vertical transition connector
        if y1 != y0:
            ax.plot(
                [x1, x1],
                [y0, y1],
                color=ASSET_COLORS[y1],
                linewidth=2.5,
                solid_capstyle="butt",
                zorder=3
            )
            #ax.scatter([x1], [y1], s=10, zorder=4)

    # transitions (orange)
    rule_change = decisions["rule_id"] != decisions["rule_id"].shift(1)
    for d in decisions.loc[rule_change, "date"]:
        ax.axvline(d, color="orange", alpha=0.25, linewidth=0.8, linestyle='--', zorder=0)

    ax.set_yticks([asset_map[a] for a in ASSET_ORDER])
    ax.set_yticklabels(ASSET_ORDER)
    ax.set_title("Decision Timeline")
    ax.grid(True, axis="x")

    return fig
st.subheader("Decision Timeline")

fig = plot_decision_timeline(timeline)
st.pyplot(fig, use_container_width=True)
st.title("")

############################################
with st.expander("Filters", expanded=False):
    min_d = decisions["date"].min().date()
    max_d = decisions["date"].max().date()

    start, end = st.date_input(
        "Date range",
        value=(min_d, max_d),
        min_value=min_d,
        max_value=max_d
    )

    assets = sorted(decisions["chosen_asset"].unique())
    asset_filter = st.multiselect(
        "Assets",
        options=assets,
        default=assets
    )
df = decisions.copy()
df = df[(df["date"].dt.date >= start) & (df["date"].dt.date <= end)]
df = df[df["chosen_asset"].isin(asset_filter)]
df = df.sort_values("date").reset_index(drop=True)

if df.empty:
    st.warning("No rows after filters.")
    st.stop()

#Turnover primitives
df["prev_asset"] = df["chosen_asset"].shift(1)
df["switched"] = df["chosen_asset"] != df["prev_asset"]
df.loc[0, "switched"] = False  # first row: ignore artificial "switch"

df["block"] = df["switched"].cumsum()

# holding periods per contiguous block
holding_blocks = (
    df.groupby(["block", "chosen_asset"])
      .size()
      .rename("days_held")
      .reset_index()
      .sort_values("days_held", ascending=False)
)

holding_periods = holding_blocks["days_held"]

# headline metrics
total_days = len(df)
num_switches = int(df["switched"].sum())
switch_rate = (num_switches / total_days) if total_days else 0.0

avg_hold = float(holding_periods.mean()) if len(holding_periods) else 0.0
median_hold = float(holding_periods.median()) if len(holding_periods) else 0.0
p90_hold = float(holding_periods.quantile(0.9)) if len(holding_periods) else 0.0

#Header metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Days in sample", f"{total_days:,}")
c2.metric("Switches", f"{num_switches:,}")
c3.metric("Switch rate (per day)", f"{switch_rate:.2%}")
c4.metric("Median hold (days)", f"{median_hold:.0f}")

c5, c6, c7 = st.columns(3)
c5.metric("Avg hold (days)", f"{avg_hold:.1f}")
c6.metric("90th pct hold (days)", f"{p90_hold:.0f}")
c7.metric("Approx switches / year", f"{(num_switches / max(1, (df['date'].dt.year.nunique()))):.1f}")

st.divider()

#switches per year (visual)
df["year"] = df["date"].dt.year
switches_per_year = (
    df.groupby("year")["switched"]
      .sum()
      .rename("num_switches")
      .reset_index()
)

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Switches per year")
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(switches_per_year["year"], switches_per_year["num_switches"])
    ax.set_xlabel("Year")
    ax.set_ylabel("Switches")
    ax.grid(True)
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

with col_right:
    st.subheader("Holding period distribution")
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.hist(holding_periods, bins=40)
    ax.set_xlabel("Days held (contiguous)")
    ax.set_ylabel("Count")
    ax.grid(True, axis="y")
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

st.divider()

# Transition table
st.subheader("Top transitions (when a switch occurs)")

switch_rows = df[df["switched"]].copy()
switch_rows["from"] = switch_rows["prev_asset"]
switch_rows["to"] = switch_rows["chosen_asset"]

transitions = (
    switch_rows.groupby(["from", "to"])
      .size()
      .rename("count")
      .reset_index()
      .sort_values("count", ascending=False)
)

if transitions.empty:
    st.info("No transitions found (no switches in filtered range).")
else:
    transitions["pct_of_switches"] = transitions["count"] / transitions["count"].sum()
    st.dataframe(
        transitions.style.format({"count": "{:,}", "pct_of_switches": "{:.1%}"}),
        use_container_width=True
    )

st.divider()

#Longest holds table
st.subheader("Longest holds (contiguous blocks)")

show_n = st.slider("Show top N holds", 10, 200, 30, step=10)
st.dataframe(
    holding_blocks.head(show_n).reset_index(drop=True),
    use_container_width=True
)