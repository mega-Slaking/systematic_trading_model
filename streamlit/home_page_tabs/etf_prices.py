"""ETF Prices tab module."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from .utils import load_etf_prices


def render_etf_prices_tab():
    """Render the ETF Prices tab."""
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
                fig.add_trace(
                    go.Scatter(
                        x=ticker_data["date"],
                        y=ticker_data["close"],
                        mode="lines",
                        name=ticker,
                        hovertemplate="<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>Close: $%{y:.2f}<extra></extra>",
                    )
                )

        fig.update_layout(
            title="Historical ETF Prices: TLT, AGG, SHY",
            xaxis_title="Date",
            yaxis_title="Close Price ($)",
            template="plotly_white",
            hovermode="x unified",
            height=600,
            width=None,
        )
        st.plotly_chart(fig, use_container_width=True)

        # Price statistics
        st.subheader("Price Statistics")
        price_stats = []

        for ticker in ["TLT", "AGG", "SHY"]:
            ticker_data = etf_prices[etf_prices["ticker"] == ticker]

            if not ticker_data.empty:
                close_prices = ticker_data["close"]
                price_stats.append(
                    {
                        "Ticker": ticker,
                        "First Close": f"${close_prices.iloc[0]:.2f}",
                        "Last Close": f"${close_prices.iloc[-1]:.2f}",
                        "Min Price": f"${close_prices.min():.2f}",
                        "Max Price": f"${close_prices.max():.2f}",
                        "Total Return": f"{(close_prices.iloc[-1] / close_prices.iloc[0] - 1):.2%}",
                    }
                )

        price_stats_df = pd.DataFrame(price_stats)
        st.dataframe(price_stats_df, use_container_width=True)
