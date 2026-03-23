import streamlit as st
import pandas as pd
import sqlite3
import sys
from pathlib import Path
from src.visuals.backtest_analysis import (plot_nav, plot_drawdown,
                                          plot_exposure, build_buy_and_hold_nav)

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
st.set_page_config(
    page_title="Systematic Trading Dashboard",
    layout="wide"
)

st.title("Systematic Trading Dashboard")
st.caption("Backtest & Live Analytics")

DB_PATH = REPO_ROOT / "data" / "database.db"

if not DB_PATH.exists():
    st.error("No database found at data/database.db. Run the backtest/persistence pipeline first.")
    st.stop()

def _connect_db() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)

@st.cache_data
def load_table(table_name: str, order_by: str = "date") -> pd.DataFrame:
    query = f"SELECT * FROM {table_name} ORDER BY {order_by}"
    with _connect_db() as conn:
        df = pd.read_sql(query, conn, parse_dates=["date"])

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df.sort_values("date", inplace=True)

    return df

results = load_table("backtest_results")

st.subheader("Overview")

col1, col2 = st.columns(2)

with col1:
    st.metric(
        "Final NAV",
        f"{results['nav'].iloc[-1]:,.0f}"
    )

with col2:
    peak = results["nav"].cummax()
    drawdown = (results["nav"] / peak - 1).min()
    st.metric(
        "Max Drawdown",
        f"{drawdown:.2%}"
    )

st.divider()
st.subheader("NAV comparison")
strategy = load_table("backtest_results")
etf_prices = load_table("etf_prices")
tlt_nav = build_buy_and_hold_nav(etf_prices, "TLT")
agg_nav = build_buy_and_hold_nav(etf_prices, "AGG")
shy_nav = build_buy_and_hold_nav(etf_prices, "SHY")

fig_nav=plot_nav(
    dfs=[strategy, tlt_nav, agg_nav, shy_nav],
    labels=["Strategy","TLT Buy & Hold", "AGG Buy & Hold", "SHY Buy & Hold"],
    name="nav_comparison"
)
st.pyplot(fig_nav, use_container_width=True)

st.subheader("Drawdown")
fig_dd_s = plot_drawdown(strategy)
fig_dd_tlt = plot_drawdown(tlt_nav,'tlt')
fig_dd_agg = plot_drawdown(agg_nav, 'agg')
fig_dd_shy = plot_drawdown(shy_nav,'shy')
col1, col2 = st.columns(2)
with col1:
    st.write('Strategy Drawdown')
    st.pyplot(fig_dd_s, use_container_width=True)
    st.write('AGG Drawdown')
    st.pyplot(fig_dd_agg, use_container_width=True)
with col2:
    st.write('TLT Drawdown')
    st.pyplot(fig_dd_tlt, use_container_width=True)
    st.write('SHY Drawdown')
    st.pyplot(fig_dd_shy, use_container_width=True)

# fig_exposure = plot_exposure(strategy, "Buy and Hold")
# st.subheader("Assest Exposure")
# st.pyplot(fig_exposure, use_container_width=True)
st.write("Net exposure plot, Gross exposure plot, weighting plots and attributions")