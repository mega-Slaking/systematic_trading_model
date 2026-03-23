import pandas as pd
from pathlib import Path
import plotly.graph_objects as go

OUTPUT_DIR = Path("output/reports")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def load_results(path): #This will need refactor
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df

def plot_nav(dfs, labels, name=None):
    fig = go.Figure()

    for df, label in zip(dfs, labels):
        fig.add_trace(go.Scatter(
            x=df["date"],
            y=df["nav"],
            mode='lines',
            name=label
        ))

    fig.update_layout(
        title="NAV Comparison",
        xaxis_title="Date",
        yaxis_title="NAV",
        hovermode='x unified',
        template='plotly_white',
        height=600,
        width=1200
    )

    if name:
        fig.write_image(OUTPUT_DIR / f"{name}_nav.png")

    return fig

def plot_drawdown(df, name=None):
    peak = df["nav"].cummax()
    dd = df["nav"] / peak - 1

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"],
        y=dd,
        mode='lines',
        fill='tozeroy',
        name='Drawdown'
    ))

    fig.update_layout(
        title="Drawdown",
        xaxis_title="Date",
        yaxis_title="Drawdown",
        hovermode='x unified',
        template='plotly_white',
        height=400,
        width=1200
    )

    if name:
        fig.write_image(OUTPUT_DIR / f"{name}_drawdown.png")

    return fig

def plot_exposure(df, name=None):
    exp = pd.get_dummies(df["asset"])
    exp["date"] = df["date"]
    exp = exp.groupby("date").sum()

    fig = go.Figure()

    # Add stacked areas
    assets = ["TLT", "AGG", "SHY"]
    colors = ["#2ecc71", "#3498db", "#e74c3c"]

    for i, (asset, color) in enumerate(zip(assets, colors)):
        y_data = exp.get(asset, 0)
        fig.add_trace(go.Scatter(
            x=exp.index,
            y=y_data,
            name=asset,
            mode='lines',
            line=dict(width=0.5, color=color),
            fillcolor=color,
            fill='tonexty' if i > 0 else 'tozeroy',
            stackgroup='one'
        ))

    fig.update_layout(
        title="Asset Exposure",
        xaxis_title="Date",
        yaxis_title="Exposure",
        hovermode='x unified',
        template='plotly_white',
        height=400,
        width=1200
    )

    if name:
        fig.write_image(OUTPUT_DIR / f"{name}_exposure.png")

    return fig

def build_buy_and_hold_nav(etf_df, ticker, initial_nav=1_000_000):
    df = (
        etf_df[etf_df["ticker"] == ticker]
        .sort_values("date")
        .copy()
    )

    returns = df["close"].pct_change().fillna(0)
    df["nav"] = initial_nav * (1 + returns).cumprod()

    return df[["date", "nav"]]


def plot_inflation_regime(regime_df: pd.DataFrame, name: str | None = None):
    df = regime_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df.sort_values("date", inplace=True)
    INFLATION_COLORS = {
        -1: "#03fc5a",   # DIS → green
        0: "tab:blue",  # NEU → blue
        1: "#ff0000"    # INF → red
    }

    series = df["inflation_regime"].map({"DIS": -1, "NEU": 0, "INF": 1})
    df = df.assign(code=series).dropna(subset=["code"])
    df["code"] = df["code"].astype(int)

    fig = go.Figure()

    # Draw segments + transitions
    for i in range(len(df) - 1):
        y0 = df.iloc[i]["code"]
        y1 = df.iloc[i + 1]["code"]
        x0 = df.iloc[i]["date"]
        x1 = df.iloc[i + 1]["date"]

        # horizontal segment
        fig.add_trace(go.Scatter(
            x=[x0, x1],
            y=[y0, y0],
            mode='lines',
            line=dict(color=INFLATION_COLORS[y0], width=2.5),
            showlegend=False,
            hoverinfo='skip'
        ))

        # vertical connector if state changes
        if y1 != y0:
            fig.add_trace(go.Scatter(
                x=[x1, x1],
                y=[y0, y1],
                mode='lines',
                line=dict(color=INFLATION_COLORS[y1], width=2.5),
                showlegend=False,
                hoverinfo='skip'
            ))

    fig.add_hline(y=0, line_dash="dash", line_width=1, line_color="black", opacity=0.4)

    fig.update_layout(
        title="Inflation Regime (DIS = green, NEU = blue, INF = red)",
        xaxis_title="Date",
        yaxis_title="Regime",
        hovermode='x unified',
        template='plotly_white',
        height=250,
        width=1200,
        yaxis=dict(tickvals=[-1, 0, 1], ticktext=["DIS", "NEU", "INF"])
    )

    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')
    fig.update_xaxes(range=[df["date"].min(), df["date"].max()])

    if name:
        fig.write_image(OUTPUT_DIR / f"{name}_inflation_regime.png")

    return fig

