# Design Spec: Volatility Features Diagnostic Dashboard

## 1. Objective

Refactor the existing **Volatility Features** view from a raw estimator-comparison chart into an interpretable volatility **diagnostic** dashboard, and expose the underlying features through a stable typed interface that strategy and risk layers *can* consume later — without changing any allocation, sizing, or execution behaviour during this work.

The current implementation displays point-in-time, annualised volatility estimates for one asset:

* Rolling 20-day volatility (`rolling_20`)
* Rolling 60-day volatility (`rolling_60`)
* EWMA volatility, λ = 0.94 (`ewma_94`)
* EWMA volatility, λ = 0.97 (`ewma_97`)
* GARCH(1,1) (`garch`)

Today the view answers only:

> What volatility does each estimator calculate for this asset?

The redesigned view progressively answers:

1. Is current volatility high or low relative to the asset's **own** history? (Phase 1)
2. Is volatility expanding, stable, or contracting? (Phase 2)
3. What single, explainable volatility **state** are we in? (Phase 3)
4. Do the estimators broadly agree? (Phase 4)
5. Is the volatility move associated with favourable or adverse price behaviour? (Phase 5)
6. When did meaningful transitions occur, shown clearly on the chart? (Phase 6)
7. Is one asset becoming unusually risky relative to the others? (Phase 7)
8. Are the volatility **estimates themselves** stable? (Phase 8)
9. What historically followed similar states, with honest sample sizes? (Phase 9)
10. How can other layers safely consume these features, with full reproducibility metadata? (Phase 10)

The product principle:

> Compute and present volatility *level, direction, state, estimator agreement, stability, and historical consequences* as plain-language diagnostics — never as automatic trading actions during this build.

---

## 2. Architecture context

The live analytics frontend is the **FastAPI + React** stack. The Streamlit → React migration completed across V1.12.0–V1.16.0; **Streamlit is frozen legacy** and new features are React-only. The feature-computation layer is UI-agnostic and is the durable core of this plan; only the rendering surface, API layer, and data-access path differ from the original Streamlit draft.

**Layer contract (do not violate):**

| Layer | Target | Rule |
| ----- | ------ | ---- |
| Compute | pure functions under `src/volatility/` | All feature maths lives here. UI-agnostic, fully unit-testable, no I/O. |
| Persistence | `volatility_features` table via `src/storage/db_reader.get_volatility_features` | **Source of the raw estimator surface only.** Already lagged one day (see §4). Unchanged by this work. |
| API | `api/routers/volatility.py` → `api/services/volatility.py` → Pydantic schemas in `api/schemas/volatility.py` | Services **call** `src/volatility/` pure functions and shape typed responses. **No feature-calc logic in handlers.** TTL-cached via `api/cache.py`. NaN→null + ISO dates at the boundary via `api/serialization/frames.py`. |
| UI | `frontend/src/pages/VolatilityPage.tsx` + reusable charts under `frontend/src/components/charts/` | **Presentation only.** Consumes typed responses; builds Plotly traces from typed data. **No feature-calc logic and no chart objects built server-side.** |

Hard architectural decisions, applied throughout:

* React is the active frontend; Streamlit is frozen and must not be extended.
* All feature calculations are pure functions in `src/volatility/`. None in API handlers; none in React.
* The persisted `volatility_features` surface is the **raw estimator source**. Derived Phase 1–8 features are **computed on demand**, not persisted.
* The persisted surface is **already lagged one day**. Derived features are computed on the already-lagged columns and **never shifted twice**.
* Every calculation is isolated by `config_key` (§4). Series from different configs are never mixed.
* Strategy, portfolio, sizing, and execution behaviour are **unchanged** in every phase.

---

## 3. Product terminology

Use these terms precisely. Before Phase 9 the dashboard presents **features and diagnostic states**; it must never imply a diagnostic state is a validated trading signal.

* **Feature** — a computed numeric quantity derived from the raw estimator surface (e.g. a historical percentile, a 20D/60D ratio, an estimator-dispersion value). Descriptive, point-in-time, no claim of predictive value.
* **Diagnostic state** — a human-readable label produced deterministically from features (e.g. `Calm`, `Normalisation`, `Adverse Shock`). A *description of the current configuration of features*, not evidence about the future.
* **Validated signal** — a diagnostic state for which Phase 9 has measured forward outcomes on a sufficient, sample-quality-labelled basis. Only Phase 9 can promote a diagnostic state toward this status, and even then with explicit sample caveats.
* **Strategy input** — a stable, typed, point-in-time snapshot (Phase 10) that other layers *could* consume. Producing it does **not** wire it into allocation; that is explicitly out of scope.

---

## 4. Data and information-time contracts

### 4.1 The surface is already lagged one day

`src/volatility/feature_surface.py` builds the surface and, at the end of the build, shifts **every** non-key column by `lag_features_days` (default 1) within each ticker (`_lag_feature_columns`). Therefore the value stored at row `t` is what was computable at the **close of `t-1`**.

Consequences enforced throughout this plan:

* Percentiles, directions, term ratios, dispersion, and vol-of-vol are computed **on the already-lagged columns**. They are **never re-shifted**. Including the current (already-lagged) observation in its own percentile reference set is "as-of `t`" and causal — it is correct, not a leak.
* This is the single most common subtle bug here: do not "be safe" by adding another `.shift(1)`. The contract is **one lag, applied once, in `feature_surface.py`**.

### 4.2 Snapshot information-time contract

Every per-asset snapshot dated `t` carries information as follows:

* **Volatility** features: information through **`t-1`** (the one-day surface lag).
* **Price-direction** features (Phase 5): information through **`t-1`** (deliberately matched — see §4.4), so the snapshot is internally consistent and usable for a decision *on* `t`.
* **Forward returns** (Phase 9): from **unlagged** adjusted prices strictly **after** `t`. The state comes from the lagged surface; the forward return does not. Never mix these date conventions.

Phase 10 makes this explicit in the snapshot via two distinct fields: `as_of_date` (the decision/snapshot date `t`) and `information_through_date` (the final market date actually used; `= t-1` for the one-day-lagged surface).

### 4.3 config_key isolation

`volatility_features` carries a `config_key` column (`config_key = str(VolatilityFeatureConfig.cache_key())`, written per `(date, ticker)` in `run_backtest.py`). The persisted surface is scenario-independent — one row per `(date, ticker)`. All derived features must be computed **within a single `config_key`**; never mix rows from different volatility configs into one percentile / ratio / dispersion / vol-of-vol series. `config_key` propagates into every cache key (§7) and into the Phase 10 snapshot metadata.

### 4.4 Price-direction information-time (Phase 5)

Price-direction features attached to row `t` must end at `t-1`, the **same boundary** as the already-lagged volatility surface. Use the as-of convention:

```python
price_return_20d_asof_t = adjusted_price.shift(1).pct_change(20)   # and 5d, 60d
```

This means the return measured at `t` uses prices through `t-1` only. **Do not** combine a lagged-vol-through-`t-1` reading with a same-day close at `t`; that would make the price feature "see" one day further than the volatility feature and is a look-ahead leak relative to the strategy's own decision timing. The surface uses `close` as its price column today; price-direction features use the same `close` series. If/when an explicit adjusted-close column is introduced, switch both to it together and document it.

### 4.5 Yield data is monthly (constrains Phase 5)

`gs10` / `gs2` live in `macro_data` and are sourced from **FRED at monthly cadence** (`src/api_fetch/fetch_macro_data.py` resamples every series with `resample("MS")`), then forward-filled. There is **no daily yield series** in the database. A "20-day change in the 10Y yield" computed on monthly-ffilled data is a staircase and a "+42 bps" precision is false precision. Phase 5 therefore uses **adjusted-price direction only**; daily-yield context is a clearly-labelled deferred enhancement (§Phase 5).

### 4.6 Known data quirks

* The persisted surface contains **warm-up `NaN`s** (rolling/EWMA/GARCH `min_history`, plus the one-day lag dropping the first row per ticker). These must survive to the JSON boundary as `null` (`api/serialization/frames.py:nan_to_none`), not break the response.
* A known all-`NaN` `etf_prices` row at **2026-06-09** propagates `NaN` into derived features for that date; confirm it serialises to `null`.
* GARCH alignment is already causal: monthly refit + daily roll-forward of `var_t = ω + α·ε²_{t-1} + β·var_{t-1}`, then the whole surface is lagged by 1. `garch_refit_frequency="daily"` reduces exactly to the point-in-time estimator (the validated correctness anchor). The Phase 0 GARCH item is a **verification/documentation exercise**, not an expected bug.

