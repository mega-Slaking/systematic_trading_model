import streamlit as st
import pandas as pd
import sqlite3
import sys
from pathlib import Path
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dataclasses import asdict

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

sys.path.insert(0, str(SRC_ROOT))

from accounting.tearsheet_builder import build_tearsheet

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


@st.cache_data
def load_regime_trace() -> pd.DataFrame:
    query = """
        SELECT
            date,
            scenario_id,
            inflation_regime,
            growth_regime,
            labour_regime,
            curve_state,
            macro_supports_duration
        FROM backtest_regime_trace
        ORDER BY scenario_id, date
    """

    with _connect_db() as conn:
        df = pd.read_sql(query, conn, parse_dates=["date"])

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])

    return df

# Load data
results = load_backtest_results()
regime_trace = load_regime_trace()

# Check if scenario_id column exists
if "scenario_id" not in results.columns:
    st.error("No scenario_id column found in backtest_results. Ensure backtests were run with scenarios.")
    st.stop()

scenarios = sorted(results["scenario_id"].unique())
st.subheader(f"Available Scenarios: {len(scenarios)}")
#st.write("Scenarios: " + ", ".join(scenarios))

st.divider()

# Create tabs for different views
tab1, tab2, tab3, tab4 = st.tabs(["NAV Comparison", "Returns Analysis", "Tearsheet", "ETF Prices"])

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
    st.subheader("Tearsheet by Scenario")

    selected_scenario = st.selectbox(
        "Select a scenario:",
        scenarios,
        key="tearsheet_scenario_select",
    )

    scenario_data = (
        results[results["scenario_id"] == selected_scenario]
        .sort_values("date")
        .copy()
    )

    scenario_regime_trace = (
        regime_trace[regime_trace["scenario_id"] == selected_scenario]
        .sort_values("date")
        .copy()
    )

    ##dewbug
    merged_debug = scenario_data.merge(
        scenario_regime_trace,
        on=["date", "scenario_id"],
        how="left",
    )

    if "inflation_regime" in merged_debug.columns:
        match_rate = merged_debug["inflation_regime"].notna().mean()
        st.caption(f"Regime trace match rate: {match_rate:.2%}")
    ##dewbug

    if scenario_data.empty:
        st.warning("No data available for selected scenario.")
        st.stop()

    tearsheet = build_tearsheet(
        results_df=scenario_data,
        regime_df=scenario_regime_trace,
        risk_free_rate=0.02,
        periods_per_year=252,
    )

    summary = tearsheet.summary

    st.caption(
        f"{summary.scenario_id} | {summary.start_date} to {summary.end_date}"
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Return", f"{summary.total_return:.2%}")
        st.metric("CAGR", f"{summary.cagr:.2%}")

    with col2:
        st.metric("Annualized Volatility", f"{summary.annualized_volatility:.2%}")
        st.metric("Sharpe", f"{summary.sharpe:.2f}")

    with col3:
        st.metric("Sortino", f"{summary.sortino:.2f}")
        st.metric("Calmar", f"{summary.calmar:.2f}")

    with col4:
        st.metric("Max Drawdown", f"{summary.max_drawdown:.2%}")
        st.metric("VaR 95%", f"{summary.var_95:.2%}")

    st.divider()

    col5, col6, col7, col8 = st.columns(4)

    with col5:
        st.metric("CVaR 95%", f"{summary.cvar_95:.2%}")

    with col6:
        st.metric("Skew", f"{summary.skew:.2f}")

    with col7:
        st.metric("Excess Kurtosis", f"{summary.excess_kurtosis:.2f}")

    with col8:
        st.metric("Avg Turnover", f"{summary.avg_turnover:.2%}")

    col12, col13 = st.columns(2)

    with col12:
        st.metric("Worst Day", f"{summary.worst_day:.2%}")

    with col13:
        st.metric("Best Day", f"{summary.best_day:.2%}")

    col9, col10, col11 = st.columns(3)

    with col9:
        st.metric("Annualized Turnover", f"{summary.annualized_turnover:.2%}")

    with col10:
        st.metric("Total Cost", f"${summary.total_cost:,.2f}")

    with col11:
        if summary.cost_drag is None:
            st.metric("Cost Drag", "N/A")
        else:
            st.metric("Cost Drag", f"{summary.cost_drag:.2%}")

    st.divider()

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.write("**Equity Curve**")

        equity_fig = go.Figure()
        equity_fig.add_trace(
            go.Scatter(
                x=tearsheet.equity_curve["date"],
                y=tearsheet.equity_curve["nav"],
                mode="lines",
                name="NAV",
                hovertemplate=(
                    "Date: %{x|%Y-%m-%d}<br>"
                    "NAV: $%{y:,.0f}"
                    "<extra></extra>"
                ),
            )
        )

        equity_fig.update_layout(
            title="Scenario NAV",
            xaxis_title="Date",
            yaxis_title="NAV ($)",
            template="plotly_white",
            height=400,
        )

        st.plotly_chart(equity_fig, use_container_width=True)

    with chart_col2:
        st.write("**Drawdown Curve**")

        drawdown_fig = go.Figure()
        drawdown_fig.add_trace(
            go.Scatter(
                x=tearsheet.drawdown_curve["date"],
                y=tearsheet.drawdown_curve["drawdown"],
                mode="lines",
                name="Drawdown",
                hovertemplate=(
                    "Date: %{x|%Y-%m-%d}<br>"
                    "Drawdown: %{y:.2%}"
                    "<extra></extra>"
                ),
            )
        )

        drawdown_fig.update_layout(
            title="Drawdown",
            xaxis_title="Date",
            yaxis_title="Drawdown",
            template="plotly_white",
            height=400,
        )

        st.plotly_chart(drawdown_fig, use_container_width=True)

    st.divider()

    st.write("**Rolling Metrics**")

    rolling_df = tearsheet.rolling_metrics.dropna().copy()

    if rolling_df.empty:
        st.info("Not enough data to calculate rolling metrics yet.")
    else:
        rolling_fig = make_subplots(specs=[[{"secondary_y": True}]])

        rolling_fig.add_trace(
            go.Scatter(
                x=rolling_df["date"],
                y=rolling_df["rolling_volatility"],
                mode="lines",
                name="Rolling Volatility",
                hovertemplate=(
                    "Date: %{x|%Y-%m-%d}<br>"
                    "Rolling Volatility: %{y:.2%}"
                    "<extra></extra>"
                ),
            ),
            secondary_y=False,
        )

        rolling_fig.add_trace(
            go.Scatter(
                x=rolling_df["date"],
                y=rolling_df["rolling_sharpe"],
                mode="lines",
                name="Rolling Sharpe",
                hovertemplate=(
                    "Date: %{x|%Y-%m-%d}<br>"
                    "Rolling Sharpe: %{y:.2f}"
                    "<extra></extra>"
                ),
            ),
            secondary_y=True,
        )

        rolling_fig.update_layout(
            title="Rolling Volatility and Rolling Sharpe",
            xaxis_title="Date",
            template="plotly_white",
            hovermode="x unified",
            height=500,
        )

        rolling_fig.update_yaxes(
            title_text="Rolling Volatility",
            tickformat=".0%",
            secondary_y=False,
        )

        rolling_fig.update_yaxes(
            title_text="Rolling Sharpe",
            secondary_y=True,
        )

        st.plotly_chart(rolling_fig, use_container_width=True)
    
        st.divider()

    st.write("**Exposure Summary**")

    if tearsheet.exposure_summary is None or tearsheet.exposure_summary.empty:
        st.info(
            "No exposure summary available. Check whether weights are stored in backtest_results."
        )
    else:
        exposure_display = tearsheet.exposure_summary.copy()

        if "value" in exposure_display.columns:
            exposure_display["value"] = exposure_display["value"].map(
                lambda x: f"{x:.2%}" if pd.notna(x) else "N/A"
            )

        st.dataframe(
            exposure_display,
            use_container_width=True,
        )

    
        st.divider()

    st.write("**Regime Summary**")

    if tearsheet.regime_summary is None or tearsheet.regime_summary.empty:
        st.info(
            "No regime summary available. Check whether regime_trace is populated and date-aligned."
        )
    else:
        regime_summary = tearsheet.regime_summary.copy()

        percent_columns = [
            "total_return",
            "annualized_volatility",
            "max_drawdown",
            "worst_day",
            "best_day",
            "avg_weight_TLT",
            "avg_weight_AGG",
            "avg_weight_SHY",
        ]

        for regime_type in regime_summary["regime_type"].dropna().unique():
            st.write(f"**{regime_type}**")

            subset = regime_summary[
                regime_summary["regime_type"] == regime_type
            ].copy()

            for column in percent_columns:
                if column in subset.columns:
                    subset[column] = subset[column].map(
                        lambda x: f"{x:.2%}" if pd.notna(x) else "N/A"
                    )

            if "regime_type" in subset.columns:
                subset = subset.drop(columns=["regime_type"])

            st.dataframe(
                subset,
                use_container_width=True,
            )

    st.divider()

    st.write("**Tearsheet Summary Table**")

    summary_df = pd.DataFrame([asdict(summary)]).T
    summary_df.columns = ["Value"]

    st.dataframe(summary_df, use_container_width=True)

    st.write("**Raw Scenario Data**")

    display_columns = [
        column
        for column in [
            "date",
            "scenario_id",
            "nav_pre",
            "nav",
            "ret",
            "turnover",
            "fee_cost",
            "slippage_cost",
            "total_cost",
            "gross_notional",
            "n_positions",
            "top_asset",
            "top_weight",
        ]
        if column in scenario_data.columns
    ]

    st.dataframe(
        scenario_data[display_columns],
        use_container_width=True,
    )

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