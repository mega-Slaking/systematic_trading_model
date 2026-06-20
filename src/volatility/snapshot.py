"""Phase 10 — passive strategy-integration snapshot interface.

Exposes the volatility diagnostics to strategy/risk layers through **one stable,
typed, point-in-time snapshot with full reproducibility metadata** — without
changing any allocation logic. The volatility feature surface is already attached
to ``BacktestContext`` (``volatility_feature_surface``) and is explicitly
**passive / unused for sizing**; this interface keeps it that way.

Single as-of access path (§Phase 10): the snapshot is a thin typed wrapper over
the existing ``VolatilityFeatureSurface.get_ticker_snapshot(as_of_date, ticker)``.
That one call supplies (and gates the existence of) the as-of row; the Phase 1–8
diagnostics are then computed from the **trailing** ``date <= as_of`` history of
the same already-one-day-lagged surface, so every percentile/state is point-in-time
and no second as-of retrieval mechanism is introduced.

Information-time (§4.2): ``as_of_date`` is the decision/snapshot date ``t``;
``information_through_date`` is the prior surface date (``t-1``) — the surface is
lagged one day, so the row at ``t`` already carries information only through
``t-1``. The two are deliberately distinct fields.

**Documented-but-NOT-implemented future uses** (must not be silently introduced
here — each is a future strategy decision needing its own reviewed design):

* position sizing ``target_weight ∝ target_vol / estimated_asset_vol``;
* risk overlays (extreme percentile -> lower max weight; low estimator agreement
  -> more conservative estimate; unstable estimate -> slower weight changes);
* allocation context (regime + price + normalising vol -> stronger/weaker
  duration evidence).

This module produces the snapshot only; it wires nothing into allocation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.volatility.agreement import (
    EstimatorAgreementConfig,
    classify_estimator_agreement,
    compute_estimator_dispersion,
)
from src.volatility.constants import (
    CONFIG_KEY_COLUMN,
    DEFAULT_HISTORICAL_WINDOW,
    DEFAULT_REFERENCE_ESTIMATOR,
    HISTORICAL_WINDOWS,
    MIN_PERCENTILE_HISTORY,
    VOL_ESTIMATOR_NAMES,
)
from src.volatility.feature_frame import build_ticker_feature_frame
from src.volatility.models import VolatilityFeatureSurface
from src.volatility.percentiles import (
    classify_volatility_level,
    compute_rolling_percentile,
)
from src.volatility.price_context import (
    PRICE_DIRECTION_THRESHOLD,
    classify_price_volatility_context,
    compute_price_direction_features,
)
from src.volatility.relative import compute_relative_volatility_ratios, default_ratio_pairs
from src.volatility.stability import classify_estimate_stability, compute_volatility_of_volatility
from src.volatility.states import (
    UNKNOWN_STATE,
    VolatilityStateConfig,
    build_latest_volatility_state_table,
)

# Y-axis percentile bands etc. live elsewhere; the snapshot deals in decimals/labels.


@dataclass(frozen=True)
class AssetVolatilitySignalSnapshot:
    """One asset's point-in-time volatility diagnostics + full reproducibility metadata.

    Every percentile/state is accompanied by the window + configuration context
    needed to reproduce it, and both information-time dates. Numeric fields are
    decimals (``None`` when unavailable); state/label fields default to
    ``"Unknown"``. This is a *description of features*, never a trading instruction.
    """

    ticker: str
    as_of_date: pd.Timestamp                     # decision/snapshot date t
    information_through_date: pd.Timestamp | None  # final market date used; = t-1

    # --- reproducibility metadata (never expose a percentile/state without it) ---
    config_key: str
    reference_estimator: str
    historical_window: str
    minimum_history: int
    state_config_version: str
    confirmation_days: int
    agreement_config_version: str | None
    stability_window: str | None

    # --- features / diagnostic states ---
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
    raw_vol_of_vol: float | None        # precisely "20D std of daily changes in annualised vol"


@dataclass(frozen=True)
class CrossAssetRatioSnapshot:
    """One cross-asset volatility ratio + its own historical context (monitor only)."""

    pair: str
    current_ratio: float | None
    percentile_ordinal: int | None
    relative_risk_state: str


@dataclass(frozen=True)
class AssetRiskRankSnapshot:
    """One row of the all-asset risk ranking (by raw current volatility)."""

    rank: int
    ticker: str
    annualized_volatility: float | None
    historical_percentile: float | None
    confirmed_state: str


@dataclass(frozen=True)
class CrossAssetVolatilitySnapshot:
    """All-asset point-in-time snapshot: per-asset snapshots + Phase 7 ratios/ranking.

    Carries the same reproducibility metadata as the per-asset snapshot so the whole
    cross-asset view is reproducible from one object.
    """

    as_of_date: pd.Timestamp
    information_through_date: pd.Timestamp | None
    config_key: str
    reference_estimator: str
    historical_window: str
    minimum_history: int
    state_config_version: str
    confirmation_days: int
    agreement_config_version: str | None
    stability_window: str | None
    assets: tuple[AssetVolatilitySignalSnapshot, ...]
    ratios: tuple[CrossAssetRatioSnapshot, ...]
    ranking: tuple[AssetRiskRankSnapshot, ...]


def _f(value: object) -> float | None:
    """Scalar -> float, with NaN/None -> ``None`` (the snapshot's missing convention)."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    return float(value)


def _resolve_window(window_key: str) -> int | None:
    """Window key -> trailing length; ``"Full"`` -> ``None`` (expanding)."""
    if window_key == "Full":
        return None
    if window_key in HISTORICAL_WINDOWS:
        return HISTORICAL_WINDOWS[window_key]
    raise ValueError(f"unknown historical window '{window_key}'")


@dataclass(frozen=True)
class VolatilitySignalSnapshotProvider:
    """Thin typed wrapper over a ``VolatilityFeatureSurface`` (§Phase 10).

    Holds the surface (and, optionally, a long ``date, ticker, close`` price frame
    for the Phase 5 price-context fields) plus the reference estimator / window /
    threshold configuration, and exposes the two as-of retrieval methods. All
    point-in-time retrieval goes through ``surface.get_ticker_snapshot``; no second
    as-of mechanism is introduced. Nothing here mutates the surface or touches
    allocation.
    """

    surface: VolatilityFeatureSurface
    prices: pd.DataFrame | None = None
    reference_estimator: str = DEFAULT_REFERENCE_ESTIMATOR
    historical_window: str = DEFAULT_HISTORICAL_WINDOW
    minimum_history: int = MIN_PERCENTILE_HISTORY
    state_config: VolatilityStateConfig = field(default_factory=VolatilityStateConfig)
    agreement_config: EstimatorAgreementConfig = field(default_factory=EstimatorAgreementConfig)
    stability_window: str = DEFAULT_HISTORICAL_WINDOW

    # -- internal helpers ---------------------------------------------------- #

    def _ticker_history(self, ticker: str, as_of: pd.Timestamp, config_key: str) -> pd.DataFrame:
        """Trailing ``date <= as_of`` history for one ticker within a single config_key."""
        vals = self.surface.values
        hist = vals[(vals["ticker"] == ticker) & (vals["date"] <= as_of)]
        if config_key and CONFIG_KEY_COLUMN in hist.columns:
            hist = hist[hist[CONFIG_KEY_COLUMN].astype(str) == config_key]
        return hist.sort_values("date").reset_index(drop=True)

    def _price_context(
        self, ticker: str, as_of: pd.Timestamp, vol_change_20d: float | None
    ) -> tuple[float | None, str]:
        """As-of-(t-1) 20D price return + the joint price/volatility context label.

        Returns ``(None, "Unknown")`` when no price history was supplied for the
        ticker — the snapshot stays valid, the price fields are simply absent.
        """
        if self.prices is None or self.prices.empty or "close" not in self.prices.columns:
            return None, UNKNOWN_STATE
        p = self.prices[(self.prices["ticker"] == ticker) & (self.prices["date"] <= as_of)]
        if p.empty:
            return None, UNKNOWN_STATE
        close = p.sort_values("date").set_index("date")["close"].ffill()
        returns = compute_price_direction_features(close, horizons=(20,))["price_return_20d"]
        asset_return_20d = _f(returns.iloc[-1]) if len(returns) else None
        context = classify_price_volatility_context(
            asset_return_20d, vol_change_20d, PRICE_DIRECTION_THRESHOLD, self.state_config.rising_change
        )
        return asset_return_20d, context

    def _missing_snapshot(self, ticker: str, as_of: pd.Timestamp) -> AssetVolatilitySignalSnapshot:
        """Snapshot for a ticker/date with no surface row — metadata populated, features blank."""
        return AssetVolatilitySignalSnapshot(
            ticker=ticker, as_of_date=as_of, information_through_date=None,
            config_key="", reference_estimator=self.reference_estimator,
            historical_window=self.historical_window, minimum_history=self.minimum_history,
            state_config_version=self.state_config.version(),
            confirmation_days=self.state_config.confirmation_days,
            agreement_config_version=self.agreement_config.version(),
            stability_window=self.stability_window,
            annualized_volatility=None, historical_percentile=None,
            volatility_level=classify_volatility_level(None), change_5d=None, change_20d=None,
            direction=UNKNOWN_STATE, short_long_ratio=None, term_state=UNKNOWN_STATE,
            instantaneous_state=UNKNOWN_STATE, confirmed_state=UNKNOWN_STATE,
            estimator_agreement=UNKNOWN_STATE, absolute_spread=None, relative_dispersion=None,
            asset_return_20d=None, price_volatility_context=UNKNOWN_STATE,
            stability_percentile=None, estimate_stability=UNKNOWN_STATE, raw_vol_of_vol=None,
        )

    # -- public API ---------------------------------------------------------- #

    def get_volatility_signal_snapshot(
        self, ticker: str, as_of_date: pd.Timestamp
    ) -> AssetVolatilitySignalSnapshot:
        """Point-in-time signal snapshot for one ticker as-of ``as_of_date``.

        Retrieval goes through ``surface.get_ticker_snapshot`` (the single as-of
        path); the diagnostics are computed from the trailing ``date <= as_of``
        history so they are causal. A missing as-of row yields a metadata-only
        snapshot (all features blank) rather than an error.
        """
        as_of = pd.to_datetime(as_of_date)
        as_of_row = self.surface.get_ticker_snapshot(as_of, ticker)
        if as_of_row is None:
            return self._missing_snapshot(ticker, as_of)

        config_key = str(as_of_row.get(CONFIG_KEY_COLUMN, "") or "")
        estimator = self.reference_estimator
        hist = self._ticker_history(ticker, as_of, config_key)

        feats = build_ticker_feature_frame(
            hist, estimator=estimator, window=_resolve_window(self.historical_window),
            min_periods=self.minimum_history, config=self.state_config, ticker=ticker,
        )
        # As-of confirmed/instantaneous state via the same latest-on/before-as_of
        # selector the dashboard uses (point-in-time, debounced).
        state_table = build_latest_volatility_state_table(feats, as_of, self.state_config)
        state_row = state_table.iloc[0]
        last = feats.iloc[-1]
        information_through_date = hist["date"].iloc[-2] if len(hist) >= 2 else None

        # Estimator agreement at the as-of row (across the five estimators).
        dispersion = compute_estimator_dispersion(
            hist, VOL_ESTIMATOR_NAMES, self.agreement_config.min_estimators
        ).iloc[-1]
        absolute_spread = _f(dispersion["absolute_spread"])
        relative_dispersion = _f(dispersion["relative_dispersion"])

        # Estimate stability (vol-of-vol percentile) at the as-of row.
        vov = compute_volatility_of_volatility(hist[estimator], window=20)
        stability_pct = compute_rolling_percentile(
            vov, _resolve_window(self.stability_window), self.minimum_history
        )
        stability_percentile = _f(stability_pct.iloc[-1]) if len(stability_pct) else None

        change_20d = _f(last["change_20d"])
        asset_return_20d, price_context = self._price_context(ticker, as_of, change_20d)

        return AssetVolatilitySignalSnapshot(
            ticker=ticker, as_of_date=as_of, information_through_date=information_through_date,
            config_key=config_key, reference_estimator=estimator,
            historical_window=self.historical_window, minimum_history=self.minimum_history,
            state_config_version=self.state_config.version(),
            confirmation_days=self.state_config.confirmation_days,
            agreement_config_version=self.agreement_config.version(),
            stability_window=self.stability_window,
            annualized_volatility=_f(last["current_volatility"]),
            historical_percentile=_f(last["percentile"]),
            volatility_level=str(last["volatility_level"]),
            change_5d=_f(last["change_5d"]),
            change_20d=change_20d,
            direction=str(last["direction"]),
            short_long_ratio=_f(last["term_ratio"]),
            term_state=str(last["term_state"]),
            instantaneous_state=str(state_row["instantaneous_state"]),
            confirmed_state=str(state_row["confirmed_state"]),
            estimator_agreement=classify_estimator_agreement(
                relative_dispersion, absolute_spread, self.agreement_config
            ),
            absolute_spread=absolute_spread,
            relative_dispersion=relative_dispersion,
            asset_return_20d=asset_return_20d,
            price_volatility_context=price_context,
            stability_percentile=stability_percentile,
            estimate_stability=classify_estimate_stability(stability_percentile),
            raw_vol_of_vol=_f(vov.iloc[-1]) if len(vov) else None,
        )

    def get_cross_asset_volatility_snapshot(
        self, as_of_date: pd.Timestamp
    ) -> CrossAssetVolatilitySnapshot:
        """All-asset snapshot: per-asset snapshots + relative-vol ratios + risk ranking.

        Each asset reuses ``get_volatility_signal_snapshot``; the ranking is by raw
        current volatility (percentile + confirmed state carry the real relative
        context); the ratios reuse the Phase 7 ratio maths with their own as-of
        historical percentile. Monitor only — no allocation implication.
        """
        as_of = pd.to_datetime(as_of_date)
        vals = self.surface.values
        present = vals[vals["date"] <= as_of]
        tickers = sorted(str(t) for t in present["ticker"].dropna().unique())

        assets = tuple(self.get_volatility_signal_snapshot(t, as_of) for t in tickers)
        assets = tuple(a for a in assets if a.config_key != "")  # drop tickers with no as-of row

        config_key = assets[0].config_key if assets else ""
        information_through_date = assets[0].information_through_date if assets else None

        ratios = self._cross_asset_ratios([a.ticker for a in assets], as_of, config_key)
        ranking = _rank_assets(assets)

        return CrossAssetVolatilitySnapshot(
            as_of_date=as_of, information_through_date=information_through_date,
            config_key=config_key, reference_estimator=self.reference_estimator,
            historical_window=self.historical_window, minimum_history=self.minimum_history,
            state_config_version=self.state_config.version(),
            confirmation_days=self.state_config.confirmation_days,
            agreement_config_version=self.agreement_config.version(),
            stability_window=self.stability_window,
            assets=assets, ratios=ratios, ranking=ranking,
        )

    def _cross_asset_ratios(
        self, tickers: list[str], as_of: pd.Timestamp, config_key: str
    ) -> tuple[CrossAssetRatioSnapshot, ...]:
        """Per-pair relative-vol ratio + as-of historical percentile (Phase 7 maths)."""
        estimator = self.reference_estimator
        vals = self.surface.values
        sliced = vals[vals["date"] <= as_of]
        if config_key and CONFIG_KEY_COLUMN in sliced.columns:
            sliced = sliced[sliced[CONFIG_KEY_COLUMN].astype(str) == config_key]
        if sliced.empty or estimator not in sliced.columns:
            return ()

        wide = sliced.pivot_table(index="date", columns="ticker", values=estimator).sort_index()
        pairs = default_ratio_pairs(tickers)
        ratio_df = compute_relative_volatility_ratios(wide, pairs)

        out: list[CrossAssetRatioSnapshot] = []
        for a, b in pairs:
            col = f"{a}/{b}"
            if col not in ratio_df.columns:
                continue
            pct = compute_rolling_percentile(
                ratio_df[col], _resolve_window(self.historical_window), self.minimum_history
            )
            pct_val = _f(pct.iloc[-1]) if len(pct) else None
            out.append(
                CrossAssetRatioSnapshot(
                    pair=f"{a} / {b}",
                    current_ratio=_f(ratio_df[col].iloc[-1]) if len(ratio_df) else None,
                    percentile_ordinal=(None if pct_val is None else int(round(pct_val * 100))),
                    relative_risk_state=classify_volatility_level(pct_val),
                )
            )
        return tuple(out)


def _rank_assets(
    assets: tuple[AssetVolatilitySignalSnapshot, ...]
) -> tuple[AssetRiskRankSnapshot, ...]:
    """Rank assets by raw annualized volatility (descending; missing vol sorts last)."""
    ordered = sorted(
        assets,
        key=lambda a: (a.annualized_volatility is None, -(a.annualized_volatility or 0.0)),
    )
    return tuple(
        AssetRiskRankSnapshot(
            rank=i + 1, ticker=a.ticker, annualized_volatility=a.annualized_volatility,
            historical_percentile=a.historical_percentile, confirmed_state=a.confirmed_state,
        )
        for i, a in enumerate(ordered)
    )
