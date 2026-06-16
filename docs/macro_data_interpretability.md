# Design Spec: Correct & Redesign the ETFs-vs-Macro Dashboard for Regime Interpretation

**Status:** Proposal (no code changes yet — this document only)
**Target version:** see §13 (SemVer)
**Builds on:** the V1.15.0 FastAPI + React analytics stack (`docs/fastapi_react_migration_spec.md`, shipped — Streamlit retired to legacy) and the V1.10.0 `StrategyConfig` registry.
**Author:** drafted with quant-engineer analysis
**Date:** 2026-06-14

---

## 0. Reader orientation — what changed since the original prompt was written

The original idea (preserved verbatim in the **Appendix**) was written against the **Streamlit/Plotly** dashboard (`streamlit/pages/macro_indicators_vs_etf.py`). That frontend has since been **retired to legacy** (V1.15.0): the live analytics surface is now a **React SPA served by a FastAPI service** that reads SQLite via `src/storage/db_reader.py`. The ETFs-vs-Macro view is now `frontend/src/pages/MacroPage.tsx`, backed by `api/routers/macro.py` → `api/services/macro.py` (endpoints 10 + 11). Streamlit still launches but is frozen; **new work is React-only**.

This rework therefore re-targets every "add to the Streamlit page" instruction onto the **API-service / React-page** seam, and — critically — corrects several technical premises in the original that do not match how the data actually flows in this codebase (see §3, the verified findings). The *economic intent* of the original is sound and largely preserved; the *implementation surface* is rewritten.

The single highest-value correction: **the original's headline bug is real and confirmed** — `MacroPage.tsx` relabels the raw `cpi` series (a CPI **index level**, FRED `CPIAUCSL`) as "CPI YoY", and relabels `pmi` (which is actually **CFNAI**) as "PMI". Both are economically misleading. But the fix cannot be "derive YoY in the page" the way the original implies, because **the derived inflation/policy fields are not persisted and the API cannot currently see them** (§3.2). The derivation must move server-side.

---

## 1. Goal & motivation

### Goal
Make the ETFs-vs-Macro dashboard **correct, economically meaningful, and interpretable**: every series correctly labelled with its true source/units/frequency; inflation shown as YoY change (not index level); the CFNAI activity index named and interpreted correctly; the yield curve classified into bull/bear steepening/flattening; a transparent rule-based macro-regime overlay; and conditional forward-return tables that show how TLT/AGG/SHY historically behaved in similar regimes — with honest caveats about overlapping horizons and small samples.

### Motivation
The dashboard today places macro and ETF lines side by side with **mislabelled, mistransformed series** (§3), inviting exactly the wrong inference ("these two lines moved together, therefore..."). The system's actual edge is the **regime → asset map** (§3 mental model: which monetary/economic *phase* calls for TLT vs AGG vs SHY), not vol scaling. A dashboard that surfaces *regime* and *conditional behaviour* — rather than raw level overlaps — is the analytics complement to that thesis. This is **explanatory tooling**, not a new signal: per the operating principle "validate, then integrate, then (maybe) signal", nothing here touches allocation.

### Core product principle (carried over from the original)
Guide the user from *"these two series moved at the same time"* to *"inflation, growth, labour, policy, and the yield curve placed the market in this regime; under similar historical conditions these ETFs behaved this way — subject to these sample sizes and limitations."*

---

## 2. Scope & non-goals

### In scope
- A new **macro-features compute layer** (pure functions) that derives YoY inflation, momentum/change features, real policy rate, yield-curve change features, a curve-regime label, and a macro-regime label from the raw `macro_data` table.
- New / extended **FastAPI endpoints** exposing those derived series, snapshot cards, a regime timeline, and conditional forward-return tables.
- A redesigned **`MacroPage.tsx`** (and supporting React components) organised around snapshot cards → macro overview → yield curve → ETF/macro explorer → regime timeline → conditional forward returns → data-quality/methodology.
- **Unit tests** for every pure transform; **API tests** for every endpoint; data-quality diagnostics.

