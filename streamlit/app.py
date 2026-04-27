import streamlit as st
import pandas as pd
import sqlite3
import sys
from pathlib import Path
import plotly.graph_objects as go
from plotly.subplots import make_subplots

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

st.set_page_config(page_title="Scenario Testing", layout="wide")
st.title("Scenario Testing Dashboard")
st.caption("Analyze NAV curves across different backtest scenarios")

DB_PATH = REPO_ROOT / "data" / "database.db"

if not DB_PATH.exists():
    st.error("No database found at data/database.db. Run the backtest/persistence pipeline first.")
    st.stop()

def _connect_db() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)

@st.cache_data
def load_backtest_results() -> pd.DataFrame:
    query = "SELECT * FROM backtest_results ORDER BY scenario_id, date"
    with _connect_db() as conn:
        df = pd.read_sql(query, conn, parse_dates=["date"])
    
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    
    return df

@st.cache_data
def load_etf_prices() -> pd.DataFrame:
    query = "SELECT date, ticker, close FROM etf_prices ORDER BY ticker, date"
    with _connect_db() as conn:
        df = pd.read_sql(query, conn, parse_dates=["date"])
    
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    
    return df

# Load data
results = load_backtest_results()

# Check if scenario_id column exists
if "scenario_id" not in results.columns:
    st.error("No scenario_id column found in backtest_results. Ensure backtests were run with scenarios.")
    st.stop()

scenarios = sorted(results["scenario_id"].unique())
st.subheader(f"Available Scenarios: {len(scenarios)}")
#st.write("Scenarios: " + ", ".join(scenarios))

st.divider()

# Create tabs for different views
tab1, tab2, tab3, tab4 = st.tabs(["NAV Comparison", "Returns Analysis", "Detailed Metrics", "ETF Prices"])

