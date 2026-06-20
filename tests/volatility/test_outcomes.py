"""Phase 9 — historical signal outcome analysis tests.

Covers the four-way correctness contract: forward-return alignment (the state
side and the forward side use opposite date conventions and are never mixed),
no-look-ahead in signal construction, the non-overlapping sampler, the
forward-window drawdown, state grouping, the mandatory minimum-sample gates, and
the no-many-to-many-join guard.
"""

import numpy as np
import pandas as pd
import pytest

from src.volatility.outcomes import (
    COND_AGREEMENT_LOW,
    COND_RATIO_EXPANSION,
    COND_RELATIVE_VOL_EXTREME,
    COND_VOL_DOWN_AFTER_HIGH,
    COND_VOL_UP_PRICE_DOWN,
    COND_VOL_UP_PRICE_UP,
    DEFAULT_MIN_SAMPLE_GATES,
    FORWARD_HORIZONS,
    build_combined_condition_outcome_table,
    build_state_return_distribution,
    build_volatility_signal_outcome_table,
    classify_sample_quality,
    compute_combined_condition_flags,
    compute_forward_asset_returns,
    compute_forward_window_drawdowns,
    select_non_overlapping_dates,
)


def _prices(values, start="2021-01-04"):
    idx = pd.bdate_range(start, periods=len(values))
    return pd.Series(np.asarray(values, dtype=float), index=idx)


# --------------------------------------------------------------------------- #
# compute_forward_asset_returns — alignment, after-t, terminal NaNs
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_forward_return_is_after_t():
    # price[t+h] / price[t] - 1, reading only future bars.
    prices = _prices([100, 110, 121, 133.1])
    fwd = compute_forward_asset_returns(prices, {"1M": 1})
    col = fwd["forward_return_1M"]
    assert col.iloc[0] == pytest.approx(0.10)   # 110/100 - 1
    assert col.iloc[1] == pytest.approx(0.10)   # 121/110 - 1
    assert col.iloc[2] == pytest.approx(0.10)   # 133.1/121 - 1
    assert pd.isna(col.iloc[3])                  # no future bar -> NaN


@pytest.mark.unit
def test_forward_return_terminal_window_is_nan():
    prices = _prices(np.linspace(100, 150, 30))
    fwd = compute_forward_asset_returns(prices, {"3M": 5})
    # The final 5 rows have no full forward window.
    assert fwd["forward_return_3M"].iloc[-5:].isna().all()
    assert not pd.isna(fwd["forward_return_3M"].iloc[-6])


@pytest.mark.unit
def test_forward_return_zero_base_is_nan():
    prices = _prices([0.0, 100.0, 110.0])
    fwd = compute_forward_asset_returns(prices, {"1M": 1})
    assert pd.isna(fwd["forward_return_1M"].iloc[0])    # 100/0 -> inf -> NaN


@pytest.mark.unit
def test_forward_horizons_default_excludes_12m():
    assert FORWARD_HORIZONS == {"1M": 21, "3M": 63, "6M": 126}


# --------------------------------------------------------------------------- #
# no-look-ahead in signal construction (the cardinal Phase 9 test)
# --------------------------------------------------------------------------- #


@pytest.mark.lookahead
def test_forward_return_reads_only_prices_after_t():
    # Mutating a price strictly *after* t+h must not change forward_return at t for
    # horizon h; mutating price[t+h] must. This pins the "strictly after t" contract.
    prices = _prices(np.linspace(100, 200, 40))
    base = compute_forward_asset_returns(prices, {"3M": 5})["forward_return_3M"]

    # Bump a bar far beyond t=0's 5-bar window — t=0 unchanged.
    bumped_far = prices.copy()
    bumped_far.iloc[20] *= 1.5
    far = compute_forward_asset_returns(bumped_far, {"3M": 5})["forward_return_3M"]
    assert far.iloc[0] == pytest.approx(base.iloc[0])

    # Bump the endpoint of t=0's window (price[5]) — t=0 *does* change.
    bumped_end = prices.copy()
    bumped_end.iloc[5] *= 1.5
    end = compute_forward_asset_returns(bumped_end, {"3M": 5})["forward_return_3M"]
    assert end.iloc[0] != pytest.approx(base.iloc[0])


