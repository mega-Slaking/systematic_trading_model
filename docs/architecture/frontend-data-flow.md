# Frontend / Data Flow

How data moves from the FastAPI service through the React data layer into pages,
components, and finally charts and tables.

```mermaid
flowchart TD
    subgraph BACKEND["Backend"]
        SVC["api/services<br/>tearsheet · volatility · macro<br/>etf_prices · scenarios · jobs"]
        ROUT["api/routers<br/>REST endpoints"]
        SER["api/serialization<br/>frames · dataclasses<br/>(NaN→null · ISO dates)"]
        SVC --> SER --> ROUT
    end

    subgraph DATALAYER["Data layer (frontend/src)"]
        CLIENT["api/client.ts<br/>typed fetch · schema.d.ts"]
        HOOKS["api/hooks.ts<br/>React Query hooks"]
        URL["hooks/useUrlState.ts<br/>shareable view state"]
        ROUT -->|JSON| CLIENT --> HOOKS
    end

    subgraph PAGES["Pages"]
        P["NavComparison · Returns · Tearsheet<br/>Volatility · Macro · EtfPrices · Strategies"]
    end

    subgraph COMPONENTS["Shared components"]
        GATE["HealthGate · ErrorBoundary<br/>Skeleton · ThemeToggle"]
        GRID["MetricGrid · StatCard<br/>ScenarioSelect · InfoTooltip"]
    end

    subgraph VIEWS["Charts + Tables"]
        CHARTS["charts/<br/>PlotlyLineChart · NavChart<br/>ReturnsScatter · boxplots"]
        TABLES["tables/DataTable"]
    end

    HOOKS --> P
    URL --> P
    P --> GRID
    P --> CHARTS
    P --> TABLES
    GATE --> P
    GRID --> CHARTS
```

## Flow

1. **Backend** — `api/services` compute results from the DB / `build_tearsheet`;
   `api/serialization` enforces the JSON boundary (NaN → null, ISO dates) before
   `api/routers` expose them as REST endpoints.
2. **Data layer** — `api/client.ts` issues typed fetches (types from
   `schema.d.ts`), wrapped by React Query hooks in `api/hooks.ts`;
   `useUrlState` keeps selected scenario/filters in the URL for shareable views.
3. **Pages** — each of the seven pages calls the relevant hook and composes
   shared components.
4. **Components** — cross-cutting UI (`HealthGate`, `ErrorBoundary`, theme,
   `MetricGrid`, `ScenarioSelect`) wraps and feeds the views.
5. **Charts + tables** — Plotly-based charts (one shared lazy chunk) and
   `DataTable` render the final visuals.