#helper for bool plots - returns traces to add to a figure
def fill_binary_regime(dates, series, pos_color="green", neg_color="red", alpha=0.25):
    traces = []

    # Create positive fill
    pos_mask = series > 0
    if pos_mask.any():
        traces.append(go.Scatter(
            x=dates[pos_mask],
            y=series[pos_mask],
            fill='tozeroy',
            fillcolor=f'rgba({tuple(int(pos_color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))}, {alpha})',
            line=dict(width=0),
            showlegend=False,
            hoverinfo='skip'
        ))

    # Create negative fill
    neg_mask = series < 0
    if neg_mask.any():
        traces.append(go.Scatter(
            x=dates[neg_mask],
            y=series[neg_mask],
            fill='tozeroy',
            fillcolor=f'rgba({tuple(int(neg_color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))}, {alpha})',
            line=dict(width=0),
            showlegend=False,
            hoverinfo='skip'
        ))

    return traces

def plot_growth_regime(regime_df: pd.DataFrame, name: str | None = None):
    df = regime_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df.sort_values("date", inplace=True)
    series = df["growth_regime"].map({"SLOW": -1, "OK": 1})

    fig = go.Figure()

    # Add fill traces
    fill_traces = fill_binary_regime(df["date"], series, pos_color="#2ecc71", neg_color="#e74c3c")
    for trace in fill_traces:
        fig.add_trace(trace)

    # Add step line
    fig.add_trace(go.Scatter(
        x=df["date"],
        y=series,
        mode='lines',
        line=dict(width=2),
        name="Growth Regime"
    ))

    fig.add_hline(y=0, line_dash="dash", line_width=1, line_color="black")

    fig.update_layout(
        title="Growth Regime (SLOW=-1, OK=+1)",
        xaxis_title="Date",
        yaxis_title="Regime",
        hovermode='x unified',
        template='plotly_white',
        height=250,
        width=1200,
        yaxis=dict(tickvals=[-1, 1], ticktext=["SLOW", "OK"])
    )

    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')

    if name:
        fig.write_image(OUTPUT_DIR / f"{name}_growth_regime.png")

    return fig


def plot_labour_regime(regime_df: pd.DataFrame, name: str | None = None):
    df = regime_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df.sort_values("date", inplace=True)
    series = df["labour_regime"].map({"WEAK": -1, "OK": 1})

    fig = go.Figure()

    # Add fill traces
    fill_traces = fill_binary_regime(df["date"], series, pos_color="#2ecc71", neg_color="#e74c3c")
    for trace in fill_traces:
        fig.add_trace(trace)

    # Add step line
    fig.add_trace(go.Scatter(
        x=df["date"],
        y=series,
        mode='lines',
        line=dict(width=2),
        name="Labour Regime"
    ))

    fig.add_hline(y=0, line_dash="dash", line_width=1, line_color="black")

    fig.update_layout(
        title="Labour Regime (WEAK=-1, OK=+1)",
        xaxis_title="Date",
        yaxis_title="Regime",
        hovermode='x unified',
        template='plotly_white',
        height=250,
        width=1200,
        yaxis=dict(tickvals=[-1, 1], ticktext=["WEAK", "OK"])
    )

    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')

    if name:
        fig.write_image(OUTPUT_DIR / f"{name}_labour_regime.png")

    return fig


def plot_curve_state(regime_df: pd.DataFrame, name: str | None = None):
    df = regime_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df.sort_values("date", inplace=True)
    series = df["curve_state"].map({"INV": -1, "NORM": 1})

    fig = go.Figure()

    # Add fill traces
    fill_traces = fill_binary_regime(df["date"], series, pos_color="#2ecc71", neg_color="#e74c3c")
    for trace in fill_traces:
        fig.add_trace(trace)

    # Add step line
    fig.add_trace(go.Scatter(
        x=df["date"],
        y=series,
        mode='lines',
        line=dict(width=2),
        name="Curve State"
    ))

    fig.add_hline(y=0, line_dash="dash", line_width=1, line_color="black")

    fig.update_layout(
        title="Curve State (INV=-1, NORM=+1)",
        xaxis_title="Date",
        yaxis_title="State",
        hovermode='x unified',
        template='plotly_white',
        height=250,
        width=1200,
        yaxis=dict(tickvals=[-1, 1], ticktext=["INV", "NORM"])
    )

    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')

    if name:
        fig.write_image(OUTPUT_DIR / f"{name}_curve_state.png")

    return fig


def plot_macro_supports_duration(regime_df: pd.DataFrame, name: str | None = None):
    df = regime_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df.sort_values("date", inplace=True)
    series = df["macro_supports_duration"].map({False: -1, True: 1})

    fig = go.Figure()

    # Add fill traces
    fill_traces = fill_binary_regime(df["date"], series, pos_color="#2ecc71", neg_color="#e74c3c")
    for trace in fill_traces:
        fig.add_trace(trace)

    # Add step line
    fig.add_trace(go.Scatter(
        x=df["date"],
        y=series,
        mode='lines',
        line=dict(width=2),
        name="Macro Supports Duration"
    ))

    fig.add_hline(y=0, line_dash="dash", line_width=1, line_color="black")

    fig.update_layout(
        title="Macro Supports Duration (False=-1, True=+1)",
        xaxis_title="Date",
        yaxis_title="Support",
        hovermode='x unified',
        template='plotly_white',
        height=250,
        width=1200,
        yaxis=dict(tickvals=[-1, 1], ticktext=["False", "True"])
    )

    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')

    if name:
        fig.write_image(OUTPUT_DIR / f"{name}_macro_supports_duration.png")

    return fig