@pytest.mark.lookahead
def test_truncating_after_t_does_not_change_state_outcome_join():
    # The state side is the already-lagged surface; truncating rows after t must
    # not change the (state, forward_return) pairing for dates on/before t.
    prices = _prices(np.linspace(100, 130, 30))
    fwd_full = compute_forward_asset_returns(prices, {"1M": 3})
    fwd_trunc = compute_forward_asset_returns(prices.iloc[:20], {"1M": 3})
    # On/before the truncation point, every fully-formed window matches exactly.
    pd.testing.assert_series_equal(
        fwd_full["forward_return_1M"].iloc[:17],
        fwd_trunc["forward_return_1M"].iloc[:17],
        check_exact=False, rtol=1e-12,
    )


# --------------------------------------------------------------------------- #
# compute_forward_window_drawdowns
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_drawdown_monotonic_up_is_zero():
    prices = _prices([100, 101, 102, 103, 104])
    dd = compute_forward_window_drawdowns(prices, {"1M": 3})
    assert dd["forward_max_drawdown_1M"].iloc[0] == pytest.approx(0.0)


@pytest.mark.unit
def test_drawdown_captures_intra_window_trough():
    # Up then down within the window: worst peak-to-trough is the trough vs the peak.
    prices = _prices([100, 120, 90, 110])
    dd = compute_forward_window_drawdowns(prices, {"1M": 3})
    # window after t0 = [120, 90, 110], anchored at 100 -> running peak 120, trough 90.
    assert dd["forward_max_drawdown_1M"].iloc[0] == pytest.approx(90 / 120 - 1)


@pytest.mark.unit
def test_drawdown_terminal_window_is_nan():
    prices = _prices(np.linspace(100, 150, 20))
    dd = compute_forward_window_drawdowns(prices, {"3M": 5})
    assert dd["forward_max_drawdown_3M"].iloc[-5:].isna().all()


# --------------------------------------------------------------------------- #
# select_non_overlapping_dates
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_non_overlapping_picks_every_h_positions():
    dates = pd.Series(pd.bdate_range("2021-01-04", periods=20))
    kept = select_non_overlapping_dates(dates, horizon_days=5)
    # First pick is position 0, then 5, 10, 15.
    assert kept.tolist() == [dates.iloc[i] for i in (0, 5, 10, 15)]


@pytest.mark.unit
def test_non_overlapping_skips_overlapping_candidates():
    # A sparse, irregular set of positions: greedy pick excludes anyone within h.
    dates = pd.Series(pd.bdate_range("2021-01-04", periods=12)).iloc[[0, 1, 2, 6, 7, 11]]
    kept = select_non_overlapping_dates(dates, horizon_days=5)
    # pick pos0; exclude pos1,2 (within 5); next eligible pos6; exclude pos7; next pos11.
    assert kept.tolist() == [dates.iloc[i] for i in (0, 3, 5)]  # positional in the *subset*


@pytest.mark.unit
def test_non_overlapping_deduplicates_and_sorts():
    raw = pd.Series(pd.to_datetime(["2021-01-06", "2021-01-04", "2021-01-04", "2021-01-05"]))
    kept = select_non_overlapping_dates(raw, horizon_days=1)
    # Sorted ascending, de-duplicated; h=1 keeps adjacent distinct dates.
    assert kept.tolist() == list(pd.to_datetime(["2021-01-04", "2021-01-05", "2021-01-06"]))


@pytest.mark.unit
def test_non_overlapping_empty_and_nonpositive_horizon():
    assert select_non_overlapping_dates(pd.Series([], dtype="datetime64[ns]"), 5).empty
    dates = pd.Series(pd.bdate_range("2021-01-04", periods=4))
    # h<=0 -> no overlap constraint, every unique date survives.
    assert select_non_overlapping_dates(dates, 0).tolist() == dates.tolist()