---

## 5. Canonical column names (authoritative)

The estimator columns use **one** naming scheme spanning the in-memory surface, the DB schema, the writer constant, the reader, the API service, and the React method map. **Use these names verbatim.** Do not invent new ones (e.g. `rolling_20d`, `ewma_094`, `garch_11` exist nowhere and would be drift-prone).

| Internal name | Display label | Defined in |
| ------------- | ------------- | ---------- |
| `rolling_20`  | Rolling 20D   | `feature_surface.py`, `db_population.py`, `_VOLATILITY_FEATURE_COLUMNS` (`db_writer.py`), `db_reader.get_volatility_features`, `_VOL_METHODS` (`api/services/volatility.py`), `VOL_METHODS` (`VolatilityPage.tsx`) |
| `rolling_60`  | Rolling 60D   | "" |
| `ewma_94`     | EWMA λ=0.94   | "" |
| `ewma_97`     | EWMA λ=0.97   | "" |
| `garch`       | GARCH(1,1)    | "" |

Comparison features already persisted (do not duplicate them): `ewma_94_to_rolling_20`, `ewma_94_change_5d`, `ewma_97_to_rolling_20`, `ewma_97_change_5d`.

Shared internal constant for the five raw estimators:

```python
VOL_ESTIMATOR_COLUMNS = {
    "rolling_20": "Rolling 20D",
    "rolling_60": "Rolling 60D",
    "ewma_94": "EWMA λ=0.94",
    "ewma_97": "EWMA λ=0.97",
    "garch": "GARCH(1,1)",
}
```

Display labels are never used as internal identifiers.

**Default reference estimator:** `rolling_20` (responsive, easy to explain). Later phases may make it selectable; never switch it silently. **Historical windows** (trading observations, not calendar days):

```python
HISTORICAL_WINDOWS = {"3Y": 756, "5Y": 1260, "10Y": 2520}   # "Full" = expanding
DEFAULT_HISTORICAL_WINDOW = "5Y"
MIN_PERCENTILE_HISTORY = 126   # configurable
```

---

## 6. Compute-vs-persist decision

The `volatility_features` table persists **only** the five raw estimates plus the four comparison features and `config_key`. It does **not** carry percentiles, term ratios, dispersion, states, vol-of-vol, or relative ratios.

**Decision: compute all Phase 1–8 derived features on demand** in `src/volatility/` pure functions called from `api/services/volatility.py`, starting from the already-persisted raw estimates. Do **not** add derived columns to the table.

Rationale:

* Percentile windows (3Y/5Y/10Y/Full) and thresholds are **user-selectable at view time**; persisting a single fixed choice fights that.
* `data/db_population.py` `DROP`s then `CREATE`s `volatility_features`, and the writer has no `CREATE IF NOT EXISTS` guard, so adding a column means a **full DB repopulate**, not an in-place migration. Avoid that.
* Keeps the scenario-independent table small and stable.

Persist a derived feature later **only** if on-demand compute over full history becomes a measured UI-latency problem — and then with the full cache key of §7 baked into the persisted row.

---

## 7. Cache policy

Derived features are computed on demand and cached in the existing in-process TTL cache (`api/cache.py`, `TTLCache.get/set/flush`). The cache key is a `Hashable` tuple. **The `(ticker, estimator, window)` triple is insufficient** — two requests that differ in config, thresholds, minimum history, or underlying-data version must never collide. Every input that changes the output is part of the key.

### 7.1 Percentile / level / direction / ratio / dispersion / vol-of-vol keys

```python
percentile_cache_key = (
    "vol_percentile",            # feature id
    "v1",                        # feature/version id (bump on algorithm change)
    config_key,                  # str(VolatilityFeatureConfig.cache_key())
    ticker,
    reference_estimator,         # e.g. "rolling_20"
    window_key,                  # "3Y" | "5Y" | "10Y" | "Full"
    min_periods,                 # MIN_PERCENTILE_HISTORY
    data_version,                # latest underlying-data version / as-of boundary
)
```

`data_version` is the surface's freshness token: derive it from the max `date` (and row count) of the queried `(config_key, ticker)` slice — the same shape the surface build cache already uses (`str(max date)`, `len`). A new persisted row must invalidate stale derived results; a TTL backstop covers anything not explicitly invalidated.

### 7.2 Classified-state keys (Phase 3)

Classified-state results additionally include the threshold/classifier configuration and confirmation policy:

```python
state_cache_key = percentile_cache_key[:-1] + (   # reuse the percentile inputs, minus data_version
    state_config_version,        # hash/version of VolatilityStateConfig
    confirmation_days,
    cooldown_days,               # where applicable (transition extraction, Phase 6)
    data_version,
)
```

`VolatilityStateConfig` (and all threshold configs) are `frozen` dataclasses; derive `state_config_version` from a stable hash of the dataclass fields so a threshold change forces a new key.

### 7.3 Estimator-agreement keys (Phase 4)

```python
agreement_cache_key = (
    "estimator_agreement", "v1", config_key, ticker,
    tuple(sorted(estimator_columns)),     # the set of estimators in the dispersion
    min_estimators,
    agreement_config_version,             # hash of EstimatorAgreementConfig
    data_version,
)
```

### 7.4 Cross-asset keys (Phase 7)

```python
cross_asset_cache_key = (
    "relative_vol", "v1", config_key,
    reference_estimator,
    ratio_pair_or_universe,               # ordered ("TLT","AGG") or sorted full universe
    window_key, min_periods,
    cross_asset_config_version,
    data_version,
)
```

### 7.5 Invalidation and isolation rules

* **Invalidation:** the cache is TTL-bounded and explicitly flushed (`TTLCache.flush`) on backtest completion / data refresh — the same hook the read/tearsheet endpoints already use. Because `data_version` is part of every key, a stale-data hit cannot survive a surface update even before the TTL expires.
* **Isolation (forbidden collisions):** results from different `config_key`, `window_key`, threshold/classifier config, reference estimator, or confirmation policy **must never share a cache entry**. If any of those inputs is absent from the key, the key is wrong.
* Keys must be plain hashable tuples of scalars/strings (dataclass *versions/hashes*, not the dataclass objects) so they are stable across processes and serialisable for logging.

---

## 8. One phase per pull request

Each PR ships exactly one phase. There is **no bundling** and no "first milestone" of multiple phases. Each PR is independently useful, leaves the application complete and usable, and includes its own backend tests, the relevant API schema changes, and the relevant frontend changes. A PR depends only on calcs/UI from **earlier** phases, never on anything from a later phase.

| PR | Phase | Deliverable |
| -- | ----- | ----------- |
| PR0 | Phase 0 | Audit, data contract, baseline tests |
| PR1 | Phase 1 | Historical percentiles + level classification |
| PR2 | Phase 2 | Direction + 20D/60D term ratio |
| PR3 | Phase 3 | Unified state classifier (instantaneous **and** confirmed state) |
| PR4 | Phase 4 | Estimator agreement (relative + absolute-floor) |
| PR5 | Phase 5 | Price + volatility context |
| PR6 | Phase 6 | Chart modes, state shading, transition markers, cooldown, display controls |
| PR7 | Phase 7 | Cross-asset relative volatility |
| PR8 | Phase 8 | Estimate stability (vol-of-vol percentile) |
| PR9 | Phase 9 | Historical outcomes (non-overlapping default, sample gates) |
| PR10 | Phase 10 | Passive strategy-integration snapshot interface + reproducibility metadata |

Within each phase: complete, test, and review in the running application before starting the next.

---

## 9. Phases

Every phase below specifies: goal/scope, backend function signatures (pure, in `src/volatility/`), Pydantic API response models where relevant, React rendering responsibilities (presentation only), tests, acceptance criteria, and non-goals. Every phase preserves the existing raw estimator chart and latest-values table, changes no strategy/portfolio behaviour, and degrades gracefully on missing history/estimators (NaN→null at the boundary).

---

### Phase 0 — Audit, data contract, and baseline tests

**Goal / scope.** Establish a documented, tested data contract for the volatility surface before any interpretation logic. No page redesign.

Inspect and document:

