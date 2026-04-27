import streamlit as st
import sys
import sqlite3
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

st.set_page_config(page_title="ETFs vs Macro Indicators", layout="wide")
st.title("ETFs vs Macro Indicators")
st.caption("Interactive analysis of ETF prices vs macroeconomic indicators")

DB_PATH = REPO_ROOT / "data" / "database.db"

if not DB_PATH.exists():
    st.error("No database found at data/database.db")
    st.stop()

def _connect_db() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)

@st.cache_data
def load_etf_prices() -> pd.DataFrame:
    query = "SELECT date, ticker, close FROM etf_prices ORDER BY ticker, date"
    with _connect_db() as conn:
        df = pd.read_sql(query, conn, parse_dates=["date"])
    return df

@st.cache_data
def load_macro_data() -> pd.DataFrame:
    query = """
        SELECT date, cpi, core_cpi, pmi, gs2, gs10, 
               unemployment, payrolls, fed_funds, consumer_sentiment
        FROM macro_data
        ORDER BY date
    """
    with _connect_db() as conn:
        df = pd.read_sql(query, conn, parse_dates=["date"])
    return df

@st.cache_data
def load_regime_data() -> pd.DataFrame:
    query = """
        SELECT date, inflation_regime, growth_regime, curve_state
        FROM regime_trace
        ORDER BY date
    """
    with _connect_db() as conn:
        df = pd.read_sql(query, conn, parse_dates=["date"])
    return df

etf_df = load_etf_prices()
macro_df = load_macro_data()
regime_df = load_regime_data()

st.divider()

# Tab 1: ETF vs CPI
st.subheader("ETF Prices vs CPI (Year-over-Year)")

for ticker in ["TLT", "AGG", "SHY"]:
    col1, col2 = st.columns(2)
    
    ticker_data = etf_df[etf_df["ticker"] == ticker].sort_values("date").copy()
    
    if not ticker_data.empty and not macro_df.empty:
        # Normalize for dual axis visualization
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        # ETF price on primary y-axis
        fig.add_trace(
            go.Scatter(
                x=ticker_data["date"],
                y=ticker_data["close"],
                name=f"{ticker} Close Price",
                line=dict(color="blue", width=2),
                hovertemplate="<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>Price: $%{y:.2f}<extra></extra>"
            ),
            secondary_y=False
        )
        
        # CPI on secondary y-axis
        macro_sorted = macro_df.sort_values("date")
        cpi_data = macro_sorted.dropna(subset=["cpi"])
        if not cpi_data.empty:
            fig.add_trace(
                go.Scatter(
                    x=cpi_data["date"],
                    y=cpi_data["cpi"],
                    name="CPI YoY (%)",
                    line=dict(color="red", width=2, dash="dash"),
                    hovertemplate="<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>CPI: %{y:.2f}%<extra></extra>"
                ),
                secondary_y=True
            )
        
        fig.update_xaxes(title_text="Date")
        fig.update_yaxes(title_text=f"{ticker} Price ($)", secondary_y=False)
        fig.update_yaxes(title_text="CPI YoY (%)", secondary_y=True)
        fig.update_layout(
            title=f"{ticker} vs CPI",
            hovermode="x unified",
            height=500,
            template="plotly_white"
        )
        
        with col1:
            st.plotly_chart(fig, use_container_width=True)
        
        # PMI on secondary y-axis
        fig2 = make_subplots(specs=[[{"secondary_y": True}]])
        
        fig2.add_trace(
            go.Scatter(
                x=ticker_data["date"],
                y=ticker_data["close"],
                name=f"{ticker} Close Price",
                line=dict(color="blue", width=2),
                hovertemplate="<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>Price: $%{y:.2f}<extra></extra>"
            ),
            secondary_y=False
        )
        
        pmi_data = macro_sorted.dropna(subset=["pmi"])
        if not pmi_data.empty:
            fig2.add_trace(
                go.Scatter(
                    x=pmi_data["date"],
                    y=pmi_data["pmi"],
                    name="PMI",
                    line=dict(color="green", width=2, dash="dash"),
                    hovertemplate="<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>PMI: %{y:.2f}<extra></extra>"
                ),
                secondary_y=True
            )
            
            # Add PMI=50 reference line
            fig2.add_hline(
                y=50, 
                line_dash="dot", 
                line_color="gray", 
                secondary_y=True,
                annotation_text="PMI=50 (neutral)"
            )
        
        fig2.update_xaxes(title_text="Date")
        fig2.update_yaxes(title_text=f"{ticker} Price ($)", secondary_y=False)
        fig2.update_yaxes(title_text="PMI", secondary_y=True)
        fig2.update_layout(
            title=f"{ticker} vs PMI",
            hovermode="x unified",
            height=500,
            template="plotly_white"
        )
        
        with col2:
            st.plotly_chart(fig2, use_container_width=True)

st.divider()

# Yield Curve
st.subheader("Yield Curve (10Y vs 2Y Spread)")

macro_sorted = macro_df.sort_values("date")
yield_data = macro_sorted.dropna(subset=["gs10", "gs2"]).copy()

