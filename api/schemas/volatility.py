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
    estimate_stability: str           # Phase 8 status
    stability_percentile: float | None  # Phase 8 vol-of-vol percentile (0.0–1.0)


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


class EstimateStabilityResponse(BaseModel):
    """Estimate stability for one ticker (Phase 8). Percentile + Status are primary;
    the raw vol-of-vol is debug/methodology only and precisely labelled."""

    ticker: str
    config_key: str
    stability_percentile: float | None      # 0.0–1.0 (primary)
    percentile_ordinal: int | None
    estimate_stability: str                 # Status (primary)
    stability_window: str
    # Debug/methodology only — "20D std of daily changes in annualised volatility":
    raw_vol_of_vol: float | None


class CrossAssetRatioRow(BaseModel):
    """One cross-asset volatility ratio + its own historical context (Phase 7, monitor only)."""

    pair: str                          # "TLT / AGG"
    current_ratio: float | None
    percentile_ordinal: int | None
    relative_risk_state: str           # Low | Normal | Elevated | High | Extreme | Insufficient history


class AssetRiskRankRow(BaseModel):
    """One row of the all-asset risk ranking (by raw current volatility, Phase 7)."""

    rank: int
    ticker: str
    current_volatility: float | None
    percentile_ordinal: int | None
    confirmed_state: str


class CrossAssetVolatilityResponse(BaseModel):
    """Cross-asset relative-risk diagnostics: per-pair ratios + the asset ranking."""

    as_of_date: str | None
    config_key: str
    reference_estimator: str
    ratios: list[CrossAssetRatioRow]
    ranking: list[AssetRiskRankRow]


class CrossAssetRatioSeriesResponse(BaseModel):
    """One pair's ratio (or its percentile) over time for the Phase 7 chart selector."""

    pair: str
    config_key: str
    reference_estimator: str
    view: str                          # "raw" | "percentile"
    unit: str                          # "ratio" | "percentile"
    series: list[NamedSeries]
    reference_lines: list[float]


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


class SignalOutcomeRow(BaseModel):
    """Forward outcomes that followed one diagnostic state at one horizon (Phase 9).

    ``effective_observations`` is the **independent** count — non-overlapping by
    default. The statistics are gated by sample quality: ``Insufficient sample``
    emits no stats; ``Anecdotal`` emits median / worst / best only; ``Low sample``
    and above emit the full set. Gated-out statistics serialise as ``null``.
    Outcomes describe the sample only — no causality, no guarantee (see the
    response disclaimer).
    """

    state: str
    horizon: str                       # "1M" | "3M" | "6M"
    effective_observations: int        # independent count (non-overlapping by default)
    sample_quality: str                # "Insufficient sample" | "Anecdotal" | "Low sample" | ""
    mean_return: float | None          # None when gated out
    median_return: float | None
    hit_rate: float | None             # fraction of windows with a positive forward return
    std_return: float | None           # sample std of forward returns (Low-sample+ only)
    worst_return: float | None
    best_return: float | None
    forward_max_drawdown: float | None  # worst peak-to-trough inside the forward window (<= 0)


class SignalOutcomeResponse(BaseModel):
    """Historical forward outcomes by diagnostic state for one ticker (Phase 9).

    ``sampling`` is ``"non_overlapping"`` (default) or ``"all"`` (explicit override
    that overstates independent evidence — flagged in ``disclaimer``). ``rows``
    span the states present in the sample across the requested horizons.

    The ``/outcomes/conditions`` endpoint reuses this same shape for the
    combined-condition signals (``state`` then holds the condition label, e.g.
    "Vol rising + price falling"); every defined condition appears, gated to
    "Insufficient sample" when it has too few independent occurrences.
    """

    ticker: str
    config_key: str
    reference_estimator: str
    sampling: str                      # "non_overlapping" (default) | "all"
    horizons: list[str]                # the analysed horizon labels, in order
    rows: list[SignalOutcomeRow]
    disclaimer: str                    # describes-the-sample-only caveat


class StateReturnDistribution(BaseModel):
    """One state's per-observation forward-return sample for the box plot (Phase 9).

    ``returns`` is the list of realised forward returns over the state's (optionally
    non-overlapping) signal dates at one horizon — the raw distribution the box
    summarises, not aggregate stats. ``effective_observations`` is ``len(returns)``.
    """

    state: str
    effective_observations: int
    returns: list[float]


class SignalOutcomeDistributionResponse(BaseModel):
    """Per-state forward-return distributions at one horizon for the box plot (Phase 9).

    Companion to ``SignalOutcomeResponse``: the aggregate endpoint returns gated
    summary stats; this returns the per-observation samples for one ``horizon`` so
    the frontend can draw a box per diagnostic state under the same sampling policy.
    """

    ticker: str
    config_key: str
    reference_estimator: str
    sampling: str                      # "non_overlapping" (default) | "all"
    horizon: str                       # "1M" | "3M" | "6M"
    unit: str = "decimal"              # forward returns are decimal fractions
    distributions: list[StateReturnDistribution]
    disclaimer: str


class AssetVolatilitySnapshotResponse(BaseModel):
    """One asset's passive point-in-time volatility snapshot (Phase 10).

    A stable typed view of the Phase 1–8 diagnostics at ``as_of_date`` with full
    reproducibility metadata (config + versions + both information-time dates), for
    strategy/risk layers to consume. **Passive** — producing it changes no
    allocation, sizing, or weight. ``as_of_date`` is the decision date ``t``;
    ``information_through_date`` is ``t-1`` (the surface is lagged one day).
    """

    ticker: str
    as_of_date: str | None
    information_through_date: str | None
    # reproducibility metadata
    config_key: str
    reference_estimator: str
    historical_window: str
    minimum_history: int
    state_config_version: str
    confirmation_days: int
    agreement_config_version: str | None
    stability_window: str | None
    # features / diagnostic states
    annualized_volatility: float | None
    historical_percentile: float | None
    percentile_ordinal: int | None
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
    raw_vol_of_vol: float | None        # "20D std of daily changes in annualised volatility"


class CrossAssetRatioSnapshotRow(BaseModel):
    """One cross-asset volatility ratio + its own historical context (Phase 10 snapshot)."""

    pair: str
    current_ratio: float | None
    percentile_ordinal: int | None
    relative_risk_state: str


class AssetRiskRankSnapshotRow(BaseModel):
    """One row of the all-asset risk ranking, by raw current volatility (Phase 10 snapshot)."""

    rank: int
    ticker: str
    annualized_volatility: float | None
    historical_percentile: float | None
    confirmed_state: str


class CrossAssetVolatilitySnapshotResponse(BaseModel):
    """All-asset passive snapshot: per-asset snapshots + relative ratios + risk ranking (Phase 10)."""

    as_of_date: str | None
    information_through_date: str | None
    config_key: str
    reference_estimator: str
    historical_window: str
    minimum_history: int
    state_config_version: str
    confirmation_days: int
    agreement_config_version: str | None
    stability_window: str | None
    assets: list[AssetVolatilitySnapshotResponse]
    ratios: list[CrossAssetRatioSnapshotRow]
    ranking: list[AssetRiskRankSnapshotRow]


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
