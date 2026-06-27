# System Overview

End-to-end flow from raw market data through the strategy engine, portfolio
construction, the backtest loop, analytics, and finally the user-facing frontend.

```mermaid
flowchart TD
    subgraph DATA["1 · Data Ingestion"]
        EXT["External sources<br/>(ETF prices · macro series)"]
        FETCH["src/api_fetch<br/>fetch_etf_prices · fetch_macro_data"]
        DB[("SQLite · data/database.db<br/>etf_prices · macro_data<br/>volatility_features · backtest results")]
        EXT --> FETCH --> DB
    end

    subgraph ENGINE["2 · Strategy Engine (per date)"]
        SIG["Signals<br/>price + macro"]
        REG["Regime + base allocation<br/>(TLT tracker)"]
        RISK["Risk model<br/>volatility · covariance"]
        SIZE["Position sizer + constraints"]
        DEC["Decision<br/>(target weights)"]
        SIG --> REG --> RISK --> SIZE --> DEC
    end

    subgraph PORT["3 · Portfolio Construction"]
        REB["Rebalance → trades"]
        HOLD["Holdings + cash"]
        REB --> HOLD
    end

    subgraph BT["4 · Backtest Loop"]
        LOOP["run_backtest<br/>iterate dates"]
        VAL["Valuation → NAV snapshots"]
        LOOP --> VAL
    end

    subgraph ANALYTICS["5 · Analytics"]
        TEAR["Tearsheets · metrics<br/>(src/accounting)"]
    end

    subgraph FE["6 · Frontend"]
        API["FastAPI service<br/>(api/)"]
        SPA["React SPA<br/>(frontend/)"]
        API --> SPA
    end

    DB --> SIG
    DEC --> REB
    HOLD --> LOOP
    VAL --> DB
    DB --> TEAR
    TEAR --> API
    DB --> API
```

## Stages

1. **Data ingestion** — `src/api_fetch` pulls ETF prices and macro series from
   external providers and persists them to SQLite (`data/database.db`).
2. **Strategy engine** — for each date, price/macro signals feed a regime
   classification and TLT-tracking base allocation, which is then risk-adjusted
   (volatility + covariance), sized, and constrained into a `Decision`.
3. **Portfolio construction** — the decision's target weights drive a rebalance
   into concrete trades, updating holdings and cash.
4. **Backtest loop** — `run_backtest` walks the date range, valuing the
   portfolio into NAV snapshots and persisting results to the database.
5. **Analytics** — `src/accounting` builds tearsheets and performance metrics
   from the stored results.
6. **Frontend** — the FastAPI service exposes the data/analytics over REST; the
   React SPA renders the interactive research dashboard.
