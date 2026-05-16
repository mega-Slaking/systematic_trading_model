"""Returns Analysis tab module."""

import streamlit as st
import plotly.graph_objects as go
from .utils import load_backtest_results


def render_returns_analysis_tab():
    """Render the Returns Analysis tab."""
    st.subheader("Daily Returns Distribution")

    # Load data
    results = load_backtest_results()
    scenarios = sorted(results["scenario_id"].unique())

    fig = go.Figure()

    for scenario_id in scenarios:
        scenario_data = results[results["scenario_id"] == scenario_id].sort_values("date")
        if "ret" in scenario_data.columns:
            fig.add_trace(
                go.Scatter(
                    x=scenario_data["date"],
                    y=scenario_data["ret"],
                    mode="markers",
                    name=scenario_id,
                    hovertemplate="<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>Return: %{y:.4f}<extra></extra>",
                    marker=dict(size=4, opacity=0.6),
                )
            )

    fig.update_layout(
        title="Daily Returns by Scenario",
        xaxis_title="Date",
        yaxis_title="Daily Return",
        template="plotly_white",
        hovermode="x unified",
        height=600,
        width=None,
    )
    st.plotly_chart(fig, use_container_width=True)
