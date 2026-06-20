"""Canonical volatility-feature constants (design spec §5).

Single source of truth for the five raw estimator column names, the historical
percentile windows, and the default minimum history. These estimator names are
identical across every layer that touches the surface:

* the in-memory build (``feature_surface.py``),
* the DB schema (``data/db_population.py``),
* the writer constant (``db_writer._VOLATILITY_FEATURE_COLUMNS``),
* the reader (``db_reader.get_volatility_features``),
* the API service (``api.services.volatility._VOL_METHODS``),
* the React method map (``VolatilityPage.tsx``).

Import these constants rather than re-typing string literals so the naming can
never drift apart again. The earlier draft names ``rolling_20d`` / ``ewma_094`` /
``garch_11`` exist nowhere in the codebase and must not be reintroduced.
"""

from __future__ import annotations

# Key (non-feature) columns of the persisted surface.
SURFACE_KEY_COLUMNS: tuple[str, ...] = ("date", "ticker")
CONFIG_KEY_COLUMN = "config_key"

# The five raw annualized estimators, internal-name -> display label, in display order.
VOL_ESTIMATOR_COLUMNS: dict[str, str] = {
    "rolling_20": "Rolling 20D",
    "rolling_60": "Rolling 60D",
    "ewma_94": "EWMA λ=0.94",
    "ewma_97": "EWMA λ=0.97",
    "garch": "GARCH(1,1)",
}

# Ordered list of the raw estimator internal names.
VOL_ESTIMATOR_NAMES: list[str] = list(VOL_ESTIMATOR_COLUMNS)

# Comparison features already persisted by ``_add_comparison_features``. Listed so
# later phases never recompute or duplicate them.
COMPARISON_FEATURE_COLUMNS: tuple[str, ...] = (
    "ewma_94_to_rolling_20",
    "ewma_94_change_5d",
    "ewma_97_to_rolling_20",
    "ewma_97_change_5d",
)

# Default reference estimator for single-series interpretation (responsive,
# easy to explain). Later phases may make it selectable; never switch it silently.
DEFAULT_REFERENCE_ESTIMATOR = "rolling_20"

# Historical percentile windows in *trading observations* (not calendar days).
# "Full" history is represented by an expanding window and is intentionally
# absent from this map.
HISTORICAL_WINDOWS: dict[str, int] = {"3Y": 756, "5Y": 1260, "10Y": 2520}
DEFAULT_HISTORICAL_WINDOW = "5Y"

# Minimum non-NaN observations required before a percentile is emitted (configurable).
MIN_PERCENTILE_HISTORY = 126
