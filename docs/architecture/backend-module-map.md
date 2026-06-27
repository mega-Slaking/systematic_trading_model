# Backend Module Map

How the Python packages under `src/` (plus the `api/` service) connect. Arrows
show the dominant data/dependency direction through one engine evaluation and on
into persistence and analytics.

```mermaid
flowchart LR
    subgraph DATA["Data"]
        FETCH["api_fetch<br/>ETF + macro fetchers"]
        STORE["storage<br/>db_reader · db_writer · persister"]
        UNIV["universe.py"]
    end

    subgraph SIGNALS["Signals"]
        SP["signals_price<br/>price_signal_engine"]
        SM["signals_macro<br/>macro_features · macro_signal_engine"]
    end

    subgraph ALLOC["Regimes + Allocation"]
        REG["decision/regime_engine<br/>regime_trace"]
        STRAT["strategy<br/>config · presets · tlt_tracker"]
        CONV["conviction<br/>engine · models"]
        PIPE["decision/pipeline<br/>build_pre_risk_decision"]
    end

    subgraph RISK["Risk Model"]
        VOL["volatility<br/>estimator · states · feature_surface"]
        COV["covariance<br/>estimator · returns_view"]
    end

    subgraph SIZE["Sizing + Constraints"]
        PS["decision/position_sizer_engine"]
        CON["decision/constraint_engine<br/>constraints"]
    end

    subgraph ORCH["Orchestration"]
        ENG["engine<br/>run · decision_orchestration"]
        CTX["context<br/>backtest · live · protocol"]
    end

    subgraph EXEC["Execution + Portfolio"]
        EX["execution<br/>rebalance_v2 · models"]
        BTP["backtest<br/>engine · portfolio"]
    end

    subgraph BOOKS["Accounting + Analytics"]
        ACC["accounting<br/>valuation · metrics<br/>tearsheet_builder"]
    end

    subgraph SERVE["Serve"]
        SCN["scenarios<br/>factory · models"]
        APIS["api/<br/>routers · services · serialization"]
        NOTE["notify<br/>email · notifier"]
    end

    FETCH --> STORE
    UNIV --> SP
    STORE --> SP
    STORE --> SM
    SP --> PIPE
    SM --> PIPE
    REG --> PIPE
    STRAT --> PIPE
    CONV --> PIPE
    PIPE --> ENG
    VOL --> ENG
    COV --> ENG
    ENG --> PS --> CON --> EX
    CTX --> ENG
    EX --> BTP
    BTP --> ACC
    ACC --> STORE
    SCN --> ENG
    STORE --> APIS
    ACC --> APIS
    BTP --> NOTE
```

## Modules

| Area | Package(s) | Responsibility |
|------|-----------|----------------|
| **Data** | `api_fetch`, `storage`, `universe` | Fetch ETF/macro data; read/write SQLite; define the tradable universe. |
| **Signals** | `signals_price`, `signals_macro` | Trend/momentum signals and macro direction/acceleration features. |
| **Regimes + allocation** | `decision/regime_engine`, `strategy`, `conviction`, `decision/pipeline` | Classify the regime and build the pre-risk base allocation (TLT tracker). |
| **Risk model** | `volatility`, `covariance` | Estimate asset volatility states and the covariance matrix. |
| **Sizing + constraints** | `decision/position_sizer_engine`, `decision/constraint_engine` | Vol-target sizing and final weight constraints. |
| **Orchestration** | `engine`, `context` | Wire the per-date pipeline; provide backtest vs. live context. |
| **Execution + portfolio** | `execution`, `backtest` | Turn target weights into trades; run the backtest loop. |
| **Accounting + analytics** | `accounting` | Valuation, metrics, and tearsheet construction. |
| **Serve** | `scenarios`, `api/`, `notify` | Scenario definitions, the FastAPI read/run service, and notifications. |
