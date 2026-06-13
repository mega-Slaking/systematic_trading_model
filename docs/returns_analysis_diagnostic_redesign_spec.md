# Design Spec: Returns Analysis Diagnostic Redesign

> **Stack note (current state).** The live analytics frontend is a **FastAPI service (`api/`) + a Vite/React SPA (`frontend/src/`)**. The legacy Streamlit app has been retired (still launchable, but frozen — new features are React-only). This spec was originally drafted against Streamlit; all references have been re-pointed to the FastAPI + React architecture. The data flow for every view is:
>
> ```text
> db_reader (src/storage)  →  api/services/<view>.py  →  api/routers/<view>.py  (REST)
>                          →  frontend/src/api/hooks.ts  →  frontend/src/pages/<View>Page.tsx
>                          →  frontend/src/components/charts|tables/...
> ```
>
> Charts use **Plotly** via the shared lazy-loaded component `frontend/src/components/charts/plotlyComponent.ts` (heavy bundle code-split off the initial load); reusable wrappers are `PlotlyLineChart.tsx` and `ReturnsScatter.tsx` (WebGL `scattergl`). ETF Prices is the one view still on Recharts. Pure dataframe transforms belong in the **Python service layer** (testable under `api/tests/`); React handles only display.

## Goal

Redesign the existing `Returns Analysis` view so it functions as a focused strategy diagnostic tool rather than a dense all-scenario scatter plot.

The page should help answer:

1. Which scenarios produced unusually large daily gains or losses?
2. When did those events occur?
3. What exposure, rule, regime, turnover, or cost caused the result?
4. On which dates did scenario choice materially affect performance?
5. Are there suspicious returns that could indicate data or implementation issues?
6. Are the scenario variants genuinely different, or do they behave almost identically?

This page should not be treated as the primary strategy-ranking view. NAV, CAGR, Sharpe, Sortino, drawdown, and other tearsheet metrics should remain the main tools for comparing overall performance.

The purpose of this page is:

> Identify unusual daily behaviour, understand why it occurred, and trace it back to the strategy decision that produced it.

---

## Current Problem

The current chart displays every scenario simultaneously across the full backtest period.

This creates several usability problems:

- Too many overlapping points.
- Large, difficult-to-read legend.
- Long raw scenario IDs dominate the page.
- Colours are difficult to distinguish.
- Extreme observations are hard to attribute to a scenario.
- Parameter variants appear visually indistinguishable.
- The page does not explain why an unusual return occurred.
- The chart is visually dense but analytically shallow.
- The user must manually trace dates back through other tables or logs.

The current chart is useful as a high-level smoke alarm, but it is not yet effective as a diagnostic interface.

---

## Intended Use Cases

### 1. Identify Stress Dates

The chart should make it easy to find dates where a strategy experienced unusually large gains or losses.

Example diagnostic flow:

```text
Extreme daily return
→ scenario
→ date
→ portfolio weights
→ asset returns
→ strategy rule
→ regime
→ turnover and costs
```

Example result (regime fields mapped to the columns that actually exist — see **Available Data Sources**):

```text
Date: 2020-03-18
Scenario: Base / EWMA λ97 / TV 3%
Daily return: -5.8%
Weights: TLT 100%, AGG 0%, SHY 0%
Primary holding: TLT
Growth regime: bearish
Curve state: inverted
Macro supports duration: yes
Turnover: 0.0%
Transaction cost: 0.00%
```

### 2. Compare Scenario Risk

The chart should help determine whether some scenarios produce materially wider daily return distributions than others.

A wider vertical spread may indicate:

- Greater TLT exposure.
- Higher target volatility.
- Greater concentration.
- Different covariance estimates.
- More aggressive rebalancing.
- Future leverage or short exposure.
- Unexpected weight normalisation behaviour.

### 3. Determine Whether Parameter Sweeps Matter

If multiple scenarios overlap almost completely, this may indicate that:

- Core regime rules dominate the parameter choices.
- Volatility estimation changes do not materially affect allocations.
- Target-volatility differences are not large enough.
- Several registered presets are effectively duplicates.
- Scenario sweeps are adding complexity without changing behaviour.

The page should make scenario similarity visible rather than hiding it inside a dense cloud of points.

### 4. Detect Fat-Tail Behaviour

The page should highlight strategies that appear stable most of the time but produce occasional extreme returns.

This is especially relevant for a bond rotation strategy containing TLT, where rate shocks can create unusually large daily movements.

The user should be able to identify:

- Frequent moderate losses.
- Rare extreme losses.
- Rare extreme gains.
- Asymmetric return distributions.
- Stress periods where normal behaviour broke down.

### 5. Detect Data or Logic Problems

Large isolated returns outside expected volatile periods should be treated as potential diagnostics.

Possible causes include:

- Bad or stale price data.
- Missing-data joins.
- Incorrect return alignment.
- Duplicate dates or returns.
- Rebalance timing errors.
- Accidental leverage.
- Incorrect weight normalisation.
- Bad cost application.
- Look-ahead bias.
- Scenario registration errors.

The page should make suspicious observations easy to isolate and inspect.

---

## Scope

Modify the existing `Returns Analysis` view only — that is, the FastAPI returns endpoint/service backing it (`api/routers/backtest_results.py`, `api/services/backtest_results.py`) and the React page/components that render it (`frontend/src/pages/ReturnsPage.tsx`, `frontend/src/components/charts/ReturnsScatter.tsx`). A new dedicated service module (e.g. `api/services/returns_diagnostics.py`) is acceptable if it keeps the diagnostic transforms separable and testable.

The implementation should:

- Preserve existing return calculations.
- Reuse the existing FastAPI + React + Plotly infrastructure (the shared `plotlyComponent.ts` chart loader, the `NamedSeries`/`TableModel` payload primitives in `api/schemas/common.py`, the serialization helpers in `api/serialization/frames.py`, and the reusable `DataTable.tsx` / `ScenarioSelect.tsx` components).
- Avoid new dependencies (no new Python or npm packages).
- Use existing scenario, exposure, regime, turnover, cost, and NAV data where available (see the **Data Model** and **Available Data Sources** sections for what the DB actually exposes today).
- Degrade gracefully when optional diagnostic fields are missing.
- Avoid redesigning unrelated pages or tabs.
- Avoid changing strategy generation or backtest behaviour.

---

## Proposed Page Structure

```text
Returns Analysis

Short explanatory caption

[Scenario Controls]
[Date Controls]
[Return Filter Controls]

[Daily Return Scatter Plot]

[Selected Point / Diagnostic Drilldown]

[Worst Daily Returns]
[Best Daily Returns]
[Largest Scenario Dispersion Days]

[Optional Distribution Comparison]
```

Suggested caption:

> Inspect daily return behaviour across selected scenarios. Use filters to identify stress periods, outliers, and dates where scenario choices produced materially different outcomes.

---

## Controls

### 1. Scenario Selector

Add a multi-select control:

```text
Selected scenarios
```

Do not display every scenario by default.

The default selection should contain approximately three to five scenarios.

Suggested default selection logic:

1. `default`
2. Best Sharpe scenario, if summary metrics are available.
3. Best CAGR scenario, if summary metrics are available.
4. A representative covariance-lookback scenario.
5. A representative EWMA covariance scenario.

If summary metrics are not available, use deterministic representative defaults such as:

```text
default
baseV1_roll20
baseV1_roll20_covlb20_tv03
baseV1_roll20_ewmacov_lam94_tv03
legacyBase_roll20
```

Only include scenarios that exist in the current result set.

If more than eight scenarios are selected, display a warning:

> Showing many scenarios will reduce readability. Consider narrowing the selection or using an outlier filter.

Do not block the user from selecting more scenarios.

### 2. Scenario Family Filter

Add a scenario-family selector:

```text
Scenario family:
- All
- Default
- baseV1
- legacyBase
```

The filter should restrict the scenarios shown in the scenario multi-select.

Use parsed scenario metadata where possible.

Unknown or unparseable scenario IDs should remain available under `Other` or `All`.

### 3. Volatility Method Filter

Where scenario IDs contain parseable metadata, add:

```text
Volatility method:
- All
- Rolling
- Covariance lookback
- EWMA covariance
- Other
```

Possible ID mappings:

```text
roll → Rolling
covlb → Covariance lookback
ewmacov → EWMA covariance
```

This filter should be defensive.

If metadata cannot be parsed reliably, omit or disable the control rather than failing.

### 4. Target Volatility Filter

Where target-volatility metadata is available, add:

```text
Target volatility:
- All
- 2%
- 3%
- 4%
- 5%
- 7%
```

Example parsing:

```text
tv02 → 2%
tv03 → 3%
tv04 → 4%
tv05 → 5%
tv07 → 7%
```

The implementation must not assume every scenario contains target-volatility metadata.

### 5. Date Range Controls

Add date range presets:

```text
Date range:
- Full history
- COVID shock
- 2022 rate shock
- Last 3 years
- Custom
```

