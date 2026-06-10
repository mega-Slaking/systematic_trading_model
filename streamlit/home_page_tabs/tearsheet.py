"""Tearsheet tab module."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dataclasses import asdict
import sys
from pathlib import Path

from .utils import load_backtest_results, load_regime_trace, load_etf_prices

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from accounting.tearsheet_builder import build_tearsheet


def render_tearsheet_tab():
    """Render the Tearsheet tab."""
    st.subheader("Tearsheet by Scenario")

    # Load data
    results = load_backtest_results()
    regime_trace = load_regime_trace()
    etf_prices = load_etf_prices()
    scenarios = sorted(results["scenario_id"].unique())

    selected_scenario = st.selectbox(
        "Select a scenario:",
        scenarios,
        key="tearsheet_scenario_select",
    )

    scenario_data = (
        results[results["scenario_id"] == selected_scenario].sort_values("date").copy()
    )

    scenario_regime_trace = (
        regime_trace[regime_trace["scenario_id"] == selected_scenario]
        .sort_values("date")
        .copy()
    )

    # Debug info
    merged_debug = scenario_data.merge(
        scenario_regime_trace,
        on=["date", "scenario_id"],
        how="left",
    )

    if "inflation_regime" in merged_debug.columns:
        match_rate = merged_debug["inflation_regime"].notna().mean()
        st.caption(f"Regime trace match rate: {match_rate:.2%}")

    if scenario_data.empty:
        st.warning("No data available for selected scenario.")
        st.stop()

    tearsheet = build_tearsheet(
        results_df=scenario_data,
        regime_df=scenario_regime_trace,
        benchmark_prices_df=etf_prices,
        risk_free_rate=0.02,
        periods_per_year=252,
    )

    summary = tearsheet.summary

    st.caption(f"{summary.scenario_id} | {summary.start_date} to {summary.end_date}")

    # Display key metrics
    _display_key_metrics(summary)

    st.divider()

    # Display charts
    _display_charts(tearsheet)

    st.divider()

    # Display rolling metrics
    _display_rolling_metrics(tearsheet)

    st.divider()

    # Display exposure summary
    _display_exposure_summary(tearsheet)

    st.divider()

    # Display regime summary
    _display_regime_summary(tearsheet)

    st.divider()

    # Display benchmark summary
    _display_benchmark_summary(tearsheet)

    st.divider()

    # Display summary table
    _display_summary_table(summary)

    # Display raw data
    _display_raw_data(scenario_data)


def _display_key_metrics(summary):
    """Display key performance metrics in columns."""
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

    # col9, col10, col11 = st.columns(3) # - commented for now, nost costs are being applied/broker dependant value

    # with col9:
    #     st.metric("Annualized Turnover", f"{summary.annualized_turnover:.2%}")

    # with col10:
    #     st.metric("Total Cost", f"${summary.total_cost:,.2f}")

    # with col11:
    #     if summary.cost_drag is None:
    #         st.metric("Cost Drag", "N/A")
    #     else:
    #         st.metric("Cost Drag", f"{summary.cost_drag:.2%}")

    col14, col15, col16, col17 = st.columns(4)

    with col14:
        st.metric("Parametric VaR 95%", f"{summary.parametric_var_95:.2%}")

    with col15:
        st.metric("Daily Hit Rate", f"{summary.daily_hit_rate:.2%}")

    with col16:
        st.metric("Payoff Ratio", f"{summary.payoff_ratio:.2f}")

    with col17:
        st.metric("Profit Factor", f"{summary.profit_factor:.2f}")

    col18, col19 = st.columns(2)

    with col18:
        st.metric("Avg Win Day", f"{summary.avg_win:.2%}")

    with col19:
        st.metric("Avg Loss Day", f"{summary.avg_loss:.2%}")


def _display_charts(tearsheet):
    """Display equity and drawdown charts."""
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
                    "Date: %{x|%Y-%m-%d}<br>" "NAV: $%{y:,.0f}" "<extra></extra>"
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


def _display_rolling_metrics(tearsheet):
    """Display rolling metrics chart."""
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


def _display_exposure_summary(tearsheet):
    """Display exposure summary table."""
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


def _display_regime_summary(tearsheet):
    """Display regime summary tables."""
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


def _display_benchmark_summary(tearsheet):
    """Display benchmark-relative metrics."""
    st.write("**Benchmark Summary**")

    if tearsheet.benchmark_summary is None or tearsheet.benchmark_summary.empty:
        st.info(
            "No benchmark summary available. Check whether ETF price data is available."
        )
        return

    benchmark_display = tearsheet.benchmark_summary.copy()

    percent_columns = [
        "benchmark_total_return",
        "benchmark_cagr",
        "benchmark_volatility",
        "benchmark_max_drawdown",
        "active_cagr",
        "tracking_error",
        "alpha",
    ]

    ratio_columns = [
        "information_ratio",
        "beta",
        "correlation",
        "r_squared",
    ]

    for column in percent_columns:
        if column in benchmark_display.columns:
            benchmark_display[column] = benchmark_display[column].map(
                lambda x: f"{x:.2%}" if pd.notna(x) else "N/A"
            )

    for column in ratio_columns:
        if column in benchmark_display.columns:
            benchmark_display[column] = benchmark_display[column].map(
                lambda x: f"{x:.2f}" if pd.notna(x) else "N/A"
            )

    st.dataframe(
        benchmark_display,
        use_container_width=True,
    )


def _display_summary_table(summary):
    """Display summary table."""
    st.write("**Tearsheet Summary Table**")

    summary_df = pd.DataFrame([asdict(summary)]).T
    summary_df.columns = ["Value"]

    st.dataframe(summary_df, use_container_width=True)


def _display_raw_data(scenario_data):
    """Display raw scenario data."""
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
            "gross_trade_notional",
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
