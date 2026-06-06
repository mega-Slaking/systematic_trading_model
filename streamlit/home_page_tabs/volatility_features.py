"""Volatility Features tab module."""

import streamlit as st
import plotly.graph_objects as go

from .utils import load_volatility_features


# Raw volatility estimates (annualized), in display order.
_VOL_METHODS = {
    "rolling_20": "Rolling 20d",
    "rolling_60": "Rolling 60d",
    "ewma_94": "EWMA λ=0.94",
    "ewma_97": "EWMA λ=0.97",
    "garch": "GARCH(1,1)",
}


def render_volatility_features_tab():
    """Render the Volatility Features tab."""
    st.subheader("Volatility Feature Surface")
    st.caption(
        "Point-in-time annualized volatility per asset. Values are lagged one day - "
        "each date shows the volatility the strategy knew *before* trading that day "
        "(no lookahead bias)."
    )

    df = load_volatility_features()

    if df.empty:
        st.warning(
            "No volatility features found. Run `run_backtest.py` to build and "
            "persist the `volatility_features` table."
        )
        return

    tickers = sorted(df["ticker"].unique())

    col1, col2 = st.columns([1, 3])
    with col1:
        default_ticker = "TLT" if "TLT" in tickers else tickers[0]
        ticker = st.selectbox("Asset", tickers, index=tickers.index(default_ticker))
    with col2:
        available = [m for m in _VOL_METHODS if m in df.columns]
        methods = st.multiselect(
            "Methods",
            available,
            default=available,
            format_func=lambda m: _VOL_METHODS[m],
        )

    tdf = df[df["ticker"] == ticker].sort_values("date")

    fig = go.Figure()
    for method in methods:
        fig.add_trace(
            go.Scatter(
                x=tdf["date"],
                y=tdf[method],
                mode="lines",
                name=_VOL_METHODS[method],
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}"
                    "<br>Vol: %{y:.2%}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title=f"{ticker} - Annualized Volatility Estimates",
        xaxis_title="Date",
        yaxis_title="Annualized volatility",
        yaxis_tickformat=".0%",
        template="plotly_white",
        hovermode="x unified",
        height=600,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Latest values per ticker across all methods.
    st.subheader("Latest values")
    latest_cols = ["date", "ticker"] + [m for m in _VOL_METHODS if m in df.columns]
    latest = (
        df.sort_values("date")
        .groupby("ticker")
        .tail(1)[latest_cols]
        .reset_index(drop=True)
    )
    st.dataframe(latest, use_container_width=True)