Suggested ranges:

```text
COVID shock:
2020-02-01 to 2020-06-30

2022 rate shock:
2022-01-01 to 2022-12-31
```

For `Last 3 years`, calculate the range relative to the maximum date in the loaded backtest data rather than the current system date.

For `Custom`, show start-date and end-date controls.

Ensure selected dates are clipped to the available data range.

### 6. Return Filter Mode

Add a control:

```text
Show:
- All daily returns
- Absolute return greater than 1%
- Absolute return greater than 2%
- Worst 1% by scenario
- Best 1% by scenario
- Best and worst 20 days by scenario
```

This is one of the most important readability improvements.

#### Filter Behaviour

##### All daily returns

Show all points within the selected scenarios and date range.

##### Absolute return greater than 1%

```python
abs(daily_return) > 0.01
```

##### Absolute return greater than 2%

```python
abs(daily_return) > 0.02
```

##### Worst 1% by scenario

Calculate the first percentile separately for each scenario and retain values less than or equal to that threshold.

##### Best 1% by scenario

Calculate the ninety-ninth percentile separately for each scenario and retain values greater than or equal to that threshold.

##### Best and worst 20 days by scenario

For each selected scenario, retain:

```text
20 highest daily returns
20 lowest daily returns
```

Handle scenarios with fewer than 40 observations gracefully.

### 7. Display Options

Optional controls:

```text
Show reference lines: Yes / No
Show distribution chart: Yes / No
Show raw scenario IDs in legend: Yes / No
```

The default should favour readability:

```text
Reference lines: Yes
Distribution chart: Yes
Raw IDs in legend: No
```

---

## Scenario Labels

Raw scenario IDs should not dominate the visual interface.

Create a helper:

```python
def format_scenario_label(scenario_id: str) -> str:
    """Convert a raw scenario ID into a concise readable label."""
```

Examples:

```text
default
→ Default

baseV1_roll20
→ Base / Roll 20

baseV1_roll20_covlb20_tv03
→ Base / Cov LB 20 / TV 3%

baseV1_roll20_ewmacov_lam94_tv05
→ Base / EWMA λ94 / TV 5%

legacyBase_roll20_ewmacov_lam97_tv04
→ Legacy / EWMA λ97 / TV 4%
```

Keep the full raw ID in hover tooltips and diagnostic tables.

Formatting must have a safe fallback:

```python
return scenario_id
```

Do not allow label parsing failures to break the page.

---

## Main Daily Return Scatter Plot

### Chart Purpose

The scatter plot should answer:

> When did unusual returns occur, and which selected scenario produced them?

Each point represents:

```text
One scenario’s return on one trading date
```

Axes:

```text
X-axis: Date
Y-axis: Daily Return
```

Each selected scenario should be represented as a separate trace.

Continue using WebGL rendering, such as `Scattergl`, where appropriate.

### Default Scenario Limit

The chart should initially render three to five scenarios.

Do not render all registered scenarios automatically.

Users may explicitly add more scenarios through the selector.

### Marker Styling

Recommended default marker settings:

```text
Size: 4 or 5
Opacity: 0.35 to 0.55
Marker outline: none
```

Example:

```python
marker={
    "size": 5,
    "opacity": 0.45,
}
```

Avoid large, fully opaque points.

If a focused or selected scenario interaction is implemented:

```text
Focused scenario:
- Marker size: 6
- Opacity: 0.85

Background scenarios:
- Opacity: 0.15 to 0.25
```

### Reference Lines

Add horizontal reference lines at:

```text
0%
+1%
-1%
+2%
-2%
```

The zero line should be visually stronger than the other reference lines.

The ±1% and ±2% lines should be subtle and should not overpower the data.

At minimum, implement:

```text
0%
+1%
-1%
```

### Axis Formatting

#### X-axis

```text
Title: Date
Type: date
```

Avoid overcrowded date labels.

Allow Plotly zooming and range selection.

#### Y-axis

```text
Title: Daily Return
Tick format: percentage
```

The axis should dynamically fit the selected data while retaining enough padding around extreme observations.

### Legend

Keep the Plotly legend enabled for toggling and isolation.

Use formatted scenario labels rather than raw IDs.

Position the legend so it does not consume excessive vertical space.

Possible layouts:

```text
Horizontal legend below controls and above chart
```

or:

```text
Vertical legend to the right when only a small number of scenarios are selected
```

The legend should be secondary to the explicit scenario controls.

---

## Hover Tooltip

The tooltip is the main diagnostic payload.

Each point should display as much of the following as is available:

```text
Date
Readable scenario label
Raw scenario ID
Daily return
NAV before or after return
Portfolio weights
Primary holding
Asset-level returns
Regime context     (inflation / growth / labour / curve_state / macro_supports_duration)
Turnover
Transaction cost
```

> The example below is illustrative of the *intended payload shape*. Map the regime/rule lines to the columns that actually exist (see **Available Data Sources**): there is no persisted per-day `rule_id` or "monetary/economic regime" string for backtests, so use the real regime-trace fields (`inflation_regime`, `growth_regime`, `labour_regime`, `curve_state`, `macro_supports_duration`) and omit anything unavailable rather than showing a placeholder.

Example:

```text
Date: 2020-03-18
Scenario: Base / EWMA λ97 / TV 3%
Daily return: -5.80%
NAV: 1.241
Weights: TLT 100%, AGG 0%, SHY 0%
Asset returns: TLT -6.02%, AGG -1.18%, SHY -0.05%
Primary holding: TLT
Growth regime: bearish
Curve state: inverted
Macro supports duration: yes
Turnover: 0.00%
Cost: 0.00%
Raw ID: baseV1_roll20_ewmacov_lam97_tv03
```

Attach the optional diagnostic fields to each trace as a parallel `customdata` array (built server-side, per point) and reference them in the Plotly `hovertemplate`.

Do not show placeholder values such as:

```text
None
NaN
null
```

Omit unavailable fields from the tooltip.

---

## Diagnostic Drilldown

### First-Pass Behaviour

Hover information plus diagnostic tables is sufficient for the initial implementation.

Do not make point-click functionality a blocker.

### Optional Point Selection

If supported cleanly by Plotly's React `onClick` event (the `plotly_click` callback exposed by `react-plotly.js`), selecting a point should populate a diagnostic panel. The selected point's `customdata` already carries the diagnostic payload (see **Hover Tooltip**), so the panel reads from local React state — no extra round-trip is required.

Possible panel contents (regime/rule fields limited to what is persisted — see **Available Data Sources**):

```text
Selected date
Selected scenario
Daily return
Portfolio weights
Asset-level returns
Regime context (inflation / growth / labour / curve_state / macro_supports_duration)
Turnover
Costs
NAV movement
```

Possible layout:

```text
Selected Return Event
────────────────────────────────
Date: 2020-03-18
Scenario: Base / EWMA λ97 / TV 3%
Daily return: -5.80%

Portfolio:
TLT: 100%
AGG: 0%
SHY: 0%

Regime:
Growth regime: bearish
Curve state: inverted
Macro supports duration: yes
```

If direct point selection is unreliable, do not add a new custom frontend dependency. Use tables and hover information instead.

> The diagnostic payload for hover/selection is assembled **server-side** (in the returns service) and shipped to the client as a parallel `customdata` array on each Plotly trace. React does not re-derive it; it only renders.

---

## Diagnostic Tables

Place the following tables below the scatter plot.

Use selected scenarios and the selected date range as the table input.

The return filter used by the chart should not necessarily restrict the tables unless explicitly intended. Tables should generally analyse the full selected date range.

### 1. Worst Daily Returns

Title:

```text
Worst Daily Returns
```

Purpose:

> Identify the most severe daily losses and trace them back to strategy decisions.

Default:

```text
20 rows across selected scenarios
```

Suggested columns (using the real available fields — see **Available Data Sources**):

```text
date
scenario_label
scenario_id
daily_return
primary_holding        (results.top_asset, or derived from weights)
tlt_weight
agg_weight
shy_weight
growth_regime          (from regime trace; plus other regime cols as desired)
curve_state
macro_supports_duration
turnover
total_cost
```

Sort:

```text
daily_return ascending
```

Use percentage formatting for:

```text
daily_return
weights
turnover
cost
```

### 2. Best Daily Returns

Title:

```text
Best Daily Returns
```

Purpose:

> Identify the largest gains and determine whether they resulted from intended exposure or accidental behaviour.

Use the same columns as the worst-return table.

Sort:

```text
daily_return descending
```

Default:

```text
20 rows across selected scenarios
```

### 3. Largest Scenario Dispersion Days

Title:

```text
Largest Scenario Dispersion Days
```

Purpose:

> Identify dates where scenario choice had the greatest effect on performance.

For each date across selected scenarios:

```python
dispersion = max(daily_return) - min(daily_return)
```

Suggested columns:

```text
date
dispersion
best_scenario_label
best_scenario_id
best_return
worst_scenario_label
worst_scenario_id
worst_return
scenario_count
```