### Non-goals (explicit)
- **No change to strategy / decision / sizing / execution / backtest logic.** This is read-only analytics. In particular, the macro-regime classifier added here is a **dashboard-only explanatory label** and must NOT be confused with, or wired into, the engine's `evaluate_regime` (`src/decision/regime_engine.py`) which produces `monetary_regime`/`economic_regime` for allocation.
- **No threshold optimisation, no ML, no forecasting model.** Regimes are rule-based and chosen on economic priors, not fitted for return.
- **No claims of causality** from chart co-movement; no correlations between two trending level series.
- **No new heavy dependency.** FastAPI/pandas/numpy on the server and the existing React/Plotly stack on the client are sufficient.
- **No schema migration** for the read path — we derive from raw columns at request time (§12 #2, RESOLVED). Persisting derived fields (Phase 0, §5.0) is **not done for v1**; documented as a future option only.
- **Not resurrecting** the legacy Streamlit page (`streamlit/pages/macro_indicators_vs_etf.py`) or the dead matplotlib `src/visuals/` code.

---

## 3. Current-state analysis (verified against the code & DB, 2026-06-14)

### 3.1 The rendering surface today

| Layer | File | What it does |
|---|---|---|
| React page | `frontend/src/pages/MacroPage.tsx` | Renders, per ticker, `<TLT/AGG/SHY> vs CPI` and `… vs PMI` dual-axis charts; a yield-curve chart (10Y/2Y/spread); `Unemployment vs Consumer Sentiment`; `Fed Funds vs CPI`. **Relabels `cpi`→"CPI YoY" and `pmi`→"PMI" in the component** (`relabel(...)`). |
| API router | `api/routers/macro.py` | `GET /api/v1/macro` (indicator series), `GET /api/v1/macro/yield-curve` (gs10/gs2/spread). |
| API service | `api/services/macro.py` | Wraps `db_reader.get_macro_history()`; NaN-drops each indicator onto its own date axis; computes `spread = gs10 - gs2` inline. |
| Reader | `src/storage/db_reader.py:get_macro_history` | `SELECT date, cpi, core_cpi, unemployment, payrolls, gs2, gs10, pmi, fed_funds, hy_oas, consumer_sentiment, jobless_claims FROM macro_data`. |

### 3.2 Verified data-correctness findings (the heart of this spec)

These are confirmed by reading the ingestion, schema, writer, and reader — **not assumed**.

1. **`cpi` is the CPI *index level* (FRED `CPIAUCSL`), not YoY.** `MacroPage.tsx` relabels it "CPI YoY" — **wrong** (this is the original prompt's headline bug, and it is real). Same applies to `Fed Funds vs CPI`.

2. **`pmi` is actually CFNAI** (Chicago Fed National Activity Index). The ingestion map is explicit: `FRED_SERIES = {... "CFNAI": "pmi" ...}` (`src/api_fetch/fetch_macro_data.py:24`), and `macro_signal_engine.py:54` even comments *"This pmi is actually cfnai → below 0 suggests below-trend growth"*. CFNAI is centred on **0** (neutral = trend growth), not **50**. Labelling it "PMI" with no 0-line is misleading. → Must be renamed **"CFNAI (Chicago Fed National Activity Index)"**, neutral threshold **0**.

3. **`hy_oas` is actually FRED `BAA10Y`** (Baa-Treasury credit spread proxy), not a true HY OAS (`fetch_macro_data.py:26`). Label accordingly if surfaced.

4. **The derived inflation/policy fields are NOT persisted and the API cannot see them.** `fetch_macro_data.py` computes `cpi_yoy`, `core_cpi_yoy`, `real_policy_rate`, `yield_curve` (lines 97–102) — but the `macro_data` **schema only has the 12 raw columns** (`data/db_population.py:53-69`) and `insert_macro_data` (`db_writer.py:89`) **only writes those 12**. The derived columns are **silently dropped on insert**. Therefore `get_macro_history()` returns raw levels only; there is no persisted `cpi_yoy`.
   **Consequence:** the original's instruction to "derive YoY in the dashboard" is correct in spirit but must be implemented **server-side from the raw `cpi` column** (the API/compute layer), because neither the DB nor the current API exposes a YoY column. This is the central design constraint of the rework.

5. **The engine *does* recompute these features at runtime** in `src/signals_macro/macro_signal_engine.py:compute_macro_signals` (cpi_yoy, directions, accelerations, real_policy_rate, regime labels, `macro_supports_duration`) — but inside the **decision pipeline**, not persisted to `macro_data`. The dashboard must not import the engine path for allocation; it may, however, **reuse the same transform formulas** so the dashboard's numbers match the engine's (a deliberate "single definition of CPI YoY" choice — see §12 #3). Note a units subtlety to preserve: `real_policy_rate = fed_funds - (core_cpi_yoy * 100)` because `fed_funds` is in percent and `*_yoy` is a decimal fraction.

6. **ETF prices are already adjusted close (total-return-like).** `fetch_etf_prices.py:20` uses `yf.download(..., auto_adjust=True)` and stores it as `close`. So distributions **are** reinvested; the original's worry that "raw close understates bond ETF performance" is already mitigated. The correct fix is **labelling** ("Adjusted Close — distributions reinvested"), not a data change. There is no separate raw-close or explicit total-return-index column.

7. **`macro_data` is monthly (`MS` resample), ETF/yields rows are daily.** 294 macro rows vs ~17.7k ETF rows (per the migration spec's verified DB inventory). The dual-axis charts already keep each trace on its own date array — correct; do **not** force a shared daily index. Any merge of monthly macro onto daily ETF dates for forward-return analysis must **forward-fill only after the observation date** (look-ahead safety, §9).

8. **Point-in-time release dates are NOT available.** `macro_data.date` is the FRED *reference* month-start (`resample("MS")`), not the *release* date (CPI for month M is released ~mid M+1). Any forward-return or regime-conditioning analysis must surface this as a stated limitation and lag macro by at least one month as a conservative proxy (§9, §12 #4).

### 3.3 What already exists that we can reuse

- **Curve spread** is already computed in `api/services/macro.py:get_yield_curve` and tested (`api/tests/test_macro.py`).
- **The engine's regime vocabulary** (`monetary_regime ∈ {dovish,hawkish,neutral}`, `economic_regime ∈ {bullish,neutral,bearish}`, `macro_supports_duration`) is the authoritative regime model for *allocation* (`src/decision/regime_engine.py`). The dashboard's explanatory regimes (§5.4) should be **named distinctly** to avoid implying they drive trades, but may map to / cite the engine regimes for consistency.
- **Persisted regime traces** exist: `backtest_regime_trace` (per scenario, daily, full history) and live `regime_trace` (sparse). The dashboard can overlay the **backtest** regime trace (rich history) rather than the near-empty live one — a better choice than the original prompt's implicit reliance on the sparse live table.
- **Conventions to follow** (from the migration spec): `/api/v1` base path, `snake_case` JSON, ISO `YYYY-MM-DD` dates, NaN/Inf → `null` at the serialization boundary (`api/serialization/frames.py`), `NamedSeries`/`TableModel` primitives (`api/schemas/common.py`), TanStack Query hooks (`frontend/src/api/hooks.ts`), Plotly via the shared lazy `PlotlyLineChart` component.

---

## 4. Target architecture

```
┌─────────────────────────────────────────────────────────────┐
│ React SPA — MacroPage.tsx (redesigned) + new sub-components  │
│   snapshot cards · macro overview · yield curve ·            │
│   ETF/macro explorer · regime timeline · conditional returns │
└───────────────▲─────────────────────────────────────────────┘
                │ HTTP/JSON (NamedSeries / TableModel / cards)
┌───────────────┴─────────────────────────────────────────────┐
│ FastAPI — api/routers/macro.py (extended) + services/macro.py│
│   thin HTTP + orchestration; NO analytics math inline        │
└───────────────▲─────────────────────────────────────────────┘
                │ in-process import
┌───────────────┴─────────────────────────────────────────────┐
│ NEW pure-compute module: src/signals_macro/macro_features.py │
│   (pandas-only; NOT macro_signal_engine — see §12 #1/#3)     │
│   derive_macro_features · compute_*_features ·               │
│   classify_curve_regime · classify_macro_regime ·            │
│   compute_forward_returns ·                                  │
│   build_conditional_forward_return_table · validate_series · │
│   align_macro_to_market_dates                                │
│   operates on raw macro_data + etf_prices frames; NO I/O     │
└──────────────────────────────────────────────────────────────┘
```

**Design rule (inherited):** routers/services may import and call compute, but contain no analytics math. All derivations live in **pure functions** (no DB, no HTTP, no Streamlit/React) so they are unit-testable in isolation and reusable. This mirrors how `build_tearsheet` is structured.

---

## 5. Design, by phase

Phasing mirrors the original's intent (correctness → interpretation → redesign → regime → conditional) but re-targeted to the API/React seam. Each phase is independently shippable and testable.

### 5.0 Phase 0 (NOT for v1 — documented option only) — persist derived macro fields

**Decision (§12 #2): not done for v1 — derive at request time instead.** Documented here only as a future optimisation. Add `cpi_yoy, core_cpi_yoy, real_policy_rate, yield_curve` columns to the `macro_data` schema (`data/db_population.py`), extend `insert_macro_data` (`db_writer.py`) and `get_macro_history` (`db_reader.py`) to write/read them, and stop dropping the values `fetch_macro_data.py` already computes. **Risk:** schema migration on a populated DB (the writer has no `CREATE TABLE IF NOT EXISTS` guard for new columns; a `db_population.py` re-run DROPs data). **Recommendation: do NOT do this for v1** — derive server-side at request time (cheap; 294 monthly rows). Persistence is a later optimisation, and it would also touch the deferred reader/writer column-constants item (README item 8). Keep this phase as a documented option only.

### 5.1 Phase 1 — Data correctness (server-side derivation + correct labels)

New pure functions in `src/signals_macro/macro_features.py` (§12 #1) — signatures, house style:

```python
def compute_cpi_features(cpi_index: pd.Series) -> pd.DataFrame:
    """cpi_index (level) -> {cpi_index, cpi_yoy, cpi_yoy_change_3m, cpi_yoy_acceleration}.
    cpi_yoy = cpi_index.pct_change(12) * 100  (percent; 12 = monthly cadence).
    Must match macro_signal_engine's definition so dashboard == engine."""

def compute_activity_features(cfnai: pd.Series) -> pd.DataFrame:
    """{activity_level, activity_change_3m}; metadata: neutral=0, source='CFNAI'."""

def compute_labour_features(unemployment: pd.Series) -> pd.DataFrame:
    """{unemployment, unemployment_change_3m, unemployment_change_6m,
        unemployment_minus_12m_low}."""

def compute_policy_features(fed_funds: pd.Series, core_cpi_yoy: pd.Series) -> pd.DataFrame:
    """{fed_funds, fed_funds_change_3m, real_policy_rate}.
    real_policy_rate = fed_funds - core_cpi_yoy   (fed_funds in %, core_cpi_yoy in %)."""

def compute_yield_curve_features(gs2: pd.Series, gs10: pd.Series) -> pd.DataFrame:
    """{gs2, gs10, curve_spread, yield_2y_change_{1m,3m}, yield_10y_change_{1m,3m},
        curve_spread_change_3m}. curve_spread = gs10 - gs2 (pp). Yield changes in bp."""
```

**Units discipline (carried over, non-negotiable):** CPI YoY and curve spread in **percentage points**; yield *changes* in **basis points**; ETF returns as **decimal fractions**. The API returns raw numbers; formatting is the React layer's job (`frontend/src/lib/format.ts`). Each `NamedSeries.meta` carries `{ "unit": "pp" | "bp" | "pct" | "level" | "usd", "source": "CPIAUCSL", "frequency": "monthly", "neutral": 0 }` so the client can format and annotate without hardcoding.

**Endpoint change — endpoint 10 (`GET /api/v1/macro`) gains derived indicators.** Extend `_MACRO_INDICATORS` and `get_macro` so the FE can request `cpi_yoy`, `cpi_yoy_change_3m`, `activity_level`, `activity_change_3m`, `unemployment_change_3m`, `fed_funds_change_3m`, `real_policy_rate`, `curve_spread`, `yield_2y_change_3m`, `yield_10y_change_3m`, `curve_spread_change_3m`, etc., in addition to the raw levels. Each derived series carries correct `meta`. **Backward compatibility:** keep the existing raw keys (`cpi`, `pmi`, …) so nothing breaks; raw `cpi`/`pmi` get `meta.source`/`meta.note` so the client can label them honestly ("CPI Index", "CFNAI") instead of the current wrong labels.

**React (`MacroPage.tsx`) label fixes (immediate, low-risk):**
- Stop relabelling `cpi`→"CPI YoY". The ETF-vs-inflation charts default to the new `cpi_yoy` series labelled **"CPI YoY (%)"**; the index level, if shown, is labelled **"CPI Index"**.
- Rename `pmi` → **"CFNAI (Chicago Fed National Activity Index)"** with a **0** reference line and above/below-trend annotation.
- ETF price label → **"Adjusted Close (distributions reinvested)"**.
- Add a dual-axis caption: *"Independent axis scaling can make unrelated series appear correlated; this view compares timing/regime, not correlation."*

### 5.2 Phase 2 — Yield-curve interpretation

`classify_curve_regime(row) -> str` over `(delta_2y, delta_10y)` for a selected lookback → one of `bull_steepening | bear_steepening | bull_flattening | bear_flattening | mixed` (the original's sign logic, validated against bond conventions: bull = yields falling, steepening = 10Y falls less / rises more than 2Y). Endpoint 11 (`/macro/yield-curve`) extended to return: the existing gs10/gs2/spread series **plus** a `curve_regime` `NamedSeries` (categorical-over-time) and `inverted` shading intervals. React adds a zero spread line, inversion shading, hover with `{2Y, 10Y, spread, Δ over lookback, curve_regime}`. **Interpretation note (carried over):** an inversion is restrictive-policy + expected slowing, **not** an immediate TLT buy signal.

### 5.3 Phase 3 — Snapshot cards, explorer, display modes

- **Snapshot cards** (new endpoint `GET /api/v1/macro/snapshot`): latest value + observation date + direction/Δ-over-3m + correct unit + stale flag for CPI YoY, Δ CPI YoY (3m), CFNAI, Δ CFNAI, unemployment, Δ unemployment, fed funds, real policy rate, 2Y, 10Y, 10Y-2Y spread, current macro regime, current curve regime. **Each card carries its own observation date** — never show a monthly series as if it shared the daily yield date (original §12).
- **ETF/macro explorer:** React controls (ETF select, macro-indicator select over the level+change menu from the original §6, date range, level/change toggle, display mode). No six fixed charts as the primary view.
- **Display modes** (client-side over `NamedSeries`): dual-axis (with caption), indexed-to-100, rolling changes, scatter-vs-forward-return (X = Δ macro, Y = next-N ETF return, with zero lines + observation count, no causal claim). Scatter forward-return data comes from the Phase 5 endpoint.

### 5.4 Phase 4 — Macro-regime classifier + timeline overlay

`classify_macro_regime(row) -> str` — a transparent pure function over the derived features, emitting the original's five **explanatory** regimes: `inflationary_tightening | disinflationary_slowdown | stable_growth | stagflation_risk | easing_transition` (+ `insufficient_data`). **These are dashboard labels, named distinctly from the engine's `monetary_regime`/`economic_regime` to avoid implying they drive allocation** (§2 non-goal). The spec should document, per regime, the *expected* bond preference (SHY>AGG>TLT etc.) as a stated economic prior, explicitly flagged as a prior, not a fitted result.

New endpoint `GET /api/v1/macro/regime-timeline`: a `regime` `NamedSeries` (categorical over the macro date axis) for shading. React `MacroPage` adds a regime-timeline section: ETF adjusted-close line + subtle regime background shading (one regime per date, toggleable, legend explanations). Prefer overlaying onto a long ETF history; the regime series is monthly and forward-filled after its observation date.

### 5.5 Phase 5 — Conditional forward-return analysis

The most valuable section. Pure functions:

```python
def compute_forward_returns(prices: pd.Series, horizons: dict[str, int]) -> pd.DataFrame:
    """Forward total return over each horizon (trading days). Terminal-missing rows
    stay NaN. No future info leaks into feature construction."""

def build_conditional_forward_return_table(
    features_df: pd.DataFrame, regime_col: str, return_cols: list[str],
) -> pd.DataFrame:
    """Regime × ETF table: mean / median / hit-rate / count / std (+ optional
    worst/best) per forward horizon. Must not multiply rows on join."""
```

New endpoint `GET /api/v1/macro/conditional-returns` (params: `etf?`, `regime?`, `horizons?`, `date_range?`, `min_observations?`) → a `TableModel`. **Look-ahead discipline (non-negotiable):** macro is lagged to availability (≥1 month, §9) before being joined to ETF dates; features use only past info; forward returns are strictly future of the conditioning date. **Honesty requirements:** the response/UI must state it is **descriptive, not predictive**; surface the **overlapping-horizon** caveat (a 12M-forward series sampled monthly has ~12x autocorrelated, non-independent observations — do not present `count` as independent evidence); show observation counts and flag thin cells (`count < min_observations`). This is the operating-principle §4 made concrete: one historical path is weak, small-sample evidence.

---

## 6. Data contracts

Reuse `api/schemas/common.py` primitives. New/changed schemas in `api/schemas/macro.py`:

```python
class MacroResponse(BaseModel):          # endpoint 10 (extended)
    series: list[NamedSeries]            # each meta: {unit, source, frequency, neutral?, note?}

class YieldCurveResponse(BaseModel):     # endpoint 11 (extended)
    gs10: NamedSeries
    gs2: NamedSeries
    spread: NamedSeries                  # meta={"fill":"tozeroy"}
    curve_regime: NamedSeries            # NEW — categorical (numeric code in value + point.label; meta.categories), §12 #5
    inverted_intervals: list[dict]       # NEW — [{start, end}] for shading

class MacroSnapshotCard(BaseModel):      # NEW
    key: str; label: str
    value: float | str | None            # str for regime labels
    unit: str | None                     # "pp" | "bp" | "%" | "level" | None
    observation_date: str | None         # ISO; per-card, NOT shared
    change_3m: float | None
    direction: str | None                # "up" | "down" | "flat"
    is_stale: bool

class MacroSnapshotResponse(BaseModel):
    cards: list[MacroSnapshotCard]
    as_of: str

class RegimeTimelineResponse(BaseModel):  # NEW
    regime: NamedSeries                   # dashboard classifier — categorical (numeric code + point.label), §12 #5
    engine_regime: NamedSeries | None     # comparison overlay from backtest_regime_trace (§12 #6), same categorical form
    legend: dict[str, str]                # regime -> human description

class ConditionalReturnsResponse(BaseModel):  # NEW
    table: TableModel                     # columns: regime, etf, count, next_1m_mean, ...
    is_lagged: bool                       # macro lagged to availability proxy
    point_in_time_release_available: bool # False today (§3.2 #8) -> UI shows limitation note
    notes: list[str]                      # overlapping-horizon / descriptive-only caveats
```

All floats pass the existing NaN→null sanitizer; all dates pass the ISO normalizer (`api/serialization/frames.py`). **Categorical series wire format (§12 #5, RESOLVED):** `SeriesPoint` gains an optional `label: str | None`; `value` stays numeric and carries the ordinal **code** (drives stacking/colour/ordering), while `label` carries the display string. The series `meta.categories` holds the `{code: label}` map for the legend/colour scale. `value` is **not** widened to allow `str`, so every existing numeric chart and the float NaN→null boundary are untouched (additive, backward-compatible).

---

## 7. React component touch-points

- `frontend/src/pages/MacroPage.tsx` — restructure into the §17-style layout (snapshot cards → overview → yield curve → explorer → regime timeline → conditional returns → data quality/methodology).
- `frontend/src/api/types.ts` — add the new response types (kept in sync with `api/schemas`; regenerate from OpenAPI per the migration spec convention).
- `frontend/src/api/hooks.ts` — add `useMacroSnapshot()`, `useRegimeTimeline()`, `useConditionalReturns(params)`, extend `useMacro()`/`useYieldCurve()`.
- New components: `MacroSnapshotCards.tsx`, `MacroExplorer.tsx` (selectors + display-mode switch), `RegimeTimeline.tsx` (shading via Plotly shapes), `ConditionalReturnsTable.tsx`, `DataQualityPanel.tsx`. Reuse the shared lazy `PlotlyLineChart` and `DataTable`/`MetricGrid`.
- `frontend/src/lib/format.ts` — pp/bp/%/level/currency formatters keyed off `meta.unit`.
- Interpretation notes (collapsible) and tooltips (no `null`/`NaN`/raw column names; show source + observation date + Δ-over-lookback) per original §15–16.

---

## 8. Data-quality diagnostics

`validate_macro_series(name, values, metadata) -> list[str]` (pure) flags: CPI YoY outside a configurable band; CFNAI outside a plausible band (and explicitly **not** the 0–100 PMI rule — that only applies if the series were truly PMI, which it is not, §3.2 #2); negative unemployment; implausible yields; duplicate/non-monotonic dates; large unexplained jumps; stale latest observation; ETF price gaps. Surface via a collapsible `DataQualityPanel`; warnings never hard-fail the page — render valid sections and show warnings inline (original §14).

## 9. Mixed-frequency alignment & look-ahead safety

`align_macro_to_market_dates(macro_series, market_dates, availability_dates=None) -> pd.Series` (pure): forward-fill a monthly macro value onto daily market dates **only from its availability date forward**; never backfill into the reference month. Since point-in-time release dates are unavailable (§3.2 #8), default `availability_dates` to **reference month-end + ~1 month** as a conservative proxy (§12 #4, RESOLVED) and set `point_in_time_release_available=False` so the UI shows the limitation. This is the dashboard analogue of the engine's causal contract (`date < t`); the spec must treat look-ahead as the cardinal sin even in read-only analytics, because a forward-return table that leaks future macro would be quietly, dangerously wrong. **Accepted debt:** the flat one-month shift is a placeholder to be superseded by the user's planned forecasting/nowcasting system (what was *knowable* at `t`), not a per-series lag table — keep the proxy behind this single helper so the swap is localised.

## 10. Testing & verification

Follow the repo's domain test layout and markers. New pure-function tests (unit) + endpoint tests (API, `fastapi.testclient`):

- **CPI:** YoY = 12-month pct-change ×100 (pp); 3m change is a pp difference; index level is never returned labelled as YoY; missing monthly obs handled.
- **Activity:** CFNAI metadata neutral=0, source='CFNAI'; never labelled PMI; the PMI-50 rule is not applied.
- **Yield curve:** spread = 10Y − 2Y; inversion detection; all five curve-regime cases (bull/bear × steep/flat) + mixed.
- **Macro regime:** deterministic synthetic rows for each of the five regimes + insufficient_data.
- **Forward returns:** no future info in features; horizon alignment; terminal-missing stays NaN; counts correct; regime grouping preserves dates; **no row multiplication on join**; overlapping-horizon caveat present in response.
- **Data quality:** duplicate-date / staleness detection; implausible-value flags only on the right series; optional series may be absent without crashing.
- **API:** strict JSON (no `NaN`/`Infinity` tokens — extend the existing `test_macro_strict_json`); derived indicators present with correct `meta.unit`; snapshot cards carry per-card observation dates; conditional-returns response carries the limitation flags.
- **Regression guards preserved:** the existing `api/tests/test_macro.py` must keep passing (raw keys still present); no engine/backtest test perturbed (this spec touches none).

Manual verification: run the API on an alt port (not the user's :8000) per the verification convention, plus `npm --prefix frontend run dev`, and eyeball the redesigned page on a small viewport (original acceptance: readable on small screens).

## 11. Acceptance criteria

CPI index vs CPI YoY correctly separated and labelled; CFNAI renamed and interpreted at neutral 0; ETF prices labelled "Adjusted Close"; all units/frequencies explicit; yield-curve view has inversion + curve-regime interpretation; transparent macro-regime classifier (dashboard-only, distinct from engine regimes); regime shading on ETF charts; ETF/macro selector replaces the six fixed charts; level/change/indexed/forward-return display modes; conditional forward-return tables for TLT/AGG/SHY with sample-size & overlapping-horizon caveats; snapshot cards with per-card dates and stale flags; mixed-frequency alignment without look-ahead; data-quality warnings; meaningful tooltips; missing optional data does not crash; **no strategy/backtest change**; pure transforms unit-tested; existing tests green.

---

## 12. Resolved decisions

All six prior open questions are now decided (user sign-off 2026-06-14). They are binding for implementation.

1. **Where the pure functions live — `src/signals_macro/macro_features.py` (RESOLVED).** Not a new `src/macro_features/` package: `src/signals_macro/` already exists and already houses the macro signal logic (`macro_signal_engine.py`), matching the repo's `signals_macro` / `signals_price` convention. Add a **new, dependency-light module** `src/signals_macro/macro_features.py` (pandas only — no DB, HTTP, or engine-pipeline imports) exposing the pure derivations (`derive_macro_features`, `compute_*_features`, `classify_curve_regime`, `classify_macro_regime`, `compute_forward_returns`, `build_conditional_forward_return_table`, `validate_macro_series`, `align_macro_to_market_dates`). The API imports **this module**, not `macro_signal_engine` (which pulls in the heavier decision pipeline). This interlocks with decision 3 below.
2. **Derive at request time — yes (RESOLVED).** No schema migration; no persistence. Deriving from the 294 raw monthly rows on each request is cheap. Phase 0 (§5.0) is therefore **not done for v1** (kept documented as a future optimisation only).
3. **Single source of truth for "CPI YoY" — duplicate + pin-with-test (RESOLVED).** Do **not** edit the engine path to share a function. Instead, `macro_features.py` **copies** the formulas already in `macro_signal_engine.py` (`cpi_yoy = cpi.pct_change(12)`, `yield_curve = gs10 - gs2`, `real_policy_rate = fed_funds − core_cpi_yoy×100`, etc.), and a test **pins** them: assert `macro_features` output equals `macro_signal_engine.compute_macro_signals` output on shared input, so drift between the dashboard and the engine is caught in CI. This keeps the read-only boundary intact (the engine file is untouched).
4. **Macro availability-lag proxy — uniform "reference month-end + 1 month" (RESOLVED, with debt).** One constant, applied wherever a forward-looking calc happens (Phases 4–5 only); overlays (Phases 1–3) plot at reference date but are **labelled** "by reference month, not release date." It is conservatively *late* (slightly over-lags CPI, which releases mid-month). **⚠️ Technical debt, accepted deliberately:** this is an approximation, not point-in-time vintage data (FRED serves latest revisions; first-print values are not available without ALFRED). The user will **replace this with a forecasting/nowcasting system** that models what each macro value would plausibly have been *known to be* at time `t`, rather than a flat one-month shift. Until then, `point_in_time_release_available=False` and the UI states the limitation. A configurable per-series lag table was explicitly **not** chosen for v1.
5. **Categorical series wire format — numeric value + parallel label channel (RESOLVED).** Keep `SeriesPoint.value` strictly numeric (the existing NaN→null float boundary and every numeric Plotly/Recharts consumer stay untouched). Carry the category as an **ordinal code in `value`** (0/1/2/…, drives stacking/colour/ordering) **plus** a display string. Concrete form: extend `SeriesPoint` with an optional `label: str | None`, and carry the code→label map in the series `meta.categories` (e.g. `{"0":"Stable Growth","1":"Stagflation Risk",…}`) for the legend/colour scale. Additive and backward-compatible; do **not** widen `value` to allow `str`. (The single-scalar `MacroSnapshotCard.value` is a separate, non-series case and may stay `float | str | None` for a regime-label card.)
6. **Regime overlay source — both (RESOLVED).** Surface the dashboard's own `classify_macro_regime` output as the **primary** explanatory ribbon, **and** the engine's persisted `backtest_regime_trace` as a **comparison overlay** (toggleable), so users can see where the dashboard's transparent labels agree/disagree with the engine's allocation-driving regimes. Keep their vocabularies clearly distinct in the UI (§2 non-goal: dashboard labels must not be read as trade drivers).

---

## 13. SemVer

A new backward-compatible analytics feature (additive endpoints, redesigned page, new compute module; existing endpoints stay compatible) → **minor bump**. The dashboard is currently at V1.16.1; land this as the next minor (→ V1.17.0). The **bug-fix portion alone** — correcting the `cpi`→"CPI YoY" and `pmi`→"PMI" mislabels in `MacroPage.tsx` plus correct ETF-price labelling — is a defensible **standalone patch** that could ship first (it corrects misleading output without new features), with the larger redesign as the subsequent minor. Recommend splitting: a patch for the label corrections, then a minor for the regime/conditional redesign.

---

## Appendix: Original prompt

> The text below is the original rough prompt/idea for this document, preserved verbatim. It predates the V1.15.0 Streamlit→React/FastAPI migration, so its references to "Streamlit/Plotly dashboard" and "add to the macro page" map onto the React `MacroPage.tsx` + FastAPI macro service in the reworked spec above. Several of its technical premises were corrected against the real codebase in §3.

Task: Redesign the ETF vs Macro Dashboard for Correctness and Interpretability

Improve the existing Streamlit/Plotly ETFs vs Macro Indicators dashboard so the data is correctly labelled, economically meaningful, and easier to interpret.

The current dashboard contains:

TLT, AGG, and SHY compared with CPI
TLT, AGG, and SHY compared with a series labelled PMI
10-year yield, 2-year yield, and the 10Y–2Y spread
Unemployment versus consumer sentiment
Fed funds versus CPI

The current charts are visually useful, but several series appear to be mislabelled or presented in ways that could lead to incorrect conclusions.

The redesigned dashboard should help answer:

What macro regime is the economy currently in?
How have TLT, AGG, and SHY historically behaved during similar regimes?
Are inflation, growth, labour, and monetary policy improving or deteriorating?
Is the yield curve steepening or flattening, and why?
Which macro conditions have historically been supportive or harmful for each ETF?
Are any displayed values suspicious, stale, or incorrectly transformed?

Do not change strategy logic or backtest calculations in this task.

1. Inspect the Existing Implementation First

Before changing the UI:

Find the current macro-dashboard rendering module.
Identify the source dataframe and source column used for each displayed series.
Confirm the original source identifier, transformation, frequency, and units for:
CPI
the series currently labelled PMI
unemployment
consumer sentiment
Fed funds
2-year Treasury yield
10-year Treasury yield
TLT
AGG
SHY
Confirm whether ETF data uses:
raw close
adjusted close
a total-return series
Document any naming or unit mismatch in code comments or a small internal mapping structure.

Do not assume the existing labels are correct.

2. Correct CPI Labelling and Transformations

The line currently labelled CPI YoY (%) appears to be displaying the CPI index level rather than year-over-year inflation.

Create separate derived series:

cpi_index = CPIAUCSL
cpi_yoy = cpi_index.pct_change(12) * 100
cpi_yoy_change_3m = cpi_yoy.diff(3)

Use exact transformations appropriate to the actual data frequency.

The dashboard should distinguish clearly between:

CPI Index
CPI YoY (%)
3-Month Change in CPI YoY (percentage points)

Do not label an index level as a percentage.

For ETF-versus-inflation analysis, use CPI YoY (%) by default rather than the raw CPI index level.

Keep the CPI index available only if it has a clear analytical purpose.

3. Verify the Series Currently Labelled PMI

The current “PMI” series appears centred around zero and falls to approximately -16 during 2020.

That does not resemble a standard PMI index, which is normally interpreted around a neutral level of 50.

Inspect the underlying source.

Possible outcomes:

If the source is CFNAI

Rename it to:

Chicago Fed National Activity Index (CFNAI)

Interpretation:

0 = economic activity near historical trend
positive = above-trend growth
negative = below-trend growth

Add a horizontal reference line at 0.

If the source is an actual PMI series

Keep the name PMI, but:

Verify its level and units.
Add a horizontal reference line at 50.
Label:
above 50 as expansion
below 50 as contraction
If the source is another activity indicator

Use its correct name, source, units, and neutral threshold.

Do not keep the PMI label unless the underlying data is genuinely PMI.

4. Verify ETF Price Treatment

Confirm whether ETF prices use adjusted close or a total-return series.

For bond ETFs, distributions are economically important. Raw close alone may materially understate long-run performance.

Preferred behaviour:

Use adjusted close or total return where available.

Update labels to reflect the actual data:

TLT Adjusted Price
TLT Total Return Index
TLT Raw Close

Do not label all variants simply as Price if distributions are included.

If the existing data source does not support total return, keep the current source but clearly label it and add a short explanatory note.

5. Replace Misleading Dual-Axis Comparisons

Do not remove dual-axis charts entirely, but make clear that visual line overlap does not imply correlation or causation.

Add a caption such as:

Dual-axis charts are intended to compare timing and broad regime changes. Independent axis scaling can make unrelated series appear visually correlated.

Where possible, add more interpretable companion views.

For ETF and macro relationships, include at least one of the following:

ETF rolling return versus change in macro indicator
ETF forward return grouped by macro regime
scatter plot of macro change versus subsequent ETF return
normalised series indexed to 100
rolling correlation based on stationary transformations

Avoid calculating correlations between two trending level series such as CPI index level and ETF adjusted price.

6. Add a Macro Series Selector

Instead of hardcoding every ETF against every indicator, add controls that allow the user to select:

ETF:
- TLT
- AGG
- SHY

Macro indicator:
- CPI YoY
- Change in CPI YoY
- Activity indicator
- Change in activity indicator
- Unemployment rate
- Change in unemployment rate
- Consumer sentiment
- Fed funds rate
- Real policy rate
- 2-year yield
- 10-year yield
- 10Y–2Y spread
- Change in 2-year yield
- Change in 10-year yield
- Change in yield-curve spread

Preserve useful summary charts, but use a selector to avoid six nearly identical charts occupying the whole page.

Recommended layout:

Macro Overview
Yield Curve
ETF and Macro Explorer
Regime Analysis
Conditional Forward Returns
7. Add Direction and Momentum Transformations

Market reactions are often more sensitive to changes than absolute levels.

Add derived features where source data permits:

cpi_yoy
cpi_yoy_change_3m
cpi_yoy_acceleration

activity_level
activity_change_3m

unemployment_change_3m
unemployment_change_6m
unemployment_minus_12m_low

fed_funds_change_3m
real_policy_rate = fed_funds - cpi_yoy

yield_2y_change_1m
yield_2y_change_3m
yield_10y_change_1m
yield_10y_change_3m

curve_spread = yield_10y - yield_2y
curve_spread_change_3m

Use consistent units and labels.

Examples:

3M Change in CPI YoY: percentage points
3M Change in 10Y Yield: basis points
10Y–2Y Spread: percentage points

Do not mix decimal returns, percentage values, and basis-point changes without explicit formatting.

8. Improve Yield-Curve Interpretation

The current yield-curve chart should distinguish between:

normal curve
flattening
inversion
bull steepening
bear steepening
bull flattening
bear flattening

Use the changes in both the 2-year and 10-year yields.

Suggested classification:

if delta_2y < 0 and delta_10y < 0 and delta_2y < delta_10y:
    regime = "Bull steepening"
elif delta_2y > 0 and delta_10y > 0 and delta_10y > delta_2y:
    regime = "Bear steepening"
elif delta_2y < 0 and delta_10y < 0:
    regime = "Bull flattening"
elif delta_2y > 0 and delta_10y > 0:
    regime = "Bear flattening"
else:
    regime = "Mixed"

Adjust the exact logic where necessary based on sign conventions.

Add:

a zero reference line for the spread
clear shading for inverted periods
optional annotations for curve-regime transitions
hover details showing:
2Y yield
10Y yield
spread
changes over the selected lookback
curve regime

Do not treat inversion by itself as an immediate TLT buy signal.

9. Add a Macro Regime Classifier

Create a transparent, rule-based macro-regime classifier using existing indicators.

The goal is explanation, not optimisation.

Suggested initial regimes:

Inflationary Tightening
Inflation rising or accelerating
Fed funds rising or restrictive
2Y yield rising
Growth stable or still positive

Expected bond preference:

SHY > AGG > TLT
Disinflationary Slowdown
Inflation falling
Activity weakening
Unemployment rising or labour trend weakening
Fed easing or cuts increasingly expected
Yields falling

Expected bond preference:

TLT > AGG > SHY
Stable Growth / Controlled Inflation
Inflation stable or moderate
Growth near trend
Labour market stable
Policy broadly stable

Expected bond preference:

AGG
Stagflation Risk
Growth weakening
Inflation high, rising, or insufficiently decelerating
Fed unable to ease materially

Expected bond preference:

SHY or cash-like exposure
Easing Transition
Previously restrictive or inverted environment
Inflation falling
2Y yield falling
Fed cuts occurring or increasingly priced
Curve bull-steepening

Expected bond preference:

Increasing TLT exposure

Keep the classification logic isolated in a pure function.

Example:

def classify_macro_regime(row: pd.Series) -> str:
    ...

Do not silently embed the logic inside chart-rendering functions.

10. Add Regime Shading

Allow the user to overlay macro-regime shading on ETF charts.

Example:

Inflationary tightening
Disinflationary slowdown
Stable growth
Stagflation risk
Easing transition

Requirements:

Use subtle background shading.
Keep the ETF line readable.
Add hover or legend explanations.
Allow the user to toggle shading on and off.
Avoid showing more than one regime at a time for the same date.

The dashboard should make it easy to visually inspect how TLT, AGG, and SHY behaved during each regime.

11. Add Conditional Forward-Return Analysis

This should become one of the most useful sections of the dashboard.

For each ETF and macro regime, calculate subsequent total returns over:

1 month
3 months
6 months
12 months

Suggested table:

Regime	ETF	Observations	Next 1M Mean	Next 3M Mean	Next 6M Mean	Next 12M Mean	3M Hit Rate	3M Median

Include:

mean forward return
median forward return
hit rate
observation count
standard deviation
optional worst return
optional best return

Important:

Prevent overlapping-horizon calculations from being misrepresented as independent observations.
Clearly state that the table is descriptive and not proof of predictive power.
Use lagged macro information only.
Avoid look-ahead bias.
Do not use a macro observation before its actual release or availability date if point-in-time release data is already supported.
If point-in-time release dates are not supported, add a visible limitation note.

Add filters for:

ETF
Regime
Forward horizon
Date range
Minimum observation count
12. Add Macro Snapshot Cards

At the top of the page, add a concise current or latest-data snapshot.

Suggested cards:

CPI YoY
3M Change in CPI YoY
Activity Indicator
3M Change in Activity
Unemployment
3M Change in Unemployment
Fed Funds
Real Policy Rate
2Y Yield
10Y Yield
10Y–2Y Spread
Current Macro Regime
Current Curve Regime

Each card should show:

latest value
latest observation date
direction arrow or change
correct unit
stale-data warning where necessary

Examples:

CPI YoY
3.1%
↓ 0.4 percentage points over 3 months
As of 2026-04
10Y–2Y Spread
+0.42%
Bull steepening
As of 2026-05-29

Do not display monthly and daily series as though they share the same observation date.

13. Handle Mixed Frequencies Explicitly

The dashboard combines:

daily ETF data
daily Treasury yields
monthly CPI
monthly unemployment
monthly activity indicators
monthly consumer sentiment
policy-rate series

Add a reusable alignment policy.

Possible approach:

Macro series are forward-filled only after their observation date.
ETF and yield series remain daily.
Monthly macro release values are not backfilled into earlier dates.

Document the current limitation if true release dates are unavailable.

Do not accidentally introduce look-ahead bias by applying a monthly value to the start of its reference month when it would only have been known later.

Add a helper such as:

def align_macro_to_market_dates(
    macro_series: pd.Series,
    market_dates: pd.DatetimeIndex,
    availability_dates: pd.Series | None = None,
) -> pd.Series:
    ...
14. Add Data-Quality Diagnostics

Create a collapsible Data Quality section showing:

Series name
Source identifier
Frequency
Units
First date
Last date
Latest value
Missing values
Stale days
Transformation

Flag suspicious conditions:

CPI YoY outside a configurable plausible range
PMI outside 0–100 if it is actual PMI
unemployment below 0
yields outside plausible bounds
duplicate dates
non-monotonic date indexes
large unexplained jumps
stale latest observation
ETF price gaps

Do not hard fail the full page for non-critical issues.

Show warnings clearly and continue rendering valid sections.

15. Improve Tooltips

Every chart tooltip should show:

Date
ETF value
Macro value
Correct units
Macro change over selected lookback
Current macro regime
Current curve regime
Source series name
Observation date

Do not display raw column names where readable labels exist.

Do not show:

None
NaN
null

Omit unavailable fields.

16. Add Interpretation Notes

Add concise expandable explanations for each section.

Examples:

ETF and Inflation

Long-duration bonds usually benefit when inflation decelerates and yields fall. Inflation level alone is not sufficient; direction, expectations, and monetary-policy response matter.

Yield Curve

An inversion indicates restrictive short-term policy and expected future slowing, but it does not precisely time a duration rally. The direction of both 2-year and 10-year yields determines whether steepening is bond-friendly.

Labour and Sentiment

Unemployment is generally lagging, while sentiment is faster-moving but noisier. Their direction is often more useful than their absolute levels.

Conditional Returns

Historical forward returns describe what followed similar conditions in the sample. They do not guarantee future performance and may be sensitive to regime definitions and overlapping observations.

Keep these short and practical.

17. Recommended Page Layout

Use the following layout:

ETFs vs Macro Indicators

[Latest Macro Snapshot Cards]

[Data Quality Warnings, only when present]

Macro Overview
- Inflation
- Growth/activity
- Labour
- Policy

Yield Curve
- 2Y and 10Y yields
- spread
- inversion shading
- curve-regime classification

ETF and Macro Explorer
- ETF selector
- macro indicator selector
- date-range selector
- level/change selector
- dual-axis or normalised display mode

Macro Regime Timeline
- ETF total-return line
- regime shading
- regime explanation

Conditional Forward Returns
- regime × ETF table
- horizon controls
- observation-count warnings

Data Quality and Methodology
- source metadata
- transformations
- alignment rules
- limitations

Avoid displaying six nearly identical charts as the primary page view.

18. Display Modes

For the ETF and Macro Explorer, include:

Display mode:
- Dual axis
- Indexed to 100
- Rolling changes
- Scatter versus forward return
Dual Axis

Useful for comparing timing, with a warning about independent scaling.

Indexed to 100

Normalise both series at the selected start date:

indexed = series / series.iloc[0] * 100

Only use this where indexing is economically meaningful.

Rolling Changes

Examples:

ETF 3-month return
CPI YoY 3-month change
10Y yield 3-month change
Activity indicator 3-month change
Scatter Versus Forward Return

Example:

X-axis: 3M change in CPI YoY
Y-axis: next 3M TLT return

Include a zero line and observation count.

Do not imply causality.

19. Pure Functions to Add

Keep transformations separate from Streamlit rendering.

Suggested functions:

def compute_cpi_features(cpi: pd.Series) -> pd.DataFrame:
    ...
def compute_activity_features(activity: pd.Series) -> pd.DataFrame:
    ...
def compute_labour_features(unemployment: pd.Series) -> pd.DataFrame:
    ...
def compute_yield_curve_features(
    yield_2y: pd.Series,
    yield_10y: pd.Series,
) -> pd.DataFrame:
    ...
def classify_curve_regime(row: pd.Series) -> str:
    ...
def classify_macro_regime(row: pd.Series) -> str:
    ...
def compute_forward_returns(
    price_or_total_return_series: pd.Series,
    horizons: dict[str, int],
) -> pd.DataFrame:
    ...
def build_conditional_forward_return_table(
    features_df: pd.DataFrame,
    regime_col: str,
    return_cols: list[str],
) -> pd.DataFrame:
    ...
def validate_macro_series(
    series_name: str,
    values: pd.Series,
    metadata: dict,
) -> list[str]:
    ...
def align_macro_to_market_dates(
    macro_series: pd.Series,
    market_dates: pd.DatetimeIndex,
    availability_dates: pd.Series | None = None,
) -> pd.Series:
    ...
20. Testing Requirements

Add unit tests for all pure transformations.

CPI Tests

Verify:

CPI YoY is calculated using 12-month percentage change.
CPI YoY is expressed as percentage points.
3-month change is a difference in percentage points.
missing monthly observations are handled safely.
index level is not confused with YoY inflation.
Activity-Series Tests

Verify:

correct neutral threshold metadata
CFNAI is not labelled PMI
PMI, if present, uses a 50 threshold
malformed or missing metadata produces a safe fallback
Yield-Curve Tests

Verify:

spread equals 10Y - 2Y
inverted periods are correctly identified
curve-regime classification works for:
bull steepening
bear steepening
bull flattening
bear flattening
mixed movement
Macro-Regime Tests

Create deterministic synthetic cases for:

inflationary tightening
disinflationary slowdown
stable growth
stagflation risk
easing transition
insufficient data
Forward-Return Tests

Verify:

forward returns do not use future information in feature construction
horizon alignment is correct
missing terminal observations remain missing
observation counts are correct
grouping by regime preserves the correct dates
no row multiplication occurs during joins
Data-Quality Tests

Verify:

duplicate dates are detected
stale series are flagged
unit metadata is preserved
implausible PMI values are flagged only when the series is actual PMI
optional series may be missing without crashing the dashboard
21. Acceptance Criteria

The task is complete when:

CPI index and CPI YoY are correctly separated and labelled.
The series currently labelled PMI has been verified and renamed if necessary.
ETF price treatment is confirmed and correctly labelled.
The dashboard clearly identifies all units and observation frequencies.
The yield-curve view includes inversion and curve-regime interpretation.
The dashboard includes a macro-regime classifier.
ETF charts can display regime shading.
Users can select an ETF and macro indicator rather than relying only on six fixed charts.
Users can view level, change, indexed, and forward-return relationships.
Conditional forward-return tables are available for TLT, AGG, and SHY.
Macro snapshot cards show latest values, changes, and dates.
Mixed-frequency data is aligned without obvious look-ahead bias.
Data-quality warnings identify stale, missing, or suspicious series.
Hover tooltips contain meaningful economic context.
Missing optional data does not crash the page.
No strategy or backtest logic is changed.
No new dependency is introduced unless strictly necessary.
Pure transformation functions have unit tests.
Existing relevant tests continue to pass.
The page remains readable on smaller screens.
22. Implementation Order

Implement in this order:

Phase 1: Data Correctness
Inspect source mappings.
Correct CPI derivation and labels.
Verify the activity indicator.
Confirm ETF price or total-return handling.
Add series metadata and units.
Add data-quality checks.
Phase 2: Core Interpretation
Add derived direction and change features.
Improve the yield-curve chart.
Add curve-regime classification.
Add macro snapshot cards.
Add interpretation notes.
Phase 3: Dashboard Redesign
Add ETF and macro selectors.
Add display modes.
Reduce duplicate fixed charts.
Improve tooltips.
Add date-range controls.
Phase 4: Regime Analysis
Add macro-regime classification.
Add regime timeline.
Add ETF regime shading.
Add regime summary statistics.
Phase 5: Conditional Analysis
Add forward returns.
Add regime-conditioned return tables.
Add observation-count and methodology warnings.
Add optional scatter-versus-forward-return view.
23. Non-Goals

Do not:

Change portfolio-allocation rules.
Change strategy presets.
Change backtest execution.
Optimise macro-regime thresholds for maximum historical return.
Introduce machine learning.
Add a forecasting model.
Claim causality based on chart relationships.
Calculate correlations between trending raw levels without transformation.
Add a custom frontend dependency when Streamlit and Plotly are sufficient.
Hide uncertainty or small sample sizes.
Apply monthly macro values before they would reasonably have been observable.

24. Suggested PR Title
Correct and redesign ETF macro dashboard for regime interpretation
Suggested PR Description
This PR improves the correctness and interpretability of the ETF versus
macro dashboard.

It verifies source-series mappings, separates CPI index levels from CPI
YoY inflation, corrects the activity-indicator labelling, confirms ETF
price treatment, and adds explicit unit and frequency metadata.

The dashboard is reorganised around macro snapshots, yield-curve
interpretation, an ETF/macro explorer, macro-regime timelines, and
conditional forward-return analysis. It also introduces defensive data
quality checks, mixed-frequency alignment rules, richer tooltips, and
unit tests for the underlying transformations.

Strategy logic and backtest calculations are unchanged.
Core Product Principle

The dashboard should not merely place macro and ETF lines beside each other.

It should guide the user from:

These two series moved at the same time

to:

Inflation, growth, labour, policy, and the yield curve placed the market
in this regime; under similar historical conditions, these ETFs behaved
in this way, subject to these limitations and sample sizes.