if not yield_data.empty:
    yield_data["spread"] = yield_data["gs10"] - yield_data["gs2"]
    
    fig_yield = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Yields on primary y-axis
    fig_yield.add_trace(
        go.Scatter(
            x=yield_data["date"],
            y=yield_data["gs10"],
            name="10Y Yield",
            line=dict(color="darkblue", width=2),
            hovertemplate="<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>Yield: %{y:.2f}%<extra></extra>"
        ),
        secondary_y=False
    )
    
    fig_yield.add_trace(
        go.Scatter(
            x=yield_data["date"],
            y=yield_data["gs2"],
            name="2Y Yield",
            line=dict(color="lightblue", width=2),
            hovertemplate="<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>Yield: %{y:.2f}%<extra></extra>"
        ),
        secondary_y=False
    )
    
    # Spread on secondary y-axis
    fig_yield.add_trace(
        go.Scatter(
            x=yield_data["date"],
            y=yield_data["spread"],
            name="10Y-2Y Spread",
            line=dict(color="red", width=2, dash="dash"),
            fill="tozeroy",
            hovertemplate="<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>Spread: %{y:.2f}%<extra></extra>"
        ),
        secondary_y=True
    )
    
    # Add inversion line
    fig_yield.add_hline(
        y=0, 
        line_dash="dot", 
        line_color="gray", 
        secondary_y=True,
        annotation_text="Inversion Point"
    )
    
    fig_yield.update_xaxes(title_text="Date")
    fig_yield.update_yaxes(title_text="Yield (%)", secondary_y=False)
    fig_yield.update_yaxes(title_text="10Y-2Y Spread (%)", secondary_y=True)
    fig_yield.update_layout(
        title="Yield Curve Analysis: 10Y vs 2Y",
        hovermode="x unified",
        height=600,
        template="plotly_white"
    )
    
    st.plotly_chart(fig_yield, use_container_width=True)

st.divider()

# Macro Indicators Dashboard
st.subheader("Macro Indicators Dashboard")

macro_sorted = macro_df.sort_values("date")

col1, col2 = st.columns(2)

with col1:
    # Unemployment vs Consumer Sentiment
    fig_unemp = make_subplots(specs=[[{"secondary_y": True}]])
    
    unemp_data = macro_sorted.dropna(subset=["unemployment"])
    if not unemp_data.empty:
        fig_unemp.add_trace(
            go.Scatter(
                x=unemp_data["date"],
                y=unemp_data["unemployment"],
                name="Unemployment Rate",
                line=dict(color="darkred", width=2),
                hovertemplate="<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>Rate: %{y:.2f}%<extra></extra>"
            ),
            secondary_y=False
        )
    
    sentiment_data = macro_sorted.dropna(subset=["consumer_sentiment"])
    if not sentiment_data.empty:
        fig_unemp.add_trace(
            go.Scatter(
                x=sentiment_data["date"],
                y=sentiment_data["consumer_sentiment"],
                name="Consumer Sentiment",
                line=dict(color="orange", width=2, dash="dash"),
                hovertemplate="<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>Sentiment: %{y:.2f}<extra></extra>"
            ),
            secondary_y=True
        )
    
    fig_unemp.update_xaxes(title_text="Date")
    fig_unemp.update_yaxes(title_text="Unemployment Rate (%)", secondary_y=False)
    fig_unemp.update_yaxes(title_text="Consumer Sentiment Index", secondary_y=True)
    fig_unemp.update_layout(
        title="Unemployment vs Consumer Sentiment",
        hovermode="x unified",
        height=500,
        template="plotly_white"
    )
    
    st.plotly_chart(fig_unemp, use_container_width=True)

with col2:
    # Fed Funds vs CPI
    fig_fed = make_subplots(specs=[[{"secondary_y": True}]])
    
    fed_data = macro_sorted.dropna(subset=["fed_funds"])
    if not fed_data.empty:
        fig_fed.add_trace(
            go.Scatter(
                x=fed_data["date"],
                y=fed_data["fed_funds"],
                name="Fed Funds Rate",
                line=dict(color="purple", width=2),
                hovertemplate="<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>Rate: %{y:.2f}%<extra></extra>"
            ),
            secondary_y=False
        )
    
    cpi_data = macro_sorted.dropna(subset=["cpi"])
    if not cpi_data.empty:
        fig_fed.add_trace(
            go.Scatter(
                x=cpi_data["date"],
                y=cpi_data["cpi"],
                name="CPI YoY",
                line=dict(color="red", width=2, dash="dash"),
                hovertemplate="<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>CPI: %{y:.2f}%<extra></extra>"
            ),
            secondary_y=True
        )
    
    fig_fed.update_xaxes(title_text="Date")
    fig_fed.update_yaxes(title_text="Fed Funds Rate (%)", secondary_y=False)
    fig_fed.update_yaxes(title_text="CPI YoY (%)", secondary_y=True)
    fig_fed.update_layout(
        title="Fed Funds Rate vs CPI",
        hovermode="x unified",
        height=500,
        template="plotly_white"
    )
    
    st.plotly_chart(fig_fed, use_container_width=True)