Sort:

```text
dispersion descending
```

Default:

```text
20 rows
```

This table is particularly important because it reveals where parameter choices actually mattered.

Dates with low dispersion indicate that the selected scenarios behaved similarly.

Dates with high dispersion should be investigated through exposure and decision traces.

### 4. Optional Scenario Similarity Table

A useful later addition is a scenario return-correlation matrix or pairwise similarity table.

Possible columns:

```text
scenario_a
scenario_b
return_correlation
mean_absolute_return_difference
maximum_return_difference
```

This is optional and should not block the initial implementation.

Its purpose is to identify scenarios that are effectively duplicates.

---

## Distribution Comparison

Add a companion chart beneath the diagnostic tables or directly below the scatter plot.

### Recommended First Implementation: Boxplot

The scatter plot answers:

> When did returns happen?

The boxplot answers:

> How do the selected return distributions differ?

Use one box per selected scenario.

Show:

- Median.
- Interquartile range.
- Whiskers.
- Outliers.
- Formatted scenario labels.

Limit this chart to the selected scenarios.

Avoid plotting all scenarios.

### Optional Distribution Modes

A later version may allow:

```text
- Boxplot
- Histogram
- Violin plot
```

Do not implement multiple modes unless the architecture makes it straightforward.

A single boxplot is sufficient for the first pass.

---

## Available Data Sources

The enriched diagnostic frame is assembled in the **Python service layer** from the canonical `db_reader` functions in `src/storage/db_reader.py`. The fields actually available today (no schema changes are in scope) are:

- **`get_backtest_results(scenario_id=None)`** — the primary source. Columns: `date`, `scenario_id`, `nav_pre`, `nav`, `ret` (the daily return), `turnover`, `fee_cost`, `slippage_cost`, `total_cost`, `gross_trade_notional`, `weights` (a JSON string parsed via `accounting.tearsheet_calculator.parse_weights` into a `{ticker: weight}` dict), `n_positions`, `top_asset`, `top_weight`. Note `top_asset`/`top_weight` already give the dominant holding directly.
- **`get_backtest_regime_trace(scenario_id=None)`** — per (`date`, `scenario_id`) regime fields: `inflation_regime`, `growth_regime`, `labour_regime`, `curve_state`, `macro_supports_duration`. (The `regime_match_rate` metric in `api/services/tearsheet.py` already demonstrates merging this trace onto results on `["date", "scenario_id"]`.)
- **`get_etf_history(tickers=None)`** — ETF close prices (`date`, `ticker`, `close`); per-asset daily returns can be derived from these if the diagnostic wants asset-level return context.

There is **no** persisted per-day `rule_id` / "monetary regime" / "economic regime" / decision-trace table for backtests today. The diagnostic must therefore use the regime-trace columns that *do* exist (above) and omit anything unavailable rather than inventing fields. The earlier draft's `rule_id` / `monetary_regime` / `economic_regime` examples are illustrative of intent only; map them to the real columns (e.g. surface `inflation_regime` / `growth_regime` / `curve_state` / `macro_supports_duration` as the regime context).

## Data Model

The existing returns service begins with data similar to:

```text
date
scenario_id
ret   (the daily return)
```

Create an enriched diagnostic dataframe in the service layer.

Suggested schema (using the real available columns; rename `ret -> daily_return` for clarity in the diagnostic frame):

```python
returns_diag_df:
    date
    scenario_id
    scenario_label
    daily_return            # from results.ret
    nav
    tlt_weight              # parsed from results.weights
    agg_weight
    shy_weight
    primary_holding         # from results.top_asset, or derived from weights
    turnover
    total_cost
    # regime context (left-joined from get_backtest_regime_trace):
    inflation_regime
    growth_regime
    labour_regime
    curve_state
    macro_supports_duration
    # optional, derived from get_etf_history if asset-level context is wanted:
    tlt_return
    agg_return
    shy_return
```

Not every field is required.

The minimum required columns are:

```text
date
scenario_id
daily_return   (ret)
```

All optional diagnostic joins should be left joins.

Missing optional fields must not prevent the view from rendering.

---

## Join Behaviour

Possible join keys:

```text
date
scenario_id
```

or, where the project uses scenario run identifiers:

```text
date
scenario_id
scenario_run_id
```

Use the actual stable keys already present in the project. In this codebase that is **`["date", "scenario_id"]`** — the key on which `api/services/tearsheet.py` already merges the regime trace onto results.

Source dataframes (mapped to the real `db_reader` functions; several "potential sources" from the original draft are in fact columns of `get_backtest_results`, not separate tables):

