"""Streamlit app for Scenario Testing Dashboard."""

import streamlit as st

from home_page_tabs import (
    render_nav_comparison_tab,
    render_returns_analysis_tab,
    render_tearsheet_tab,
    render_etf_prices_tab,
    render_volatility_features_tab,
)
from home_page_tabs.utils import load_backtest_results, DB_PATH

st.set_page_config(page_title="Scenario Testing", layout="wide")
st.title("Scenario Testing Dashboard")
st.caption("Analyze NAV curves across different backtest scenarios")

if not DB_PATH.exists():
    st.error("No database found at data/database.db. Run the backtest/persistence pipeline first.")
    st.stop()

# Load data
results = load_backtest_results()

# Check if scenario_id column exists
if "scenario_id" not in results.columns:
    st.error("No scenario_id column found in backtest_results. Ensure backtests were run with scenarios.")
    st.stop()

scenarios = sorted(results["scenario_id"].unique())
st.subheader(f"Available Scenarios: {len(scenarios)}")

st.divider()

# Create tabs for different views
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["NAV Comparison", "Returns Analysis", "Tearsheet", "ETF Prices", "Volatility Features"]
)

with tab1:
    render_nav_comparison_tab()

with tab2:
    render_returns_analysis_tab()

with tab3:
    render_tearsheet_tab()

with tab4:
    render_etf_prices_tab()

with tab5:
    render_volatility_features_tab()
