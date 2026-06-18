# Volatility Surface — Data Contract (as built, PR0 / Phase 0)

This is the **as-built** contract for the persisted `volatility_features` surface,
the foundation every later phase of the Volatility Features dashboard builds on
(see `docs/vol_features_plan.md` §4 for the design-level statement). It records
what the code guarantees today, where each guarantee is enforced, and how it is
verified.

## Surface shape

One row per `(date, ticker)` within a single `config_key`. Columns:

```text
date, ticker,
rolling_20, rolling_60, ewma_94, ewma_97, garch,          # five raw estimators
ewma_94_to_rolling_20, ewma_94_change_5d,                 # persisted comparison features
ewma_97_to_rolling_20, ewma_97_change_5d,
config_key
```

Canonical column names live in `src/volatility/constants.py`
(`VOL_ESTIMATOR_COLUMNS`, `COMPARISON_FEATURE_COLUMNS`) and are identical across
the in-memory build (`feature_surface.py`), the schema (`data/db_population.py`),
the writer (`db_writer._VOLATILITY_FEATURE_COLUMNS`), the reader
(`db_reader.get_volatility_features`), the API service
(`api/services/volatility.py:_VOL_METHODS`) and the React method map. The draft
names `rolling_20d` / `ewma_094` / `garch_11` exist nowhere and must not return.

As observed on the live DB: **18,018 rows, one `config_key`, zero warnings.**

## Guarantees

1. **One lag, applied once.** `feature_surface._lag_feature_columns` shifts every
   non-key column by `lag_features_days` (default 1) per ticker, at the end of the
   build. The value at row `t` is therefore what was computable at the close of
   `t-1`. **Derived features (percentiles, direction, ratios, dispersion,
   vol-of-vol) are computed on these already-lagged columns and are never
   re-shifted.** Adding a second `.shift(1)` "to be safe" is the single most
   common subtle bug here and is prohibited.

2. **Annualised volatilities are decimals.** `0.09` means 9%. Display layers
   convert to percent; internal math stays in decimals. `validate_volatility_surface`
   warns if any value exceeds a 5.0 sanity ceiling (i.e. looks like a percentage).

3. **`config_key` isolation.** `config_key = str(VolatilityFeatureConfig.cache_key())`.
   All derived features must be computed within a single `config_key`; mixing
   configs would silently corrupt every point-in-time percentile/ratio.
   `normalize_volatility_surface` **raises** if handed more than one.

4. **Warm-up `NaN`s are expected and preserved.** Rolling/EWMA/GARCH `min_history`
   plus the one-day lag (which drops the first row per ticker) produce leading
   `NaN`s. Normalization never drops them; they cross the JSON boundary as `null`
   via `api/serialization/frames.py:nan_to_none`. A known all-`NaN` `etf_prices`
   row at **2026-06-09** propagates `NaN` into derived features for that date and
   must serialise to `null` (it does — it triggers no audit warning).

5. **GARCH is causal.** Monthly refit + daily roll-forward of
   `var_t = ω + α·ε²_{t-1} + β·var_{t-1}`, then lagged by 1.
   `garch_refit_frequency="daily"` reduces exactly to the point-in-time estimator
   in `src/volatility/estimator.py` — the validated correctness anchor.

## Enforcement / tooling (`src/volatility/audit.py`)

* `validate_volatility_surface(surface_df, estimator_columns) -> list[str]` —
  non-fatal warnings: missing keys/estimators, duplicate `(date, ticker[,
  config_key])`, negative vols, non-monotonic per-ticker dates, multiple
  `config_key`s, and the decimals-not-percent heuristic. Never raises on data
  content. Surfaced read-only at `GET /api/v1/volatility-features/audit`.
* `normalize_volatility_surface(surface_df) -> pd.DataFrame` — coerces `date`,
  orders columns canonically, sorts by `(ticker, date)`, preserves warm-up
  `NaN`s, and raises on missing keys or mixed `config_key`.
* `surface_data_version(surface_df) -> (str(max_date), row_count)` — the cache
  freshness token (spec §7); callers slice to one `(config_key, ticker)` first.

## Verification (tests)

* `tests/volatility/test_audit.py` — validate/normalize/data_version unit cases,
  plus a `lookahead`-marked guard that truncating every row after `t` leaves all
  values on/before `t` unchanged (the never-re-shift contract).
* `tests/features/test_volatility_surface.py` — rolling/EWMA/GARCH equal the
  point-in-time estimator; `daily` GARCH refit equivalence anchor.
* `api/tests/test_volatility.py` — the audit endpoint returns 200, a warnings
  list, and strict JSON (no `NaN`/`Infinity` tokens).