```text
results_df         -> get_backtest_results()      # carries ret, nav, weights, turnover, costs, top_asset/top_weight
regime_trace_df    -> get_backtest_regime_trace() # inflation/growth/labour/curve_state/macro_supports_duration
asset_prices_df    -> get_etf_history()           # optional, to derive per-asset returns
```

Before joining, validate uniqueness of expected keys.

Avoid many-to-many joins that duplicate daily return rows.

Suggested validation:

```python
assert not results_df.duplicated(["date", "scenario_id"]).any()
```

Where duplicates are valid in the underlying structure, aggregate or select the correct record before joining.

---

## Primary Holding Logic

Add a helper to determine the dominant exposure:

```python
def determine_primary_holding(row: pd.Series) -> str | None:
    """Return the asset with the highest absolute portfolio weight."""
```

For long-only strategies:

```text
highest portfolio weight
```

For future long/short strategies:

```text
highest absolute portfolio weight
```

If all weights are zero, return:

```text
Cash
```

If weights are unavailable, return `None`.

---

## Scenario Metadata Parsing

Add:

```python
def parse_scenario_metadata(scenario_id: str) -> dict:
    """
    Extract scenario metadata where possible.

    Expected output:
    {
        "family": str | None,
        "lookback": int | None,
        "vol_method": str | None,
        "cov_lookback": int | None,
        "ewma_lambda": float | None,
        "target_vol": float | None,
    }
    """
```

Example:

```text
baseV1_roll20_ewmacov_lam94_tv03
```

Expected result:

```python
{
    "family": "baseV1",
    "lookback": 20,
    "vol_method": "ewmacov",
    "cov_lookback": None,
    "ewma_lambda": 0.94,
    "target_vol": 0.03,
}
```

Parsing must be permissive and defensive.

Unknown components should not raise exceptions.

---

## Recommended Functions

### Formatting

```python
def format_scenario_label(scenario_id: str) -> str:
    """Convert a raw scenario ID into a readable display label."""
```

### Metadata Parsing

```python
def parse_scenario_metadata(scenario_id: str) -> dict:
    """Extract scenario family, method, lookback, lambda, and target vol."""
```

### Diagnostic Frame

```python
def build_returns_diagnostic_frame(
    results_df: pd.DataFrame,
    regime_trace_df: pd.DataFrame | None = None,
    asset_prices_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Build the enriched daily-return diagnostic dataframe.

    Required input:
    - results_df  (get_backtest_results: ret, nav, weights, turnover,
                   costs, top_asset/top_weight)

    Optional inputs (left-joined on ["date", "scenario_id"]):
    - regime_trace_df  (get_backtest_regime_trace)
    - asset_prices_df  (get_etf_history, to derive per-asset returns)

    NAV, weights/exposures, turnover, and costs are already columns of
    results_df, so they need no separate join. Parse the JSON ``weights``
    column into per-ticker weights (and primary holding) here.
    """
```

### View Filtering

```python
def filter_returns_for_view(
    df: pd.DataFrame,
    selected_scenarios: list[str],
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    filter_mode: str,
) -> pd.DataFrame:
    """Apply scenario, date, and return filters."""
```

### Scatter Construction

```python
def build_daily_return_scatter(
    df: pd.DataFrame,
    show_reference_lines: bool = True,
) -> go.Figure:
    """Build the daily-return diagnostic scatter plot."""
```

### Distribution Chart

```python
def build_return_distribution_boxplot(
    df: pd.DataFrame,
) -> go.Figure:
    """Build a boxplot comparing selected scenario return distributions."""
```

### Diagnostic Tables

```python
def build_worst_returns_table(
    df: pd.DataFrame,
    limit: int = 20,
) -> pd.DataFrame:
    """Return the worst daily observations across selected scenarios."""
```

```python
def build_best_returns_table(
    df: pd.DataFrame,
    limit: int = 20,
) -> pd.DataFrame:
    """Return the best daily observations across selected scenarios."""
```

```python
def build_scenario_dispersion_table(
    df: pd.DataFrame,
    limit: int = 20,
) -> pd.DataFrame:
    """Return dates with the largest spread between scenario returns."""
```

---

## Client State

Hold the control state in React (`useState` in `ReturnsPage.tsx`, or a small reducer if it grows). Preserve across interactions:

```text
Selected scenarios
Scenario family
Volatility method
Target volatility
Date preset
Custom dates
Return filter mode
Display options
```

