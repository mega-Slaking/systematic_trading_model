import streamlit as st
import sys
from pathlib import Path
import pandas as pd
from src.visuals.plots import plot_etf_vs_macro, plot_yield_curve

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
BASE_DIR = Path(__file__).resolve().parents[2]
st.title("ETFs vs Macro Indicators ")
@st.cache_data
def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df.sort_values("date", inplace=True)
    return df

etf_df = load_csv(BASE_DIR / "data" / "raw" / "etf_prices.csv")
macro_df = load_csv(BASE_DIR / "data" / "raw" / "macro_cpi.csv")

col1, col2 = st.columns(2)
with col1:
    for ticker in ["TLT", "AGG", "SHY"]:
        fig = plot_etf_vs_macro(
            etf_df,
            macro_df,
            ticker,
            macro_col="cpi_yoy",
            macro_label="CPI YoY"
        )
        st.write(ticker + " vs CPI YoY")
        st.pyplot(fig, use_container_width=True)
    
with col2:
    for ticker in ["TLT", "AGG", "SHY"]:
        fig = plot_etf_vs_macro(
            etf_df,
            macro_df,
            ticker,
            macro_col="pmi",
            macro_label="PMI"
        )
        st.write(ticker + " vs PMI YoY")
        st.pyplot(fig, use_container_width=True)
    
fig_yield_curve = plot_yield_curve(macro_df)
st.subheader("Yield Curve (10Y vs 2Y)")
st.pyplot(fig_yield_curve, use_container_width=True)