* How each series is calculated; whether annualisation is consistent (decimals internally; percent on display).
* Where the one-day lag is applied (answer: `_lag_feature_columns`, once) — and assert nothing re-shifts it downstream.
* Missing-value / warm-up handling, including the 2026-06-09 all-NaN row.
* That all estimators use the same return definition and the same price column (`close`).
* That GARCH fit/forecast dates are aligned to the same as-of date as rolling/EWMA (verification of the already-validated `daily`-refit equivalence anchor — not a bug hunt).
* That the surface has one row per `(date, ticker)` within a `config_key`.

**Required normalized contract** (already the persisted shape — confirm, don't rebuild):

```text
date, ticker, rolling_20, rolling_60, ewma_94, ewma_97, garch, config_key
```

Optional metadata to document (not persist): `source_price_column`, `annualization_factor`, `lag_days`.

**Backend function signatures** (`src/volatility/audit.py`):

```python
def validate_volatility_surface(
    surface_df: pd.DataFrame,
    estimator_columns: list[str],
) -> list[str]:
    """Return data-quality warnings (non-fatal) for the persisted surface."""

def normalize_volatility_surface(surface_df: pd.DataFrame) -> pd.DataFrame:
    """Return a stable date/ticker/estimator frame within one config_key."""
```

**API.** No new response model. Optionally surface `validate_volatility_surface` warnings on an existing/debug endpoint; they must never break the response.

**React.** No visual redesign. Confirm the existing chart and latest-values table still render, including `null` warm-up points.

**Tests.** Duplicate `(date, ticker)`; negative volatility; missing estimator columns; warm-up NaN; annualisation consistency (decimals internal); **one-day lag equivalence** (truncating rows after `t` leaves every value on/before `t` unchanged — `lookahead`-marked); GARCH `daily`-refit equivalence to the point estimator; the 2026-06-09 NaN row serialises to `null`.

**Acceptance.** (1) Contract documented. (2) Point-in-time alignment verified, lag located and asserted single. (3) Existing values and latest-value rendering still work. (4) Validation warnings available without breaking the page. (5) Baseline tests cover existing calculations and the NaN boundary. (6) No visual redesign.

**Non-goals.** No percentiles, direction, states, or any interpretation logic.

---

### Phase 1 — Historical volatility percentiles

**Goal / scope.** Make raw volatility interpretable relative to each asset's **own** history. Highest-priority interpretability win.

For each `(ticker, estimator)` compute the point-in-time historical percentile over a selectable window (3Y/5Y/10Y/Full), using only observations available up to and including `t`. Default window `5Y`; configurable `min_periods` (default `MIN_PERCENTILE_HISTORY = 126`).

#### Canonical percentile algorithm (single, exact method)

For each row `t`, the percentile is the **average-rank percentile of the current (already-lagged) observation within its trailing window, inclusive**:

```python
# window = the trailing slice ending at t (length `window` for 3Y/5Y/10Y; expanding for "Full")
percentile_t = window.rank(method="average", pct=True).iloc[-1]   # internal 0.0–1.0
```

Locked semantics:

* **Inclusion:** the current observation is **included** in its own reference set. Because the surface is already lagged (§4.1) this is as-of `t`, not future.
* **Ties:** `method="average"` (ties share the mean of their ranks). Deterministic. The method matters only when the current value is *tied* with others in the window; with `"average"`, a value tied with all of a length-`k` window scores `(k+1)/(2k)` (→ ~0.5 as `k` grows), **not** `1.0`. This is deliberate: `"average"` is the symmetric/midpoint convention (scipy `percentileofscore(kind="mean")`), so a flat series reads as mid-distribution rather than spuriously `Extreme`. (`method="max"`, the "fraction ≤ current" convention, would return `1.0` for a constant window — rejected for exactly that reason.)
* **Constant window:** every value tied → the canonical percentile is `(k+1)/(2k)` for a window of `k` non-NaN values (e.g. `0.625` at `k=4`, → ~0.5 for long windows). This exact value is locked by a test. It is **not** `1.0`.
* **Missing values:** `NaN`s are excluded from the rank (pandas `rank` skips `NaN`); a `NaN` current value yields `NaN` percentile (→ `null`).
* **First valid percentile:** only after at least `min_periods` non-NaN observations exist in the window; before that, `NaN`/`Insufficient history`.
* **Internal vs displayed:** internal `0.0–1.0`; the API/UI display an **ordinal 0–100** ("24th"). The conversion is display-only.
* Use the vectorised `rolling(window).rank(pct=True)` / `expanding().rank(pct=True)` path; do **not** use a slow per-row Python `apply` callback. Mirror the rolling-baseline idiom already in `src/signals_macro/macro_signal_engine.py` (`rolling(...).median()` style), not a bespoke loop.

#### Level classification (configurable thresholds)

```python
VOL_LEVEL_THRESHOLDS = {"low": 0.20, "normal": 0.60, "elevated": 0.80, "high": 0.95}
# 0.00–0.20 Low | 0.20–0.60 Normal | 0.60–0.80 Elevated | 0.80–0.95 High | 0.95–1.00 Extreme
```

Boundary rule (deterministic): a percentile exactly on a threshold falls into the **upper** band (`>= low` is Normal, etc.). The `Extreme` band is the top ~6 of ~126 observations and will flicker day-to-day; Phase 3's confirmed state (not Phase 1's instantaneous level) is what the headline card should rely on once Phase 3 ships.

**Backend signatures** (`src/volatility/percentiles.py`):

```python
def compute_rolling_percentile(
    series: pd.Series,
    window: int | None,        # None => expanding ("Full")
    min_periods: int,
) -> pd.Series:
    """Point-in-time historical percentile (0.0–1.0), inclusive of the current
    already-lagged observation, average tie-handling, vectorised, no look-ahead."""

def classify_volatility_level(
    percentile: float | None,
    thresholds: dict[str, float],
) -> str:
    """Map a 0.0–1.0 percentile to Low/Normal/Elevated/High/Extreme (upper-edge rule)."""
```

Computation is scoped to `(config_key, ticker, estimator, window)` and cached from this first implementation using §7.1 keys.

**Pydantic API models** (`api/schemas/volatility.py`, additive):

```python
class VolatilityContextResponse(BaseModel):
    ticker: str
    config_key: str
    reference_estimator: str
    historical_window: str            # "5Y"
    as_of_date: str | None            # snapshot date t
    information_through_date: str | None  # t-1
    current_volatility: float | None  # decimal
    historical_percentile: float | None   # 0.0–1.0
    percentile_ordinal: int | None    # 0–100 for display
    volatility_level: str             # "Normal"
    insufficient_history: bool

class VolatilityPercentileSeriesResponse(BaseModel):
    ticker: str
    config_key: str
    reference_estimator: str
    historical_window: str
    unit: str = "percentile"          # 0.0–1.0
    series: list[NamedSeries]         # percentile line(s)
    reference_lines: list[float]      # [0.20, 0.60, 0.80, 0.95]
```

**React.** Add a `Latest Volatility Context` card above the chart (current %, "Nth" percentile, level, as-of). Add a **view selector** (`Annualised volatility` | `Historical percentile`). The percentile view uses a `0–100%` y-axis (`yTickFormat=".0%"` on 0–1 data) with the existing `PlotlyLineChart` `referenceLines` at 0.20/0.60/0.80/0.95. The raw annualised view is unchanged. Show `Insufficient history` when flagged.

**Tests.** No future observation affects a past percentile (`lookahead`, truncation test); first valid percentile only after `min_periods`; **constant-series locked value** (`1.0`/100th, average ties); missing values don't corrupt later percentiles; tickers ranked independently; threshold boundary determinism; a performance benchmark over ~2520-row history confirming the vectorised path is used.

**Acceptance.** (1) Current vol shown with its percentile. (2) Readable level shown. (3) Raw↔percentile view toggle. (4) Window configurable. (5) Insufficient history handled clearly. (6) Estimator toggles still work. (7) Percentile calcs have point-in-time tests and are cached.

**Non-goals.** No direction, ratios, disagreement, cross-asset, price context, or strategy actions.

---

### Phase 2 — Volatility direction and short/long ratio

**Goal / scope.** Separate **level** from **direction**, and add the 20D/60D term ratio. Distinguish "low and stable" / "low but rising" / "high and rising" / "high but falling".

For the reference estimator (`rolling_20`) compute (point-in-time, on already-lagged columns): 5-day and 20-day **relative** change, and the term ratio `rolling_20 / rolling_60`.

