import plotly.graph_objects as go


def plot_etf_vs_macro(etf_df, macro_df, ticker, macro_col, macro_label):
    fig = go.Figure()

    etf = etf_df[etf_df["ticker"] == ticker].sort_values("date")

    # Add ETF price on primary y-axis
    fig.add_trace(go.Scatter(
        x=etf["date"],
        y=etf["close"],
        name=f"{ticker} Price",
        yaxis='y1',
        mode='lines',
        line=dict(color='#1f77b4')
    ))

    # Add macro indicator on secondary y-axis
    fig.add_trace(go.Scatter(
        x=macro_df["date"],
        y=macro_df[macro_col],
        name=macro_label,
        yaxis='y2',
        mode='lines',
        line=dict(color='#ff7f0e', dash='dash')
    ))

    fig.update_layout(
        title=f"{ticker} vs {macro_label}",
        hovermode='x unified',
        template='plotly_white',
        height=500,
        width=1000,
        yaxis=dict(
            title=f"{ticker} Price",
            titlefont=dict(color='#1f77b4'),
            tickfont=dict(color='#1f77b4')
        ),
        yaxis2=dict(
            title=macro_label,
            titlefont=dict(color='#ff7f0e'),
            tickfont=dict(color='#ff7f0e'),
            overlaying='y',
            side='right'
        )
    )

    return fig


def plot_yield_curve(macro_df):
    fig = go.Figure()

    # Add 10Y line
    fig.add_trace(go.Scatter(
        x=macro_df["date"],
        y=macro_df["gs10"],
        name="10Y",
        mode='lines',
        line=dict(color='#1f77b4')
    ))

    # Add 2Y line
    fig.add_trace(go.Scatter(
        x=macro_df["date"],
        y=macro_df["gs2"],
        name="2Y",
        mode='lines',
        line=dict(color='#ff7f0e')
    ))

    # Add spread as fill
    spread = macro_df["gs10"] - macro_df["gs2"]
    fig.add_trace(go.Scatter(
        x=macro_df["date"],
        y=spread,
        fill='tozeroy',
        fillcolor='rgba(127, 127, 127, 0.2)',
        line=dict(width=0),
        name="10Y–2Y Spread"
    ))

    fig.add_hline(y=0, line_color="black", line_dash="dash", line_width=1)

    fig.update_layout(
        title="US Yield Curve (10Y vs 2Y)",
        xaxis_title="Date",
        yaxis_title="Yield (%)",
        hovermode='x unified',
        template='plotly_white',
        height=500,
        width=1000
    )

    return fig