# --------------------------------------------------------------------------- #
# classify_sample_quality — gate boundaries
# --------------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize(
    "n, expected",
    [
        (0, "Insufficient sample"),
        (4, "Insufficient sample"),
        (5, "Anecdotal"),
        (9, "Anecdotal"),
        (10, "Low sample"),
        (19, "Low sample"),
        (20, ""),
        (200, ""),
    ],
)
def test_sample_quality_gate_boundaries(n, expected):
    assert classify_sample_quality(n, DEFAULT_MIN_SAMPLE_GATES) == expected


# --------------------------------------------------------------------------- #
# build_volatility_signal_outcome_table — grouping, gating, hit rate, joins
# --------------------------------------------------------------------------- #


def _outcome_inputs(states, returns, drawdowns=None, start="2021-01-04"):
    idx = pd.bdate_range(start, periods=len(states))
    feats = pd.DataFrame({"date": idx, "confirmed_state": states})
    cols = {"date": idx, "forward_return_1M": returns}
    if drawdowns is not None:
        cols["forward_max_drawdown_1M"] = drawdowns
    fwd = pd.DataFrame(cols)
    return feats, fwd


@pytest.mark.unit
def test_state_grouping_and_full_stats():
    # 25 Calm rows -> >= full gate (20) with non_overlapping=False.
    n = 25
    feats, fwd = _outcome_inputs(["Calm"] * n, [0.01] * 13 + [-0.02] * 12)
    table = build_volatility_signal_outcome_table(
        feats, fwd, "confirmed_state", "forward_return_1M", non_overlapping=False
    )
    row = table[table["state"] == "Calm"].iloc[0]
    assert row["effective_observations"] == n
    assert row["sample_quality"] == ""           # adequate sample
    assert row["mean_return"] == pytest.approx((13 * 0.01 + 12 * -0.02) / n)
    assert row["hit_rate"] == pytest.approx(13 / n)
    assert row["worst_return"] == pytest.approx(-0.02)
    assert row["best_return"] == pytest.approx(0.01)


@pytest.mark.unit
def test_insufficient_sample_gated_out():
    feats, fwd = _outcome_inputs(["Shock"] * 3, [0.05, -0.01, 0.02])
    table = build_volatility_signal_outcome_table(
        feats, fwd, "confirmed_state", "forward_return_1M", non_overlapping=False
    )
    row = table[table["state"] == "Shock"].iloc[0]
    assert row["effective_observations"] == 3
    assert row["sample_quality"] == "Insufficient sample"
    # No aggregate stats at all.
    for stat in ("mean_return", "median_return", "hit_rate", "worst_return", "best_return"):
        assert row[stat] is None


@pytest.mark.unit
def test_anecdotal_sample_partial_stats():
    # 6 obs -> Anecdotal: count / median / min / max only (no mean / hit_rate / std).
    feats, fwd = _outcome_inputs(["Stress Expansion"] * 6, [0.01, 0.02, -0.01, 0.03, -0.02, 0.0])
    table = build_volatility_signal_outcome_table(
        feats, fwd, "confirmed_state", "forward_return_1M", non_overlapping=False
    )
    row = table[table["state"] == "Stress Expansion"].iloc[0]
    assert row["sample_quality"] == "Anecdotal"
    assert row["median_return"] is not None
    assert row["worst_return"] == pytest.approx(-0.02)
    assert row["best_return"] == pytest.approx(0.03)
    assert row["mean_return"] is None and row["hit_rate"] is None and row["std_return"] is None


@pytest.mark.unit
def test_low_sample_has_descriptive_stats():
    feats, fwd = _outcome_inputs(["Normalisation"] * 15, [0.01] * 15)
    table = build_volatility_signal_outcome_table(
        feats, fwd, "confirmed_state", "forward_return_1M", non_overlapping=False
    )
    row = table[table["state"] == "Normalisation"].iloc[0]
    assert row["sample_quality"] == "Low sample"
    assert row["mean_return"] is not None and row["hit_rate"] is not None


@pytest.mark.unit
def test_unknown_state_is_excluded():
    feats, fwd = _outcome_inputs(["Unknown"] * 25 + ["Calm"] * 25, [0.01] * 50)
    table = build_volatility_signal_outcome_table(
        feats, fwd, "confirmed_state", "forward_return_1M", non_overlapping=False
    )
    assert "Unknown" not in table["state"].tolist()
    assert "Calm" in table["state"].tolist()