Server reads are cached by TanStack Query (see `frontend/src/api/hooks.ts`); the diagnostic payload should be fetched once per scenario set and filtered client-side where cheap, mirroring how `useReturns` fetches the full scatter once and the legend toggles scenarios. (If filtering is pushed server-side instead, key the query on the filter args so cache invalidation stays clean — the existing hooks already pass `scenario_ids` as a query key.)

Avoid resetting user selections unnecessarily when interacting with other controls.

When family or metadata filters remove a selected scenario from the available set, update the selected scenarios safely.

Do not allow the multi-select default to reference unavailable options.

---

## Performance Considerations

The full dataset may contain:

```text
many scenarios × thousands of dates
```

The redesign should improve performance by plotting only selected scenarios.

Recommended order of operations:

1. Filter to selected scenarios.
2. Filter to selected date range.
3. Apply return filter.
4. Build Plotly traces.
5. Build optional hover custom data only for the remaining points.

Use vectorised Pandas operations.

Avoid row-by-row dataframe loops where possible.

Continue using WebGL scatter rendering for large filtered datasets.

Cache enriched diagnostic data where appropriate, but do not cache widgets or user-specific filtered views incorrectly.

---

## Empty and Error States

### No Scenarios Selected

Display:

> Select at least one scenario to view daily returns.

Do not render an empty chart.

### No Data in Selected Date Range

Display:

> No return observations are available for the selected scenarios and date range.

### No Data After Return Filter

Display:

> No returns match the selected return filter. Try a lower threshold or a broader date range.

### Missing Optional Diagnostic Data

Render the chart normally.

Only include available hover and table fields.

Optionally show a small informational note:

> Exposure or decision-trace details are unavailable for some observations.

Do not show an error unless required data is missing.

---

## Testing Requirements

Add unit tests for the pure transform/filter functions. Since these live in the **Python service layer**, the tests belong under `api/tests/` (e.g. `api/tests/test_returns_diagnostics.py`), alongside the existing `pytest` suite — the same place `test_serialization.py`, `test_backtest_results.py`, etc. live. Keeping the diagnostic logic in Python (not React) is precisely what makes it cheaply unit-testable.

### Scenario Label Tests

Test examples:

```text
default
baseV1_roll20
baseV1_roll20_covlb20_tv03
baseV1_roll20_ewmacov_lam94_tv05
legacyBase_roll20_ewmacov_lam97_tv04
unknown_custom_scenario
```

Verify:

- Expected readable labels.
- Unknown IDs safely fall back.
- No exceptions for malformed IDs.

### Metadata Parsing Tests

Verify parsing of:

```text
family
lookback
volatility method
covariance lookback
EWMA lambda
target volatility
```

Verify malformed and partial IDs return `None` values rather than raising.

### Return Filter Tests

Verify:

- All returns.
- Absolute return above 1%.
- Absolute return above 2%.
- Worst 1% per scenario.
- Best 1% per scenario.
- Best and worst 20 per scenario.
- Empty data.
- Small scenarios with fewer than 20 observations.

### Dispersion Tests

Given returns for several scenarios on the same date, verify:

```python
dispersion == maximum_return - minimum_return
```

Verify:

- Best scenario is correct.
- Worst scenario is correct.
- Missing scenario observations do not fail.
- Dates with only one scenario are either excluded or explicitly return zero dispersion.

Preferred behaviour:

```text
Exclude dates with fewer than two scenario observations.
```

### Join Tests

Verify:

- Optional dataframes may be `None`.
- Left joins preserve all return rows.
- Missing optional records produce nulls rather than dropped rows.
- Duplicate join keys are detected or handled.
- Enrichment does not multiply return observations.

---

## Acceptance Criteria

The redesign is complete when:

1. The page no longer displays every scenario by default.
2. The default chart contains approximately three to five scenarios.
3. Users can select and remove scenarios explicitly.
4. Users can filter scenarios by family.
5. Volatility-method and target-volatility filters are included where metadata is parseable.
6. Users can select full history, stress periods, recent history, or custom dates.
7. Users can filter to outlier returns.
8. Long raw scenario IDs no longer dominate the page.
9. Raw scenario IDs remain available in hover details and tables.
10. The chart uses smaller, partially transparent markers.
11. The chart includes useful horizontal return reference lines.
12. Hovering a point provides meaningful diagnostic context.
13. The page includes worst-return and best-return tables.
14. The page includes a largest-dispersion-days table.
15. Missing optional diagnostic fields do not crash the page.
16. Existing return and backtest calculations remain unchanged.
17. No unrelated pages are redesigned.
18. No new dependency is added unless strictly necessary.
19. Pure transformation and filtering functions have tests.
20. The implementation remains usable on smaller screens.

