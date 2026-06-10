"""NAV Comparison tab module."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from .utils import load_backtest_results, load_etf_prices


def render_nav_comparison_tab():
    """Render the NAV Comparison tab."""
    st.subheader("NAV Curves by Scenario + Buy & Hold Benchmarks")

    # Load data
    results = load_backtest_results()
    scenarios = sorted(results["scenario_id"].unique())

    fig = go.Figure()

    # Add a line for each scenario
    for scenario_id in scenarios:
        scenario_data = results[results["scenario_id"] == scenario_id].sort_values("date")
        fig.add_trace(
            go.Scatter(
                x=scenario_data["date"],
                y=scenario_data["nav"],
                mode="lines",
                name=f"Scenario: {scenario_id}",
                hovertemplate="<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>NAV: $%{y:,.0f}<extra></extra>",
            )
        )

    # Add buy & hold benchmarks
    etf_prices = load_etf_prices()
    # Align benchmarks to the actual backtest window so they don't drift from the
    # scenario lines (the backtest start floor is set in run_backtest.py). The old
    # hardcoded clip is kept commented as a rollback reference.
    # start_date = pd.to_datetime("2014-01-01")
    start_date = results["date"].min()
    initial_nav = (
        results[results["scenario_id"] == scenarios[0]]["nav"].iloc[0]
        if scenarios
        else 1_000_000
    )

    for ticker in ["TLT", "AGG", "SHY"]:
        ticker_data = etf_prices[etf_prices["ticker"] == ticker].sort_values("date")
        ticker_data = ticker_data[ticker_data["date"] >= start_date]

        if not ticker_data.empty:
            # Calculate buy & hold NAV (starting with initial NAV amount)
            first_close = ticker_data["close"].iloc[0]
            shares = initial_nav / first_close
            ticker_data_copy = ticker_data.copy()
            ticker_data_copy["nav"] = ticker_data_copy["close"] * shares

            fig.add_trace(
                go.Scatter(
                    x=ticker_data_copy["date"],
                    y=ticker_data_copy["nav"],
                    mode="lines",
                    name=f"B&H: {ticker}",
                    line=dict(dash="dash"),
                    hovertemplate="<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>NAV: $%{y:,.0f}<extra></extra>",
                )
            )

    fig.update_layout(
        title="NAV Comparison: Scenarios vs Buy & Hold Benchmarks",
        xaxis_title="Date",
        yaxis_title="NAV ($)",
        template="plotly_white",
        hovermode="x unified",
        height=600,
        width=None,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Summary statistics
    st.subheader("Scenario Performance Summary")
    summary_stats = []

    for scenario_id in scenarios:
        scenario_data = results[results["scenario_id"] == scenario_id]
        final_nav = scenario_data["nav"].iloc[-1]
        start_nav = scenario_data["nav"].iloc[0]
        total_return = final_nav / start_nav - 1

        peak = scenario_data["nav"].cummax()
        max_drawdown = (scenario_data["nav"] / peak - 1).min()

        summary_stats.append(
            {
                "Scenario": scenario_id,
                "Final NAV": f"${final_nav:,.0f}",
                "Total Return": f"{total_return:.2%}",
                "Max Drawdown": f"{max_drawdown:.2%}",
                "Volatility": (
                    f"{scenario_data['ret'].std() * (252 ** 0.5):.2%}"
                    if "ret" in scenario_data.columns
                    else "N/A"
                ),
            }
        )

    summary_df = pd.DataFrame(summary_stats)
    st.dataframe(summary_df, use_container_width=True)