@pytest.mark.unit
def test_terminal_missing_forward_returns_lower_effective_count():
    # Last 5 forward returns are NaN (no window); they must not count as observations.
    returns = [0.01] * 20 + [np.nan] * 5
    feats, fwd = _outcome_inputs(["Calm"] * 25, returns)
    table = build_volatility_signal_outcome_table(
        feats, fwd, "confirmed_state", "forward_return_1M", non_overlapping=False
    )
    row = table[table["state"] == "Calm"].iloc[0]
    assert row["effective_observations"] == 20   # NaNs excluded


@pytest.mark.unit
def test_non_overlapping_reduces_effective_count():
    # 30 consecutive Calm days; horizon 1M=21 -> only ceil(30/21)=2 non-overlapping.
    feats, fwd = _outcome_inputs(["Calm"] * 30, [0.01] * 30)
    overlapping = build_volatility_signal_outcome_table(
        feats, fwd, "confirmed_state", "forward_return_1M", non_overlapping=False
    )
    non_overlap = build_volatility_signal_outcome_table(
        feats, fwd, "confirmed_state", "forward_return_1M", non_overlapping=True
    )
    n_over = overlapping[overlapping["state"] == "Calm"].iloc[0]["effective_observations"]
    n_non = non_overlap[non_overlap["state"] == "Calm"].iloc[0]["effective_observations"]
    # Overlapping counts every defined window (last 21 have no future bar -> 9 here),
    # non-overlapping keeps far fewer — the whole point of the default.
    assert n_non < n_over


@pytest.mark.unit
def test_forward_max_drawdown_aggregated_as_worst():
    feats, fwd = _outcome_inputs(
        ["Calm"] * 12, [0.01] * 12, drawdowns=[-0.01, -0.05, -0.02] + [-0.01] * 9
    )
    table = build_volatility_signal_outcome_table(
        feats, fwd, "confirmed_state", "forward_return_1M", non_overlapping=False
    )
    row = table[table["state"] == "Calm"].iloc[0]
    assert row["forward_max_drawdown"] == pytest.approx(-0.05)   # worst across the state


@pytest.mark.unit
def test_no_many_to_many_join_raises_on_duplicate_dates():
    # Duplicate dates on the forward side would multiply rows; the one_to_one
    # validation must raise instead of silently inflating the sample.
    idx = pd.bdate_range("2021-01-04", periods=5)
    feats = pd.DataFrame({"date": idx, "confirmed_state": ["Calm"] * 5})
    dup_dates = list(idx) + [idx[0]]
    fwd = pd.DataFrame({"date": dup_dates, "forward_return_1M": [0.01] * 6})
    with pytest.raises(Exception):
        build_volatility_signal_outcome_table(
            feats, fwd, "confirmed_state", "forward_return_1M", non_overlapping=False
        )


@pytest.mark.unit
def test_empty_state_absent_from_table():
    feats, fwd = _outcome_inputs(["Calm"] * 5, [0.01] * 5)
    table = build_volatility_signal_outcome_table(
        feats, fwd, "confirmed_state", "forward_return_1M", non_overlapping=False
    )
    # Only Calm appears; states with zero occurrences are not rows.
    assert table["state"].tolist() == ["Calm"]


# --------------------------------------------------------------------------- #
# build_state_return_distribution — per-state samples for the box plot
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_distribution_returns_per_state_samples():
    feats, fwd = _outcome_inputs(["Calm"] * 4 + ["Shock"] * 2, [0.01, 0.02, 0.03, 0.04, -0.05, -0.06])
    dist = build_state_return_distribution(
        feats, fwd, "confirmed_state", "forward_return_1M", non_overlapping=False
    )
    assert dist["Calm"] == pytest.approx([0.01, 0.02, 0.03, 0.04])
    assert dist["Shock"] == pytest.approx([-0.05, -0.06])


