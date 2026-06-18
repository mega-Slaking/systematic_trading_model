"""Volatility-features schemas (spec endpoints 8 + 9, Tab 5).

Endpoint 8 returns the per-method volatility lines for one ticker; endpoint 9 the
latest-per-ticker values table. Methods mirror the tab's ``_VOL_METHODS`` keys.
"""

from __future__ import annotations

from pydantic import BaseModel

from api.schemas.common import NamedSeries


class VolatilityContextResponse(BaseModel):
    """Latest point-in-time percentile context for one ticker/estimator (Phase 1).

    ``historical_percentile`` is the internal 0.0–1.0 value; ``percentile_ordinal``
    is the 0–100 display form ("24th"). ``as_of_date`` is the snapshot date ``t``;
    ``information_through_date`` is ``t-1`` (the surface is lagged one day, §4.2).
    """

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
    # --- Phase 2: direction + 20D/60D term ratio ---
    direction: str                    # "Rising" | "Falling" | "Stable" | "Unknown"
    change_5d: float | None           # relative change (fraction)
    change_20d: float | None          # relative change (fraction); drives `direction`
    term_ratio: float | None          # rolling_20 / rolling_60
    term_state: str                   # "Expansion" | "Balanced" | "Contraction" | "Unknown"
    # --- Phase 3: unified diagnostic state ---
    instantaneous_state: str          # direct precedence output (may flicker)
    confirmed_state: str              # persistence-debounced; what the card shows
    state_explanation: str            # deterministic one-line explanation
    state_config_version: str         # hash of the state thresholds/confirmation policy
    # --- Phase 4: estimator agreement ---
    estimator_agreement: str          # "High" | "Moderate" | "Low" | "Unknown"
    absolute_spread: float | None     # max − min across estimators (decimals)
    relative_dispersion: float | None # (max − min) / median
    agreement_config_version: str     # hash of the agreement thresholds/floor
    # --- Phase 5: price/volatility context ---
    price_volatility_context: str     # "Adverse Shock" | "Positive Volatility Expansion" | …
    asset_return_20d: float | None    # as-of-(t-1) 20-day price return
    vol_change_20d: float | None      # 20-day relative volatility change (== change_20d)


class VolatilityPercentileSeriesResponse(BaseModel):
    """The historical-percentile line for one ticker/estimator/window (Phase 1).

    ``series`` carries 0.0–1.0 percentile points (``unit="percentile"``);
    ``reference_lines`` are the band edges [0.20, 0.60, 0.80, 0.95] for the chart.
    """

    ticker: str
    config_key: str
    reference_estimator: str
    historical_window: str
    unit: str = "percentile"          # 0.0–1.0
    series: list[NamedSeries]         # percentile line(s)
    reference_lines: list[float]      # [0.20, 0.60, 0.80, 0.95]


class VolatilityStateRow(BaseModel):
    """One asset's confirmed diagnostic state + supporting features (Phase 3 table)."""

    ticker: str
    confirmed_state: str
    percentile_ordinal: int | None
    current_volatility: float | None
    change_20d: float | None
    term_ratio: float | None
    term_state: str
    price_volatility_context: str     # Phase 5 joint context
    asset_return_20d: float | None    # Phase 5 as-of-(t-1) 20-day price return


class VolatilityStateTableResponse(BaseModel):
    """Latest confirmed-state across all assets (supplements the raw latest table)."""

    as_of_date: str | None
    config_key: str
    reference_estimator: str
    state_config_version: str
    rows: list[VolatilityStateRow]


class EstimatorComparisonRow(BaseModel):
    """One estimator's reading vs the cross-estimator median (Phase 4 panel).

    The old ambiguous "Difference vs Median" is split into an explicit absolute
    (annualised-vol percentage-point) column and a relative (%) column.
    """

    estimator: str                       # display label
    method: str                          # internal key
    current_volatility: float | None
    historical_percentile_ordinal: int | None
    absolute_diff_vs_median: float | None    # decimals; "Absolute diff vs median (pp)"
    relative_diff_vs_median: float | None    # ratio;    "Relative diff vs median (%)"