```python
relative_change_20d = current_vol / vol_20d_ago - 1     # 5d analogous
vol_term_ratio = rolling_20 / rolling_60
```

Direction thresholds and ratio bands (configurable defaults):

```python
VOL_DIRECTION_THRESHOLDS = {"rising": 0.10, "falling": -0.10}   # else Stable
VOL_RATIO_BANDS = {"expansion": 1.15, "contraction": 0.85}      # else Balanced
```

Methodology note (must appear in the UI methodology section): `rolling_20` and `rolling_60` are computed from **overlapping** return windows, so the 20D/60D ratio is **mechanically mean-reverting toward 1** and the two series are strongly correlated by construction. The 0.85/1.15 bands are **descriptive, not statistically derived**. Present the ratio as "is short-term vol pulling away from its own baseline", not as a ratio of independent quantities.

**Backend signatures** (`src/volatility/direction.py`):

```python
def compute_volatility_direction_features(
    vol_series: pd.Series,
    short_change_days: int = 5,
    long_change_days: int = 20,
) -> pd.DataFrame:
    """Point-in-time relative changes (no look-ahead)."""

def compute_volatility_term_ratio(short_vol: pd.Series, long_vol: pd.Series) -> pd.Series:
    """rolling_20 / rolling_60, division-by-zero safe -> NaN."""

def classify_volatility_direction(
    relative_change: float | None, rising_threshold: float, falling_threshold: float,
) -> str: ...   # "Rising" | "Falling" | "Stable" | "Unknown"

def classify_volatility_term_state(
    ratio: float | None, expansion_threshold: float, contraction_threshold: float,
) -> str: ...   # "Expansion" | "Balanced" | "Contraction" | "Unknown"
```

**Pydantic API.** Extend `VolatilityContextResponse` with `direction: str`, `change_5d: float | None`, `change_20d: float | None`, `term_ratio: float | None`, `term_state: str`. Add a ratio/change series response (reuse `NamedSeries`) with `reference_lines = [0.85, 1.00, 1.15]` for the ratio view.

**React.** Extend the context card (direction, 20D change, 20D/60D ratio, term state). Add view modes `20D / 60D ratio` and `Change in volatility`; ratio chart draws reference lines at 0.85/1.00/1.15.

**Tests.** Correct change/ratio maths; division-by-zero → safe `NaN`; missing `rolling_60` → safe Unknown term state; threshold boundary determinism; all point-in-time; no cross-asset leakage.

**Acceptance.** (1) Direction shown. (2) 20D/60D ratio shown. (3) Change/ratio charts available. (4) Thresholds configurable. (5) Raw & percentile views intact. (6) Direction/ratio tested.

**Non-goals.** No combined state yet; no agreement or price context.

---

### Phase 3 — Unified volatility-state classifier (instantaneous **and** confirmed)

**Goal / scope.** Collapse level + direction + ratio into one concise, deterministic, explainable **diagnostic state**, and compute **both** an instantaneous state and a **confirmed** state (persistence-debounced). The headline card and the all-asset table use the **confirmed** state; tooltips/methodology may show both.

#### State precedence (complete, deterministic, ordered)

First define two scores from Phase 2 inputs:

```python
# direction in {"Rising","Falling","Stable","Unknown"}; term_state in {"Expansion","Balanced","Contraction","Unknown"}
expansion_score   = (direction == "Rising")  * 1 + (term_state == "Expansion")   * 1   # 0,1,2
contraction_score = (direction == "Falling") * 1 + (term_state == "Contraction") * 1   # 0,1,2
# "strong" = score == 2 (both agree); "mixed/neutral" = otherwise
```

Apply rules **in order**; the first match wins:

1. Any required input (`percentile`, `direction`, or `term_ratio`) unavailable → **Unknown**.
2. Confirmed-`Extreme` level (percentile in the `Extreme` band) → **Shock**. (A *single-day* Extreme does not reach the confirmed card — see confirmation below; it can still appear on the instantaneous state and on Phase 6 markers.)
3. Level ∈ {Elevated, High} **and** `expansion_score == 2` (strong expansion) → **Stress Expansion**.
4. Level ∈ {Elevated, High} **and** `contraction_score == 2` (strong contraction) → **Normalisation**.
5. Level ∈ {Elevated, High} **and** neither strong (mixed/neutral) → **Persistent Stress**.
6. Level ∈ {Low, Normal} **and** `expansion_score >= 1` → **Early Expansion**.
7. Level ∈ {Low, Normal} **and** otherwise → **Calm**.

Edge cases this resolves explicitly (all covered by tests):

* **Direction Rising but ratio Contraction** at Elevated/High: `expansion_score == 1`, `contraction_score == 1` → neither strong → rule 5 → **Persistent Stress**.
* **Direction Falling but ratio Expansion** at Elevated/High: symmetric → **Persistent Stress**.
* **One input unavailable** → rule 1 → **Unknown**.
* **Percentile exactly on a threshold** → upper-band rule from Phase 1, fed in deterministically.
* **Extreme for only one day** → fails confirmation; confirmed state stays at its prior confirmed value; instantaneous state shows `Shock`.
* **Elevated falling to Normal while direction still Rising** → level now Normal, `expansion_score >= 1` → **Early Expansion** (rule 6).

#### Instantaneous vs confirmed state

```python
instantaneous_state(t) = classify_volatility_state(...)            # from rules above
confirmed_state(t)      = the most recent instantaneous_state that has persisted unchanged
                          for at least `confirmation_days` consecutive trading days (default 3)
```

Until a new instantaneous state has persisted `confirmation_days`, `confirmed_state` holds the previous confirmed value (seeded to `Unknown`). This removes the `Extreme`/single-day-crossing flicker from the headline card. The same confirmed series feeds Phase 6's shading.

**Backend signatures** (`src/volatility/states.py`):

```python
@dataclass(frozen=True)
class VolatilityStateConfig:
    low_percentile: float = 0.20
    normal_percentile: float = 0.60
    elevated_percentile: float = 0.80
    high_percentile: float = 0.95
    expansion_ratio: float = 1.15
    contraction_ratio: float = 0.85
    rising_change: float = 0.10
    falling_change: float = -0.10
    confirmation_days: int = 3
    def version(self) -> str: ...   # stable hash for cache keys (§7.2)

def classify_volatility_state(
    percentile: float | None, direction: str, term_ratio: float | None,
    config: VolatilityStateConfig,
) -> str:
    """Instantaneous diagnostic state via the ordered precedence rules."""

def compute_confirmed_state_series(
    instantaneous_state: pd.Series, confirmation_days: int = 3,
) -> pd.Series:
    """Persistence-debounced confirmed state."""

def build_latest_volatility_state_table(
    features_df: pd.DataFrame, as_of_date: pd.Timestamp, config: VolatilityStateConfig,
) -> pd.DataFrame:
    """Per-asset confirmed state + supporting features at as_of_date."""

def explain_volatility_state(row: pd.Series) -> str:
    """Deterministic, template-based explanation from visible inputs (no external model)."""
```

**Pydantic API.** Extend `VolatilityContextResponse` with `instantaneous_state: str`, `confirmed_state: str`, `state_explanation: str`, `state_config_version: str`. Add:

```python
class VolatilityStateRow(BaseModel):
    ticker: str
    confirmed_state: str
    percentile_ordinal: int | None
    current_volatility: float | None
    change_20d: float | None
    term_ratio: float | None
    term_state: str

class VolatilityStateTableResponse(BaseModel):
    as_of_date: str | None
    config_key: str
    reference_estimator: str
    state_config_version: str
    rows: list[VolatilityStateRow]
```

**React.** Prominent **state card** showing `confirmed_state` plus its inputs and a deterministic one-line explanation; tooltip may show the instantaneous state. Compact all-asset **confirmed-state table** (`VolatilityStateTableResponse`) that supplements — never replaces — the raw latest-estimator table.

**Tests.** Synthetic cases for **every** state (Calm, Early Expansion, Stress Expansion, Persistent Stress, Normalisation, Shock, Unknown); every precedence branch and listed edge case; boundary percentiles; conflicting direction/ratio; single-day Extreme not reaching confirmed card; confirmation persistence (state flips only after `confirmation_days`); explanation determinism.

**Acceptance.** (1) Each asset gets one deterministic confirmed state. (2) Selected asset has a prominent confirmed-state card. (3) All assets in a confirmed-state table. (4) Explanations derive from visible inputs. (5) No allocation recommendation. (6) State logic lives in `src/volatility/`, isolated from API/React. (7) Full synthetic-case + confirmation tests.