---

## Implementation Priority

Implement in this order.

### Phase 1: Core Readability

1. Add scenario multi-select.
2. Limit default scenarios.
3. Add readable scenario labels.
4. Reduce marker size and opacity.
5. Improve legend layout.
6. Add date range controls.

### Phase 2: Diagnostic Filtering

7. Add return filter modes.
8. Add scenario-family filter.
9. Add volatility-method filter.
10. Add target-volatility filter.
11. Add horizontal reference lines.

### Phase 3: Diagnostic Context

12. Build enriched diagnostic dataframe.
13. Add weights and primary holding to hover.
14. Add rule and regime information to hover.
15. Add turnover, costs, NAV, and asset returns where available.

### Phase 4: Diagnostic Outputs

16. Add worst daily returns table.
17. Add best daily returns table.
18. Add largest scenario dispersion table.
19. Add return-distribution boxplot.

### Phase 5: Optional Interaction

20. Add selected-point drilldown if supported cleanly.
21. Add scenario similarity diagnostics if useful.
22. Add linked decision-trace navigation in a later PR.

---

## Non-Goals

Do not:

- Change strategy logic.
- Change backtest calculations.
- Change return calculations.
- Change scenario generation.
- Change preset registration.
- Add leverage, shorting, or cash-buffer behaviour.
- Redesign the full React dashboard or other tabs/views.
- Build a complete trade debugger in this PR.
- Add a bespoke JavaScript charting component solely for point-click behaviour (use Plotly's built-in `plotly_click` event instead).
- Add dependencies for functionality already available through Pandas (service layer), FastAPI, or Plotly/React (frontend).
- Remove existing tearsheet views.
- Use this page as the primary strategy-ranking interface.

---

## Suggested File Organisation

Follow the project's established FastAPI + React layout (do not invent a new convention). The diagnostic logic splits cleanly into a Python compute/serialization tier and a React render tier:

```text
# Python tier (compute + JSON boundary, unit-tested under api/tests/)
src/storage/db_reader.py                  # existing readers (unchanged)
api/services/returns_diagnostics.py       # NEW: scenario parsing, label formatting,
                                          #      diagnostic enrichment, filtering,
                                          #      outlier + dispersion calculations
api/schemas/backtest.py                   # extend / add response models
api/routers/backtest_results.py           # extend the /returns route (or add a sibling)
api/serialization/frames.py              # reuse df_to_series / df_to_table / nan_to_none

# React tier (render only)
frontend/src/api/hooks.ts                 # add/extend the returns hook
frontend/src/pages/ReturnsPage.tsx        # controls + layout
frontend/src/components/charts/ReturnsScatter.tsx     # extend (markers, ref lines, customdata)
frontend/src/components/charts/PlotlyLineChart.tsx    # reuse for the boxplot/distribution if line-shaped
frontend/src/components/tables/DataTable.tsx          # reuse for worst/best/dispersion tables
```

Do not force a finer-grained structure than the repo already uses; small extra React components (e.g. a `ReturnsControls`) are fine if they keep `ReturnsPage.tsx` readable.

Prefer small pure (Python) functions for:

```text
Scenario parsing
Label formatting
Filtering
Diagnostic enrichment
Outlier calculations
Dispersion calculations
```

Keep React rendering logic separate from the dataframe transformation logic — the transforms live in the Python service tier, React only displays the resulting `NamedSeries` / `TableModel` / `customdata` payloads.

---

## Suggested PR Title

```text
Improve Returns Analysis with scenario filters and diagnostic drilldowns
```

---

## Suggested PR Description

```text
This PR redesigns the Returns Analysis page as a focused daily-return
diagnostic tool.

The existing view rendered every scenario simultaneously, creating an
unreadable legend and heavily overlapping scatter points. The updated
view limits default scenario selection, adds readable labels, scenario
and date filters, outlier display modes, richer hover information, and
diagnostic tables for the best days, worst days, and dates with the
largest scenario dispersion.

The underlying backtest and return calculations are unchanged. Optional
exposure, decision-trace, regime, turnover, cost, NAV, and asset-return
data are joined defensively so missing diagnostic data does not prevent
the page from rendering.
```

---

## Core Product Principle

The final page should behave like a microscope rather than a poster.

It should not attempt to show every scenario and every observation at once.

It should guide the user from:

```text
Something unusual happened
```

to:

```text
This scenario produced this return on this date because it held these
assets under this rule and regime.
```
