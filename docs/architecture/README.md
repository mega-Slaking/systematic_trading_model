# Architecture

Detailed architecture diagrams for the platform. All diagrams are written in
Mermaid and render inline on GitHub.

| Diagram | Scope |
|---------|-------|
| [System overview](system-overview.md) | Data sources → strategy engine → portfolio construction → backtest → analytics → frontend. |
| [Backend module map](backend-module-map.md) | The Python packages under `src/` (plus `api/`): data, signals, regimes, covariance, volatility, constraints, execution, accounting/tearsheets. |
| [Frontend / data flow](frontend-data-flow.md) | FastAPI services/serialization → typed client + React Query hooks → pages/components → charts/tables. |

## Design notes

- **A single `Decision` dataclass** flows through the per-date pipeline,
  accumulating state at each stage (regime → allocation → risk → sizing →
  constraints). Each stage reads and returns an updated `Decision`, which keeps
  the engines independently testable and composable.
- **Precompute-once, reuse-across-scenarios.** The covariance returns view and
  the volatility feature surface are built once before the scenario loop and
  shared read-only, with caching keyed on the inputs that actually affect the
  result.
- **Read-only analytics boundary.** The FastAPI service reuses the existing
  Python compute (`db_reader`, `build_tearsheet`) behind REST; the serialization
  layer enforces the JSON boundary (NaN → null, ISO dates) so the React client
  consumes clean, typed payloads.