**Non-goals.** No trading/weights. No price direction yet. Transition extraction/shading/cooldown/markers are **Phase 6** (basic confirmation is here, not deferred).

---

### Phase 4 — Estimator agreement and disagreement

**Goal / scope.** Make estimator differences measurable rather than eyeballed. Classify agreement using **both** a relative-dispersion threshold **and** an absolute-spread floor (the floor is part of the real interface, not a footnote) — necessary because SHY's ~1–2% vol makes relative dispersion misleading.

For each `(ticker, date)` over valid estimates (require `min_estimators`, default 3):

```python
absolute_spread     = max(valid) - min(valid)                 # internal decimals (annualised-vol)
relative_dispersion = (max(valid) - min(valid)) / median(valid)
```

Classification:

```python
@dataclass(frozen=True)
class EstimatorAgreementConfig:
    high_relative_threshold: float = 0.10     # < => High agreement
    low_relative_threshold: float = 0.25      # relative gate for Low
    low_agreement_absolute_floor: float = 0.0025
    # 0.0025 = 0.25 annualised-vol percentage points, expressed in internal decimals.
    min_estimators: int = 3
    def version(self) -> str: ...
```

* **High agreement:** `relative_dispersion < high_relative_threshold`.
* **Low agreement:** **only if BOTH** `relative_dispersion > low_relative_threshold` **AND** `absolute_spread > low_agreement_absolute_floor`. (A trivial 0.0012 spread on a 1.2% SHY median is **not** Low agreement even though it is 25%+ relative.)
* **Moderate agreement:** otherwise.

Additional diagnostics: highest/lowest estimator by name; fast-estimator premium `rolling_20 / median(rolling_60, ewma_97, garch)`.

**Backend signatures** (`src/volatility/agreement.py`):

```python
def compute_estimator_dispersion(
    df: pd.DataFrame, estimator_columns: list[str], min_estimators: int,
) -> pd.DataFrame:
    """Point-in-time absolute_spread, relative_dispersion, median, highest/lowest, fast_premium."""

def classify_estimator_agreement(
    relative_dispersion: float | None,
    absolute_spread: float | None,
    config: EstimatorAgreementConfig,
) -> str:
    """High / Moderate / Low / Unknown. Low requires BOTH relative and absolute breach."""
```

**Pydantic API.** Extend the context response with `estimator_agreement: str`, `absolute_spread: float | None`, `relative_dispersion: float | None`, `agreement_config_version: str`. Add an estimator-comparison panel model:

```python
class EstimatorComparisonRow(BaseModel):
    estimator: str            # display label
    method: str               # internal key
    current_volatility: float | None
    historical_percentile_ordinal: int | None
    absolute_diff_vs_median: float | None    # decimals; label "Absolute spread vs median (pp)"
    relative_diff_vs_median: float | None    # ratio;    label "Relative diff vs median (%)"

class EstimatorAgreementResponse(BaseModel):
    ticker: str
    config_key: str
    agreement: str
    absolute_spread: float | None
    relative_dispersion: float | None
    highest_estimator: str | None
    lowest_estimator: str | None
    agreement_config_version: str
    rows: list[EstimatorComparisonRow]
```

The ambiguous "Difference vs Median" label is replaced by two explicit columns. The card displays **both** "Absolute spread: 0.12 percentage points" and "Relative dispersion: 4.2%".

**React.** Extend the state card with agreement, both spread readings, highest/lowest. Add an `Estimator dispersion` chart view and the comparison panel (per-estimator current vol, percentile, absolute pp diff, relative % diff). Toggling estimators on/off must not break the panel.

**Tests.** Dispersion maths; median handling; missing estimators; **zero/near-zero median** (SHY-like: absolute floor prevents false Low); minimum-estimator gate; highest/lowest identification; threshold boundaries including the both-gates rule; no row multiplication during enrichment.

**Acceptance.** (1) Both absolute spread and relative dispersion computed and displayed. (2) Agreement classified with the absolute floor enforced. (3) Highest/lowest visible. (4) Dispersion chartable. (5) Missing estimators safe. (6) State classification unchanged. (7) Agreement unit-tested incl. the floor.

**Non-goals.** No auto-selection of a "best" estimator; no sizing change.

---

### Phase 5 — Price and volatility direction context

**Goal / scope.** Distinguish favourable from adverse volatility using **adjusted-price direction + volatility direction + volatility state**. Yield enrichment is **out of active scope** (§4.5) and deferred.

Price-direction features, as-of `t-1` (§4.4):

```python
price_return_5d  = adjusted_price.shift(1).pct_change(5)
price_return_20d = adjusted_price.shift(1).pct_change(20)
price_return_60d = adjusted_price.shift(1).pct_change(60)
PRICE_DIRECTION_THRESHOLD = 0.01   # configurable; tiny moves => Flat
```

Interpretation matrix (the four required rows plus Flat/Unknown):

| Price direction | Vol direction | Interpretation |
| --------------- | ------------- | -------------- |
| Falling | Rising | **Adverse Shock** |
| Rising | Rising | **Positive Volatility Expansion** |
| Rising | Falling | **Stable Positive Trend** |
| Falling | Falling | **Controlled Decline** |
| Flat | Stable | Quiet / Range-Bound |
| Insufficient data | Any | Unknown |

**Deferred enhancement (explicitly not in this PR):** daily yield context. The `gs10`/`gs2` series are monthly-ffilled FRED data, so a "20-day yield change" and any "+42 bps" precision are misleading on a staircase. Add daily-yield context only **after** a properly aligned, validated, lagged daily `DGS10`/`DGS2` source with its own point-in-time contract exists. No yield field, no yield UI example, no yield helper, no yield tests, and no acceptance criterion requiring yield direction ship in Phase 5.

**Backend signatures** (`src/volatility/price_context.py`):

```python
def compute_price_direction_features(
    prices: pd.Series, horizons: tuple[int, ...] = (5, 20, 60),
) -> pd.DataFrame:
    """As-of t-1 price returns (prices.shift(1).pct_change(h)); no look-ahead."""

def classify_price_volatility_context(
    asset_return: float | None, vol_change: float | None,
    price_threshold: float, vol_threshold: float,
) -> str:
    """Joint price/vol context label from the matrix above."""
```

(No `explain_bond_price_volatility_context` / yield helper — removed.)

**Pydantic API.** Extend the context response with `price_volatility_context: str`, `asset_return_20d: float | None`, `vol_change_20d: float | None`. Add `price_volatility_context` and `asset_return_20d` to the cross-asset state table rows.

**React.** Extend the state card with the price/volatility context label, 20D asset return, and 20D vol change. Add the context column to the all-asset table. No yield row.

**Tests.** Price returns lagged correctly (as-of `t-1`); **no-look-ahead** (changing the price *on* `t` does not alter the snapshot dated `t`); flat/positive/negative classifications; the four rising/falling combinations; price-column documented. (No yield tests.)

**Acceptance.** (1) Dashboard distinguishes positive vs adverse volatility expansion. (2) Price/vol context in the selected-asset card. (3) Context in the all-asset table. (4) Missing price history → Unknown, no crash. (5) No trading action triggered. (6) Joint-state logic deterministically tested. (No yield-direction criterion.)

**Non-goals.** No daily-yield interpretation; no trade actions.

---

### Phase 6 — Signal-oriented chart modes and transition markers

**Goal / scope.** Make state transitions visually obvious. This phase adds **transition extraction, state shading, markers, cooldown, and display controls** on top of the **already-confirmed** Phase 3 state. It does **not** introduce basic confirmation (that is Phase 3).

Chart views: `Annualised volatility`, `Historical percentile`, `20D / 60D ratio`, `Volatility change`, `Estimator dispersion`. Optional **state shading** driven by the Phase 3 **confirmed** state series (Calm / Early Expansion / Stress Expansion / Persistent Stress / Normalisation / Shock). Subtle, user-disableable.

**Transition markers** (from the confirmed series, debounced + cooldown):

* Entered Elevated / High / Extreme volatility
* 20D crossed above / below 60D
* Estimator agreement changed to Low
* Volatility entered Normalisation

Do not mark every daily crossing. A transition is emitted only when the new confirmed condition persists `confirmation_days` (≥3) and at least `cooldown_days` have elapsed since the last marker of the same type.