@pytest.mark.unit
def test_distribution_drops_nan_terminal_windows():
    feats, fwd = _outcome_inputs(["Calm"] * 4, [0.01, np.nan, 0.03, np.nan])
    dist = build_state_return_distribution(
        feats, fwd, "confirmed_state", "forward_return_1M", non_overlapping=False
    )
    assert dist["Calm"] == pytest.approx([0.01, 0.03])   # NaN windows excluded from the box


@pytest.mark.unit
def test_distribution_non_overlapping_thins_samples():
    feats, fwd = _outcome_inputs(["Calm"] * 30, [0.01] * 30)
    full = build_state_return_distribution(
        feats, fwd, "confirmed_state", "forward_return_1M", non_overlapping=False
    )["Calm"]
    thinned = build_state_return_distribution(
        feats, fwd, "confirmed_state", "forward_return_1M", non_overlapping=True
    )["Calm"]
    assert len(thinned) < len(full)


# --------------------------------------------------------------------------- #
# compute_combined_condition_flags — definitions, missing inputs, look-ahead
# --------------------------------------------------------------------------- #


def _features(**columns):
    n = len(next(iter(columns.values())))
    idx = pd.bdate_range("2021-01-04", periods=n)
    return pd.DataFrame({"date": idx, **columns})


@pytest.mark.unit
def test_combined_condition_vol_up_price_directions():
    feats = _features(
        direction=["Rising", "Rising", "Falling", "Rising"],
        asset_return_20d=[-0.05, 0.05, -0.05, 0.0],   # down, up, down(but falling vol), flat
    )
    flags = compute_combined_condition_flags(feats, price_threshold=0.01)
    assert flags[COND_VOL_UP_PRICE_DOWN].tolist() == [True, False, False, False]
    assert flags[COND_VOL_UP_PRICE_UP].tolist() == [False, True, False, False]


@pytest.mark.unit
def test_combined_condition_falling_after_high_is_causal_window():
    # Level reaches High at index 1; "falling after High/Extreme" should hold for a
    # falling day within the lookback after that, not before it.
    feats = _features(
        direction=["Falling", "Falling", "Falling", "Falling"],
        volatility_level=["Normal", "High", "Normal", "Normal"],
    )
    flags = compute_combined_condition_flags(feats, price_threshold=0.01, recent_peak_lookback=3)
    # idx0: no prior High -> False. idx1..3: High within trailing 3 -> True (and falling).
    assert flags[COND_VOL_DOWN_AFTER_HIGH].tolist() == [False, True, True, True]


@pytest.mark.unit
def test_combined_condition_expansion_and_agreement():
    feats = _features(
        term_state=["Expansion", "Balanced", "Expansion", "Unknown"],
        estimator_agreement=["Low", "High", "Low", "Moderate"],
    )
    flags = compute_combined_condition_flags(feats, price_threshold=0.01)
    assert flags[COND_RATIO_EXPANSION].tolist() == [True, False, True, False]
    assert flags[COND_AGREEMENT_LOW].tolist() == [True, False, True, False]


@pytest.mark.unit
def test_combined_condition_cross_asset_only_when_supplied():
    base = _features(direction=["Rising", "Rising"], asset_return_20d=[0.0, 0.0])
    flags_no = compute_combined_condition_flags(base, price_threshold=0.01)
    assert COND_RELATIVE_VOL_EXTREME not in flags_no.columns

    base["relative_pair_percentile"] = [0.95, 0.50]
    flags_yes = compute_combined_condition_flags(base, price_threshold=0.01)
    assert flags_yes[COND_RELATIVE_VOL_EXTREME].tolist() == [True, False]


@pytest.mark.unit
def test_combined_condition_missing_columns_yield_false():
    # No feature columns at all -> every (single-asset) condition is deterministically False.
    feats = _features(other=[1, 2, 3])
    flags = compute_combined_condition_flags(feats, price_threshold=0.01)
    for cond in (COND_VOL_UP_PRICE_DOWN, COND_VOL_UP_PRICE_UP, COND_VOL_DOWN_AFTER_HIGH,
                 COND_RATIO_EXPANSION, COND_AGREEMENT_LOW):
        assert flags[cond].tolist() == [False, False, False]