with tab1:
    st.subheader("NAV Curves by Scenario + Buy & Hold Benchmarks")
    
    fig = go.Figure()
    
    # Add a line for each scenario
    for scenario_id in scenarios:
        scenario_data = results[results["scenario_id"] == scenario_id].sort_values("date")
        fig.add_trace(go.Scatter(
            x=scenario_data["date"],
            y=scenario_data["nav"],
            mode='lines',
            name=f"Scenario: {scenario_id}",
            hovertemplate='<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>NAV: $%{y:,.0f}<extra></extra>'
        ))
    
    # Add buy & hold benchmarks
    etf_prices = load_etf_prices()
    start_date = pd.to_datetime("2014-01-01")
    initial_nav = results[results["scenario_id"] == scenarios[0]]["nav"].iloc[0] if scenarios else 1_000_000
    
    for ticker in ["TLT", "AGG", "SHY"]:
        ticker_data = etf_prices[etf_prices["ticker"] == ticker].sort_values("date")
        ticker_data = ticker_data[ticker_data["date"] >= start_date]
        
        if not ticker_data.empty:
            # Calculate buy & hold NAV (starting with initial NAV amount)
            first_close = ticker_data["close"].iloc[0]
            shares = initial_nav / first_close
            ticker_data_copy = ticker_data.copy()
            ticker_data_copy["nav"] = ticker_data_copy["close"] * shares
            
            fig.add_trace(go.Scatter(
                x=ticker_data_copy["date"],
                y=ticker_data_copy["nav"],
                mode='lines',
                name=f"B&H: {ticker}",
                line=dict(dash="dash"),
                hovertemplate='<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>NAV: $%{y:,.0f}<extra></extra>'
            ))
    
    fig.update_layout(
        title="NAV Comparison: Scenarios vs Buy & Hold Benchmarks",
        xaxis_title="Date",
        yaxis_title="NAV ($)",
        template="plotly_white",
        hovermode="x unified",
        height=600,
        width=None
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Summary statistics
    st.subheader("Scenario Performance Summary")
    summary_stats = []
    
    for scenario_id in scenarios:
        scenario_data = results[results["scenario_id"] == scenario_id]
        final_nav = scenario_data["nav"].iloc[-1]
        start_nav = scenario_data["nav"].iloc[0]
        total_return = (final_nav / start_nav - 1)
        
        peak = scenario_data["nav"].cummax()
        max_drawdown = (scenario_data["nav"] / peak - 1).min()
        
        summary_stats.append({
            "Scenario": scenario_id,
            "Final NAV": f"${final_nav:,.0f}",
            "Total Return": f"{total_return:.2%}",
            "Max Drawdown": f"{max_drawdown:.2%}",
            "Volatility": f"{scenario_data['ret'].std() * (252 ** 0.5):.2%}" if "ret" in scenario_data.columns else "N/A"
        })
    
    summary_df = pd.DataFrame(summary_stats)
    st.dataframe(summary_df, use_container_width=True)

with tab2:
    st.subheader("Daily Returns Distribution")
    
    fig = go.Figure()
    
    for scenario_id in scenarios:
        scenario_data = results[results["scenario_id"] == scenario_id].sort_values("date")
        if "ret" in scenario_data.columns:
            fig.add_trace(go.Scatter(
                x=scenario_data["date"],
                y=scenario_data["ret"],
                mode='markers',
                name=scenario_id,
                hovertemplate='<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>Return: %{y:.4f}<extra></extra>',
                marker=dict(size=4, opacity=0.6)
            ))
    
    fig.update_layout(
        title="Daily Returns by Scenario",
        xaxis_title="Date",
        yaxis_title="Daily Return",
        template="plotly_white",
        hovermode="x unified",
        height=600,
        width=None
    )
    st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.subheader("Detailed Metrics by Scenario")
    
    selected_scenario = st.selectbox("Select a scenario to view detailed metrics:", scenarios)
    
    scenario_data = results[results["scenario_id"] == selected_scenario].sort_values("date")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Final NAV", f"${scenario_data['nav'].iloc[-1]:,.0f}")
    with col2:
        total_return = (scenario_data['nav'].iloc[-1] / scenario_data['nav'].iloc[0] - 1)
        st.metric("Total Return", f"{total_return:.2%}")
    with col3:
        peak = scenario_data["nav"].cummax()
        max_drawdown = (scenario_data["nav"] / peak - 1).min()
        st.metric("Max Drawdown", f"{max_drawdown:.2%}")
    with col4:
        if "ret" in scenario_data.columns:
            ann_vol = scenario_data["ret"].std() * (252 ** 0.5)
            st.metric("Annualized Volatility", f"{ann_vol:.2%}")
    
    st.write("**Metrics Over Time**")
    
    # Show detailed columns
    display_columns = [col for col in ["date", "nav", "ret", "turnover", "fee_cost", "slippage_cost", "num_positions"] 
                       if col in scenario_data.columns or col == "date" or col == "nav"]
    
    st.dataframe(scenario_data[["date", "nav", "ret", "turnover"] if "turnover" in scenario_data.columns else ["date", "nav", "ret"]], 
                 use_container_width=True)

with tab4:
    st.subheader("Historical ETF Prices")
    st.caption("Daily closing prices for TLT, AGG, and SHY")
    
    etf_prices = load_etf_prices()
    
    if etf_prices.empty:
        st.warning("No ETF price data available in database.")
    else:
        fig = go.Figure()
        
        # Filter for target tickers
        for ticker in ["TLT", "AGG", "SHY"]:
            ticker_data = etf_prices[etf_prices["ticker"] == ticker].sort_values("date")
            
            if not ticker_data.empty:
                fig.add_trace(go.Scatter(
                    x=ticker_data["date"],
                    y=ticker_data["close"],
                    mode='lines',
                    name=ticker,
                    hovertemplate='<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>Close: $%{y:.2f}<extra></extra>'
                ))
        
        fig.update_layout(
            title="Historical ETF Prices: TLT, AGG, SHY",
            xaxis_title="Date",
            yaxis_title="Close Price ($)",
            template="plotly_white",
            hovermode="x unified",
            height=600,
            width=None
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Price statistics
        st.subheader("Price Statistics")
        price_stats = []
        
        for ticker in ["TLT", "AGG", "SHY"]:
            ticker_data = etf_prices[etf_prices["ticker"] == ticker]
            
            if not ticker_data.empty:
                close_prices = ticker_data["close"]
                price_stats.append({
                    "Ticker": ticker,
                    "First Close": f"${close_prices.iloc[0]:.2f}",
                    "Last Close": f"${close_prices.iloc[-1]:.2f}",
                    "Min Price": f"${close_prices.min():.2f}",
                    "Max Price": f"${close_prices.max():.2f}",
                    "Total Return": f"{(close_prices.iloc[-1] / close_prices.iloc[0] - 1):.2%}"
                })
        
        price_stats_df = pd.DataFrame(price_stats)
        st.dataframe(price_stats_df, use_container_width=True)