**Backend signatures** (`src/volatility/transitions.py`). **No server-built figure.** The Phase 6 helper returns typed series + metadata; React assembles the Plotly traces.

```python
def detect_persistent_state_transitions(
    confirmed_state_series: pd.Series,
    confirmation_days: int = 3,
    cooldown_days: int = 10,
) -> pd.DataFrame:
    """Confirmed, debounced, cooldown-gated transitions (date, kind, from_state, to_state)."""

def build_state_ranges(confirmed_state_series: pd.Series) -> pd.DataFrame:
    """Contiguous (start, end, state) ranges for shading."""
```

**Pydantic API** — typed chart data, **not** a `go.Figure`:

```python
class VolatilityPoint(BaseModel):
    date: str
    value: float | None

class VolatilitySeries(BaseModel):
    name: str                 # display label
    method: str | None        # internal estimator key, where relevant
    unit: str                 # "decimal" | "percentile" | "ratio" | "decimal_change"
    points: list[VolatilityPoint]

class VolatilityStateRange(BaseModel):
    start: str
    end: str
    state: str                # confirmed state for shading

class VolatilityTransition(BaseModel):
    date: str
    kind: str                 # "entered_high", "ratio_cross_up", "agreement_low", ...
    from_state: str | None
    to_state: str | None
    label: str

class VolatilityChartResponse(BaseModel):
    ticker: str
    config_key: str
    view_mode: str            # "volatility" | "percentile" | "ratio" | "change" | "dispersion"
    unit: str                 # axis unit for view_mode
    as_of_date: str | None
    series: list[VolatilitySeries]
    state_ranges: list[VolatilityStateRange]
    transitions: list[VolatilityTransition]
    reference_lines: list[float]
```

`build_volatility_feature_chart(...) -> go.Figure` is **removed entirely**; no Plotly figure is constructed on the backend.

**React.** Convert `VolatilityChartResponse` into Plotly traces via the existing shared lazy `PlotlyLineChart` (`series` → traces; `state_ranges` → `bands`; `reference_lines` → `referenceLines`; `transitions` → marker annotations). Controls: chart view, historical window, show state shading, show transition markers, show estimator curves. Estimator toggles apply only to volatility/percentile views (not the single ratio or the derived dispersion aggregate). Axis unit/format switches with `view_mode`.

**Tests (split).** *Backend:* transition confirmation + cooldown debounce; contiguous, non-overlapping state ranges; correct `unit` per view; filtering by ticker and `config_key`; NaN→null; transition metadata fields. *Frontend:* trace construction from the typed response; y-axis formatting per unit; estimator-toggle visibility rules; shading from `state_ranges`; markers from `transitions`; `null` rendered as a gap.

**Acceptance.** (1) Switch among all implemented views. (2) Confirmed-state shading toggleable. (3) Important transitions shown as markers. (4) Markers persistent + cooldown-debounced, not noisy. (5) Axes/units change correctly by view. (6) Readable across full history and short ranges. (7) Existing estimator comparison still available. (8) No `go.Figure` built server-side.

**Non-goals.** No forward-return outcomes yet.

---

### Phase 7 — Cross-asset relative volatility

**Goal / scope.** Show whether one asset is becoming unusually risky relative to the others (the strategy chooses among TLT/AGG/SHY). Monitor only — no allocation change.

Using a consistent reference estimator (`rolling_20`), compute point-in-time ratios and their historical percentiles (§Phase 1 algorithm, per-pair):

```python
tlt_to_agg = tlt_vol / agg_vol
tlt_to_shy = tlt_vol / shy_vol
agg_to_shy = agg_vol / shy_vol
```

Methodology note (required): the TLT/SHY ratio (~7×) trends with the duration differential, so its "5Y percentile" is a single-path, trend-laden statistic. Present "Elevated (74th)" as a **monitor**, never a tradable risk signal — consistent with the no-allocation-change non-goal. Same overlap/trend caveat as the Phase 2 ratio.

**Backend signatures** (`src/volatility/relative.py`):

```python
def compute_relative_volatility_ratios(
    wide_vol_df: pd.DataFrame, ratio_pairs: list[tuple[str, str]],
) -> pd.DataFrame:
    """Point-in-time cross-asset ratios; division-by-zero safe."""

def build_cross_asset_risk_table(
    features_df: pd.DataFrame, ratio_features_df: pd.DataFrame, as_of_date: pd.Timestamp,
) -> pd.DataFrame:
    """Current relative-risk diagnostics + all-asset risk ranking."""
```

Ratio percentiles use §7.4 cross-asset cache keys (ordered pair, reference estimator, window, min history, config version, data version).

**Pydantic API.**

```python
class CrossAssetRatioRow(BaseModel):
    pair: str                 # "TLT / AGG"
    current_ratio: float | None
    percentile_ordinal: int | None
    relative_risk_state: str  # "Normal" | "Elevated" | ...

class AssetRiskRankRow(BaseModel):
    rank: int
    ticker: str
    current_volatility: float | None
    percentile_ordinal: int | None
    confirmed_state: str

class CrossAssetVolatilityResponse(BaseModel):
    as_of_date: str | None
    config_key: str
    reference_estimator: str
    ratios: list[CrossAssetRatioRow]
    ranking: list[AssetRiskRankRow]
```

**React.** A `Cross-Asset Risk` section: ratio table (current, percentile, state), a ratio chart selector (TLT/AGG, TLT/SHY, AGG/SHY) with Raw-ratio / Historical-percentile views, and an all-asset risk ranking. Raw rank alone must never read as "unusual risk" — percentile and confirmed state stay visible.

**Tests.** Ratio maths; missing asset values; division-by-zero; independent per-pair percentiles; no forward info in ratio percentiles; consistent reference estimator; display ordering.

**Acceptance.** (1) Relative ratios available. (2) Ratios have historical context. (3) Risk ranking visible. (4) Reference estimator explicit. (5) Missing asset data safe. (6) Ratios + percentiles tested.

**Non-goals.** No allocation change from the ratios.

---

### Phase 8 — Volatility of volatility and estimate stability

**Goal / scope.** Measure whether the volatility **estimates themselves** are stable. **Emphasise the stability percentile, not the raw vol-of-vol units.**

For the reference volatility series (already annualised):

```python
vol_change      = vol_series.diff()         # annualised-vol pp per day (dimensionally muddy)
vol_of_vol_20d  = vol_change.rolling(20).std()
stability_percentile = compute_rolling_percentile(vol_of_vol_20d, window, min_periods)  # §Phase 1
```

The raw `vol_of_vol_20d` mixes daily-frequency variation of an annualised quantity, so the **percentile is the only cleanly interpretable output**. The primary UI shows the **5Y stability percentile + Status**. The raw value may appear in the API but must be precisely labelled **"20D standard deviation of daily changes in annualised volatility"** and placed in methodology/debug/expandable details only — never as a headline "1.4 percentage points".

Stability classification (percentile bands):

```text
< 0.60  Stable | 0.60–0.80 Changing | 0.80–0.95 Unstable | > 0.95 Extreme instability
```

**Backend signatures** (`src/volatility/stability.py`):

```python
def compute_volatility_of_volatility(vol_series: pd.Series, window: int = 20) -> pd.Series:
    """Rolling std of daily changes in the (annualised) vol estimate."""

def classify_estimate_stability(stability_percentile: float | None) -> str:
    """Stable / Changing / Unstable / Extreme instability / Unknown."""
```

**Pydantic API.**

```python
class EstimateStabilityResponse(BaseModel):
    ticker: str
    config_key: str
    stability_percentile: float | None     # 0.0–1.0 (primary)
    percentile_ordinal: int | None
    estimate_stability: str                # Status (primary)
    stability_window: str
    # Debug/methodology only, precisely labelled:
    raw_vol_of_vol: float | None           # "20D std of daily changes in annualised volatility"
```

**React.** A `Risk Estimate Stability` card headlining **percentile + Status**; the raw value only in an expandable "details/methodology" section with its full label. Add a `Volatility of volatility` chart view. Add `estimate_stability` + `stability_percentile` to the all-asset table. A concise deterministic note explains that high vol-of-vol means current-vol-based sizing would be less stable — without prescribing a trade.

**Tests.** Rolling calc; warm-up; constant series; missing observations; **stability percentile no-look-ahead**; stability threshold boundaries.

**Acceptance.** (1) Vol-of-vol computed. (2) Stability **percentile** + Status are the headline. (3) Per-asset stability displayed. (4) Chart view available. (5) Meaning explained without prescribing a trade. (6) Raw value only in labelled details. (7) Tested.