@pytest.mark.unit
def test_combined_condition_nan_price_return_is_false():
    feats = _features(direction=["Rising", "Rising"], asset_return_20d=[np.nan, -0.05])
    flags = compute_combined_condition_flags(feats, price_threshold=0.01)
    assert flags[COND_VOL_UP_PRICE_DOWN].tolist() == [False, True]   # NaN -> False, not a crash


@pytest.mark.lookahead
def test_combined_condition_flags_are_not_affected_by_future_rows():
    # Truncating rows after t must not change any flag on/before t (all inputs are
    # already-lagged and the only window — the recent-peak max — looks strictly back).
    feats = _features(
        direction=["Falling"] * 10,
        volatility_level=["Normal", "High", "Normal", "Normal", "Normal",
                          "Normal", "Normal", "Normal", "Normal", "Normal"],
        asset_return_20d=[0.0] * 10,
    )
    full = compute_combined_condition_flags(feats, price_threshold=0.01, recent_peak_lookback=3)
    trunc = compute_combined_condition_flags(feats.iloc[:5], price_threshold=0.01, recent_peak_lookback=3)
    pd.testing.assert_series_equal(
        full[COND_VOL_DOWN_AFTER_HIGH].iloc[:5], trunc[COND_VOL_DOWN_AFTER_HIGH], check_names=False
    )


# --------------------------------------------------------------------------- #
# build_combined_condition_outcome_table — per-condition aggregation + gates
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_combined_condition_table_aggregates_per_condition():
    idx = pd.bdate_range("2021-01-04", periods=25)
    # Agreement-Low holds on every day (25 obs -> full stats); expansion never holds.
    conditions = pd.DataFrame({
        "date": idx,
        COND_AGREEMENT_LOW: [True] * 25,
        COND_RATIO_EXPANSION: [False] * 25,
    })
    fwd = pd.DataFrame({"date": idx, "forward_return_1M": [0.01] * 13 + [-0.02] * 12})
    table = build_combined_condition_outcome_table(
        conditions, fwd, "forward_return_1M", non_overlapping=False
    )
    low = table[table["state"] == COND_AGREEMENT_LOW].iloc[0]
    assert low["effective_observations"] == 25
    assert low["sample_quality"] == ""
    assert low["hit_rate"] == pytest.approx(13 / 25)

    # A condition that never holds still appears, gated to Insufficient sample.
    exp = table[table["state"] == COND_RATIO_EXPANSION].iloc[0]
    assert exp["effective_observations"] == 0
    assert exp["sample_quality"] == "Insufficient sample"
    # Gated-out stat is missing (None/NaN once concatenated with float columns);
    # both normalise to null at the API boundary via _clean_float.
    assert pd.isna(exp["mean_return"])


@pytest.mark.unit
def test_combined_condition_table_respects_non_overlapping():
    idx = pd.bdate_range("2021-01-04", periods=30)
    conditions = pd.DataFrame({"date": idx, COND_AGREEMENT_LOW: [True] * 30})
    fwd = pd.DataFrame({"date": idx, "forward_return_1M": [0.01] * 30})
    over = build_combined_condition_outcome_table(
        conditions, fwd, "forward_return_1M", non_overlapping=False
    ).iloc[0]["effective_observations"]
    non = build_combined_condition_outcome_table(
        conditions, fwd, "forward_return_1M", non_overlapping=True
    ).iloc[0]["effective_observations"]
    assert non < over


@pytest.mark.lookahead
def test_combined_condition_table_pairs_each_date_with_its_own_forward_return():
    # Each condition date must be joined to ITS OWN forward return (no shift/leak):
    # forward returns are a strict function of position, the condition is true on a
    # known subset, and the aggregated stats must equal exactly that subset.
    idx = pd.bdate_range("2021-01-04", periods=20)
    flags = [True] * 10 + [False] * 10                 # true on positions 0..9
    cond = pd.DataFrame({"date": idx, COND_AGREEMENT_LOW: flags})
    fwd = pd.DataFrame({"date": idx, "forward_return_1M": [i * 0.01 for i in range(20)]})
    row = build_combined_condition_outcome_table(
        cond, fwd, "forward_return_1M", non_overlapping=False
    ).iloc[0]
    assert row["effective_observations"] == 10         # Low sample -> descriptive stats
    assert row["worst_return"] == pytest.approx(0.0)    # position 0
    assert row["best_return"] == pytest.approx(0.09)    # position 9
    assert row["median_return"] == pytest.approx(0.045)  # median of 0.00..0.09


