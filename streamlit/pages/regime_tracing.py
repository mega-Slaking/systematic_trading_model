import streamlit as st
import sys
from pathlib import Path
import pandas as pd
from src.visuals.backtest_analysis import (plot_inflation_regime,plot_growth_regime,
                                           plot_labour_regime,plot_curve_state,plot_macro_supports_duration)
st.header("Macro Indicator Dashboard")
st.write("note: these plots plan to be updated to be more visually intuitive")
col1, col2 = st.columns(2)
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
BASE_DIR = Path(__file__).resolve().parents[2]
@st.cache_data
def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df.sort_values("date", inplace=True)
    return df

regimes= load_csv(BASE_DIR / "output" / "backtests" / "regime_trace.csv")
fig_growth=plot_growth_regime(regimes)
fig_inflation=plot_inflation_regime(regimes)
fig_labour=plot_labour_regime(regimes)
fig_yield_curve=plot_curve_state(regimes)
fig_macro_duration=plot_macro_supports_duration(regimes)

with col1:
    st.write("Growth regime")
    st.pyplot(fig_growth, use_container_width=True)
    st.write("Labour regime")
    st.pyplot(fig_labour, use_container_width=True)
with col2:
    st.write("Inflation regime")
    st.pyplot(fig_inflation, use_container_width=True)
    st.write("Yield Curve Inversion")
    st.pyplot(fig_yield_curve, use_container_width=True)
st.subheader("Does macro supports duration?")
st.pyplot(fig_macro_duration, use_container_width=True)