**Non-goals.** No weight adjustment.

---

### Phase 9 — Historical signal outcome analysis

**Goal / scope.** Test, rather than assume, whether diagnostic states carried information — with **non-overlapping sampling by default** and **hard minimum-sample gates**. Only this phase can move a diagnostic state toward "validated signal", and only with explicit sample caveats.

Forward outcomes over horizons `{1M: 21, 3M: 63, 6M: 126}` (optional later `12M: 252`): mean, median, hit rate, std, worst, best, forward-window max drawdown, and the **effective independent observation count**.

States to analyse (at minimum): Calm, Early Expansion, Stress Expansion, Persistent Stress, Normalisation, Shock. Combined conditions (added incrementally, not all in one PR): vol rising + price falling; vol rising + price rising; vol falling after High/Extreme; ratio above expansion threshold; agreement Low; relative TLT/AGG vol above 90th percentile.

#### Alignment (strict, look-ahead-safe)

* `state(t)` comes from the **already-lagged surface** (so it is as-of `t`, info through `t-1`).
* `forward_return(t → t+h)` comes from **unlagged** adjusted prices **strictly after `t`**.
* Never mix the two date conventions. Pin this in a dedicated `lookahead`-marked test (truncating data after `t` must not change `state(t)`; forward returns must read only prices after `t`).

#### Sampling and minimum-sample policy (mandatory, deterministic)

**Default sampling is Non-overlapping.** Non-overlapping selection:

```text
1. Sort the eligible signal dates for the state ascending.
2. Pick the first eligible date; record it.
3. Exclude every later candidate whose forward window (length h) overlaps the recorded one.
4. Repeat from the next non-excluded candidate until none remain.
```

Minimum-sample gates (on the **effective independent** count N; cutoffs configurable but deterministic):

| N | Behaviour | Label |
| - | --------- | ----- |
| `< 5` | No aggregate stats | **Insufficient sample** |
| `5–9` | count / median / min / max only | **Anecdotal** |
| `10–19` | descriptive stats | **Low sample** |
| `>= 20` | full summary | (none) |

Rare states (`Shock`, `Extreme`-derived) are explicitly labelled **Anecdotal** at small N. The UI prominently shows the effective independent observation count. "All observations" remains available as an explicit, clearly-labelled override — but it is never the default and is annotated that overlapping daily windows overstate independent evidence.

**Backend signatures** (`src/volatility/outcomes.py`):

```python
def compute_forward_asset_returns(prices: pd.Series, horizons: dict[str, int]) -> pd.DataFrame:
    """Forward returns from UNLAGGED prices strictly after each date; signal features untouched."""

def compute_forward_window_drawdowns(prices: pd.Series, horizons: dict[str, int]) -> pd.DataFrame:
    """Worst drawdown inside each forward window."""

def select_non_overlapping_dates(signal_dates: pd.Series, horizon_days: int) -> pd.Series:
    """Deterministic non-overlapping selection (algorithm above)."""

def build_volatility_signal_outcome_table(
    features_df: pd.DataFrame, forward_returns_df: pd.DataFrame,
    signal_col: str, horizon_col: str, non_overlapping: bool = True,
    min_sample_gates: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Aggregate outcomes by state with sample-quality gating + labels."""
```

**Pydantic API.**

```python
class SignalOutcomeRow(BaseModel):
    state: str
    horizon: str
    effective_observations: int      # independent count (non-overlapping by default)
    sample_quality: str              # "Insufficient sample" | "Anecdotal" | "Low sample" | ""
    mean_return: float | None        # None when gated out
    median_return: float | None
    hit_rate: float | None
    worst_return: float | None
    best_return: float | None
    forward_max_drawdown: float | None

class SignalOutcomeResponse(BaseModel):
    ticker: str
    config_key: str
    sampling: str                    # "non_overlapping" (default) | "all"
    rows: list[SignalOutcomeRow]
    disclaimer: str                  # describes-the-sample-only caveat
```

**React.** A `Historical Signal Outcomes` section. Controls: asset, state/signal, horizon, date range, **sampling (default Non-overlapping; "All observations" is an explicit override)**. The effective independent count is prominent; gated rows show the sample-quality label and **no** full stats. Optional forward-return boxplot by state. A standing disclaimer: outcomes describe what followed similar states in the sample; they do not establish causality or guarantee future performance.

**Tests.** Forward-return alignment; **no look-ahead in signal construction** (`lookahead`); terminal missing values; effective observation counts; non-overlapping selection correctness; hit-rate; forward-window drawdown; state grouping; empty / low-sample states gated correctly; no many-to-many joins.

**Acceptance.** (1) Forward outcomes available by state. (2) Effective counts + sample limitations visible. (3) Mean and median both shown (when not gated). (4) Hit rate + downside included. (5) **Non-overlapping is the default**; overlapping is an explicit, labelled override. (6) Hard min-sample gates enforced (no full stats for inadequate samples). (7) Sample-quality labels visible. (8) Signal/outcome dates correctly separated, look-ahead tests present. (9) No strategy logic changed.

---

### Phase 10 — Passive strategy-integration snapshot interface

**Goal / scope.** Expose volatility features to strategy/risk layers through one stable, typed, point-in-time snapshot **with full reproducibility metadata** — without changing allocation logic. The surface is already attached to `BacktestContext` (`volatility_feature_surface`) and explicitly **passive / unused for sizing**; keep it that way.

**Single as-of access path.** Build the snapshot as a **thin typed wrapper over the existing** `VolatilityFeatureSurface.get_ticker_snapshot(as_of_date, ticker) -> pd.Series | None` (verified signature in `src/volatility/models.py`). Do **not** introduce a second as-of retrieval mechanism. The wrapper reads that one Series, runs the Phase 1–8 pure functions on the as-of slice, and packages the result.

```python
@dataclass(frozen=True)
class AssetVolatilitySignalSnapshot:
    ticker: str
    as_of_date: pd.Timestamp            # decision/snapshot date t
    information_through_date: pd.Timestamp  # final market date used; = t-1 (one-day lag)

    # Reproducibility metadata (never expose a percentile/state without this context):
    config_key: str
    reference_estimator: str
    historical_window: str
    minimum_history: int
    state_config_version: str
    confirmation_days: int
    agreement_config_version: str | None
    stability_window: str | None

    # Features / diagnostic states:
    annualized_volatility: float | None
    historical_percentile: float | None
    volatility_level: str
    change_5d: float | None
    change_20d: float | None
    direction: str
    short_long_ratio: float | None
    term_state: str
    instantaneous_state: str
    confirmed_state: str
    estimator_agreement: str
    absolute_spread: float | None
    relative_dispersion: float | None
    asset_return_20d: float | None
    price_volatility_context: str
    stability_percentile: float | None
    estimate_stability: str
    raw_vol_of_vol: float | None        # only because a documented consumer may need it; precisely labelled
```

Prefer `stability_percentile` + `estimate_stability`; expose `raw_vol_of_vol` only because a documented consumer might need it (labelled per Phase 8).

`as_of_date` (the decision/snapshot date) is distinct from `information_through_date` (the final market date actually used, `= t-1`). Every percentile/state in the snapshot is accompanied by its window + configuration context.

**Retrieval methods:**

```python
def get_volatility_signal_snapshot(ticker: str, as_of_date: pd.Timestamp) -> AssetVolatilitySignalSnapshot: ...
def get_cross_asset_volatility_snapshot(as_of_date: pd.Timestamp) -> CrossAssetVolatilitySnapshot: ...
```

`CrossAssetVolatilitySnapshot` carries the same reproducibility metadata plus the per-asset snapshots and the Phase 7 ratios/ranking.

**Documented-but-not-implemented future uses** (must not be silently introduced here): position sizing `target_weight ∝ target_vol / estimated_asset_vol`; risk overlays (extreme percentile → lower max weight; low agreement → conservative estimate; unstable estimate → slower weight changes); allocation context (regime + price + normalising vol → stronger/weaker duration evidence). These are future strategy decisions requiring their own reviewed design.

**Tests.** Snapshot values match underlying feature rows; historical as-of queries return historical values; **future rows do not affect earlier snapshots** (`lookahead`); missing optional features represented safely; serialization is stable for API/React; metadata fields populated (no percentile/state without context); `as_of_date != information_through_date` for the lagged surface.