@pytest.mark.unit
def test_combined_condition_table_no_many_to_many_join_raises():
    # Duplicate forward-side dates must raise (one_to_one), not inflate the sample.
    idx = pd.bdate_range("2021-01-04", periods=5)
    cond = pd.DataFrame({"date": idx, COND_AGREEMENT_LOW: [True] * 5})
    dup = pd.DataFrame({"date": list(idx) + [idx[0]], "forward_return_1M": [0.01] * 6})
    with pytest.raises(Exception):
        build_combined_condition_outcome_table(cond, dup, "forward_return_1M", non_overlapping=False)


@pytest.mark.unit
def test_combined_condition_table_gating_tiers():
    idx = pd.bdate_range("2021-01-04", periods=15)
    # Anecdotal (6 obs): median / worst / best only — no mean / hit_rate / std.
    cond6 = pd.DataFrame({"date": idx, COND_AGREEMENT_LOW: [True] * 6 + [False] * 9})
    fwd6 = pd.DataFrame({"date": idx, "forward_return_1M": [0.01, 0.02, -0.01, 0.03, -0.02, 0.0] + [0.0] * 9})
    row6 = build_combined_condition_outcome_table(
        cond6, fwd6, "forward_return_1M", non_overlapping=False
    ).iloc[0]
    assert row6["sample_quality"] == "Anecdotal"
    assert not pd.isna(row6["median_return"])
    assert pd.isna(row6["mean_return"]) and pd.isna(row6["hit_rate"]) and pd.isna(row6["std_return"])

    # Low sample (15 obs): descriptive stats present.
    cond15 = pd.DataFrame({"date": idx, COND_AGREEMENT_LOW: [True] * 15})
    fwd15 = pd.DataFrame({"date": idx, "forward_return_1M": [0.01] * 15})
    row15 = build_combined_condition_outcome_table(
        cond15, fwd15, "forward_return_1M", non_overlapping=False
    ).iloc[0]
    assert row15["sample_quality"] == "Low sample"
    assert not pd.isna(row15["mean_return"]) and not pd.isna(row15["hit_rate"])


@pytest.mark.unit
def test_combined_condition_table_aggregates_forward_drawdown():
    # The condition path must thread the forward_max_drawdown_* column (worst across the group).
    idx = pd.bdate_range("2021-01-04", periods=12)
    cond = pd.DataFrame({"date": idx, COND_AGREEMENT_LOW: [True] * 12})
    fwd = pd.DataFrame({
        "date": idx, "forward_return_1M": [0.01] * 12,
        "forward_max_drawdown_1M": [-0.01, -0.07, -0.02] + [-0.01] * 9,
    })
    row = build_combined_condition_outcome_table(
        cond, fwd, "forward_return_1M", non_overlapping=False
    ).iloc[0]
    assert row["forward_max_drawdown"] == pytest.approx(-0.07)


@pytest.mark.unit
def test_combined_condition_flags_threshold_inclusivity():
    # Price gates are inclusive: a return exactly at ±threshold is in-band.
    feats = _features(direction=["Rising", "Rising"], asset_return_20d=[-0.01, 0.01])
    flags = compute_combined_condition_flags(feats, price_threshold=0.01)
    assert flags[COND_VOL_UP_PRICE_DOWN].tolist() == [True, False]
    assert flags[COND_VOL_UP_PRICE_UP].tolist() == [False, True]

    # The cross-asset percentile gate is strict (>): exactly at the threshold is False.
    feats2 = _features(other=[1, 2])
    feats2["relative_pair_percentile"] = [0.90, 0.9001]
    flags2 = compute_combined_condition_flags(feats2, price_threshold=0.01, relative_extreme_percentile=0.90)
    assert flags2[COND_RELATIVE_VOL_EXTREME].tolist() == [False, True]