class EstimatorAgreementResponse(BaseModel):
    """Estimator-agreement summary + per-estimator comparison panel (Phase 4)."""

    ticker: str
    config_key: str
    agreement: str
    absolute_spread: float | None
    relative_dispersion: float | None
    highest_estimator: str | None        # display label
    lowest_estimator: str | None         # display label
    agreement_config_version: str
    rows: list[EstimatorComparisonRow]


class VolatilityPoint(BaseModel):
    """A single (date, value) chart point; ``value`` is ``null`` for NaN/Inf."""

    date: str
    value: float | None


class VolatilitySeries(BaseModel):
    """A named chart trace with an explicit axis unit (Phase 6 typed chart data)."""

    name: str                 # display label
    method: str | None        # internal estimator key, where relevant
    unit: str                 # "decimal" | "percentile" | "ratio" | "decimal_change"
    points: list[VolatilityPoint]


class VolatilityStateRange(BaseModel):
    """A contiguous confirmed-state band for chart shading."""

    start: str
    end: str
    state: str


class VolatilityTransition(BaseModel):
    """A confirmed, cooldown-gated regime transition for a chart marker."""

    date: str
    kind: str                 # "entered_high", "entered_normalisation", …
    from_state: str | None
    to_state: str | None
    label: str


class VolatilityChartResponse(BaseModel):
    """Unified typed chart payload for any view (Phase 6).

    React assembles the Plotly traces from ``series``; ``state_ranges`` drive
    optional shading, ``transitions`` drive optional markers, ``reference_lines``
    are horizontal guides, and ``unit`` is the axis unit for ``view_mode``. No
    ``go.Figure`` is ever built on the backend.
    """

    ticker: str
    config_key: str
    view_mode: str            # "volatility" | "percentile" | "ratio" | "change" | "dispersion"
    unit: str
    as_of_date: str | None
    series: list[VolatilitySeries]
    state_ranges: list[VolatilityStateRange]
    transitions: list[VolatilityTransition]
    reference_lines: list[float]


class VolatilityRatioChangeResponse(BaseModel):
    """A Phase 2 derived-feature line: the 20D/60D term ratio or volatility change.

    ``view`` selects the feature: ``"ratio"`` (rolling_20/rolling_60, ``unit`` =
    ``"ratio"``, reference lines [0.85, 1.00, 1.15]) or ``"change"`` (relative
    changes, ``unit`` = ``"relative_change"``, reference lines [-0.10, 0, 0.10]).
    """

    ticker: str
    config_key: str
    reference_estimator: str
    view: str                         # "ratio" | "change"
    unit: str                         # "ratio" | "relative_change"
    series: list[NamedSeries]
    reference_lines: list[float]


class VolatilityFeaturesResponse(BaseModel):
    """Vol estimate lines for one ticker (Tab 5 chart). Series names are display
    labels; ``meta.method`` carries the raw key. ``available_methods`` lists the
    method keys that are non-empty for this ticker."""

    ticker: str
    series: list[NamedSeries]
    available_methods: list[str]


class VolLatestRow(BaseModel):
    """Latest annualized vol per method for one ticker (Tab 5 table)."""

    ticker: str
    date: str | None
    rolling_20: float | None
    rolling_60: float | None
    ewma_94: float | None
    ewma_97: float | None
    garch: float | None


class VolatilityLatestResponse(BaseModel):
    """Latest-values table across all tickers."""

    methods: list[str]
    rows: list[VolLatestRow]


class VolatilityAuditResponse(BaseModel):
    """Phase 0 data-contract diagnostics for the persisted surface.

    ``warnings`` is the (possibly empty) list of non-fatal data-quality findings
    from ``validate_volatility_surface``; an empty list means the surface passed
    every check. ``config_keys`` and ``n_rows`` describe the audited slice. This
    is a read-only diagnostic endpoint and must never break the page.
    """

    warnings: list[str]
    config_keys: list[str]
    n_rows: int