**Acceptance.** (1) Stable typed interface for volatility signals. (2) Point-in-time historical retrieval via the **single** existing `get_ticker_snapshot` path. (3) Frontend/API can consume the same snapshot model. (4) Integration points documented, not wired. (5) No strategy rule or weight changed. (6) No-look-ahead tests. (7) Every snapshot carries full reproducibility metadata and both dates.

**Non-goals.** No sizing/overlay/allocation wiring; no second as-of path.

---

## 10. Cross-phase quality gates

A phase is not merged unless **all** hold:

1. Every derived calculation is isolated by `config_key`; no series mixes configs.
2. The information-time convention is documented **and** tested (vol & price through `t-1`; forward returns strictly after `t`).
3. Adding future rows never changes any historical feature/state (truncation tests pass).
4. API responses use typed Pydantic schemas.
5. NaN/Inf → `null` at the serialization boundary; warm-up and the 2026-06-09 row don't break responses.
6. React receives typed data and builds its own charts; the server never builds chart objects.
7. Every cache key contains all inputs that affect the output (config_key, window, thresholds/classifier version, estimator, confirmation policy, data version).
8. Threshold/classifier configs are versioned/hashable; a config change forces a new cache key.
9. Boundary and edge cases are deterministic and tested.
10. Raw estimator values are unchanged unless a verified defect is fixed.
11. No strategy, sizing, portfolio, or execution behaviour changes.
12. Methodology copy distinguishes **diagnostics** from **validated signals**; no diagnostic state is presented as a validated trading signal before Phase 9.
13. The view remains useful when optional estimators (e.g. GARCH) are missing.
14. The layout is readable on smaller screens.
15. The phase is not merged until backend + API + frontend are all complete for that phase.

---

## 11. Final page layout

After all phases, the Volatility Features page (`frontend/src/pages/VolatilityPage.tsx`):

```text
Volatility Features
  [Asset selector] [Date range] [Reference estimator] [Historical window] [Chart view]

Latest Volatility State (confirmed)
  - annualised volatility, historical percentile, level
  - direction, 20D/60D ratio, term state
  - unified confirmed volatility state (+ instantaneous in tooltip)
  - estimator agreement (absolute spread + relative dispersion)
  - price/volatility context
  - estimate stability (percentile + status)

Main Diagnostic Chart
  - selectable view (volatility / percentile / ratio / change / dispersion)
  - estimator toggles where relevant
  - confirmed-state shading (toggle)
  - persistent, cooldown-debounced transition markers (toggle)

Latest Cross-Asset Signals
  - all-asset confirmed-state table
  - risk ranking
  - relative-volatility ratios (+ percentile context)

Estimator Comparison
  - latest values, percentiles
  - absolute spread vs median + relative diff vs median
  - agreement state

Historical Signal Outcomes
  - forward stats + forward drawdowns + hit rates
  - effective independent observation count + sample-quality labels
  - non-overlapping by default; sampling caveat + disclaimer

Methodology
  - feature definitions, annualisation, lagging policy (one lag, in feature_surface.py)
  - percentile method (average-rank, inclusive), windows, thresholds, GARCH methodology
  - overlap/trend caveats; diagnostics-vs-validated-signals distinction; limitations
```

---

## 12. File organization

Compute under `src/volatility/`, API under `api/`, UI under `frontend/src/`. **No `features/` tree, no `frontend/tabs/*.py` Streamlit files.**

```text
src/volatility/
    feature_surface.py   # existing — surface build + the single 1-day lag
    models.py            # existing — VolatilityFeatureSurface, get_ticker_snapshot
    audit.py             # PR0 — validate_/normalize_volatility_surface
    percentiles.py       # PR1 — point-in-time rolling/expanding rank + level
    direction.py         # PR2 — change + 20D/60D term ratio
    states.py            # PR3 — instantaneous + confirmed state, config, explanation
    agreement.py         # PR4 — absolute spread + relative dispersion + floor
    price_context.py     # PR5 — as-of-(t-1) price direction + joint context
    transitions.py       # PR6 — confirmed-state ranges + debounced/cooldown transitions
    relative.py          # PR7 — cross-asset ratios + ranking
    stability.py         # PR8 — vol-of-vol + stability percentile
    outcomes.py          # PR9 — forward returns/drawdowns + sampling + gates
    snapshot.py          # PR10 — AssetVolatilitySignalSnapshot wrapper over get_ticker_snapshot

api/
    routers/volatility.py    # existing — add endpoints per phase
    services/volatility.py   # existing — call src/volatility pure fns, TTL-cached (§7)
    schemas/volatility.py    # existing — extend with the per-phase Pydantic models

frontend/src/
    pages/VolatilityPage.tsx           # existing — state card, view modes, tables
    components/charts/PlotlyLineChart.tsx  # reuse (series/referenceLines/bands/secondary)

tests/volatility/
    test_audit.py test_percentiles.py test_direction.py test_states.py
    test_agreement.py test_price_context.py test_transitions.py test_relative.py
    test_stability.py test_outcomes.py test_snapshot.py
```

Prefer: pure UI-agnostic calcs; typed configs and snapshots; thin React render components; no calc logic in API handlers or React; `lookahead`- and `determinism`-marked tests consistent with the existing regression-guard markers.

---

## 13. Overall non-goals

Do not:

* Optimise thresholds for historical returns during the dashboard build.
* Treat volatility as a directional return forecast by itself.
* Change strategy rules, sizing, or weights without a separate reviewed design.
* Use full-sample (future-inclusive) statistics for point-in-time features.
* Hide insufficient history.
* Treat overlapping forward outcomes as independent evidence (non-overlapping is the Phase 9 default).
* Select an estimator solely because it produced the best backtest.
* Introduce machine learning.
* Add allocation rules inside frontend or API code; couple React/handlers to portfolio execution.
* Build any feature on the frozen Streamlit stack.
* Build Plotly figures on the backend (`go.Figure`).
* Add daily-yield interpretation without a validated, lagged daily yield source.
* Re-shift any feature already lagged once in `feature_surface.py`.
* Remove the raw estimator-comparison view.

---

## 14. Recommended first PR

**PR0 — Phase 0 only.** Title: *Establish and test the volatility data contract.*

Scope: audit + validation functions; documented data contract; baseline tests (duplicate keys, negatives, warm-up NaN, annualisation, **one-day lag equivalence**, GARCH daily-refit equivalence, the 2026-06-09 NaN→null boundary). No percentiles, no new views, no redesign.

PR description:

```text
This PR establishes a validated, documented point-in-time data contract for the
persisted volatility feature surface and adds baseline tests. It confirms the
single one-day lag (applied in feature_surface.py), annualisation consistency,
the same-return/same-price-column invariant, GARCH causal alignment, and that
warm-up / known all-NaN rows serialise to null without breaking the API.

No interpretation logic, no new views, no visual redesign. Strategy logic,
portfolio weights, and backtest execution are unchanged.
```

Explicit exclusions: direction, ratios, states, agreement, price context, relative vol, vol-of-vol, forward-return analysis, strategy integration.

---

## 15. Final implementation sequence

One phase per PR, in order, each reviewed in the running application before the next begins:

```text
PR0  Phase 0  — audit / data contract / baseline tests
PR1  Phase 1  — historical percentiles + level
PR2  Phase 2  — direction + 20D/60D ratio
PR3  Phase 3  — unified state classifier (instantaneous + confirmed)
PR4  Phase 4  — estimator agreement (relative + absolute floor)
PR5  Phase 5  — price + volatility context (no yield)
PR6  Phase 6  — chart modes / shading / transitions / cooldown / controls
PR7  Phase 7  — cross-asset relative volatility
PR8  Phase 8  — estimate stability (percentile-first)
PR9  Phase 9  — historical outcomes (non-overlapping default + sample gates)
PR10 Phase 10 — passive snapshot interface + reproducibility metadata
```

Phase 1 and Phase 3 give the largest immediate interpretability gains. Phase 9 gives the strongest evidence about whether the diagnostics carry information — but only after the signal definitions are stable. No phase is bundled with another.

---

## Core product principle

The completed view should move the user from:

> These five volatility curves are slightly different.

to:

> TLT volatility is currently Normal relative to its own history, contracting
> relative to its 60-day baseline, estimated consistently across models, and
> associated with a stable positive price trend. Its confirmed state is
> Normalisation. Historically, similar point-in-time states produced these
> forward outcomes — with this independent sample size and these limitations.
