"""Phase 3 — unified volatility-state tests.

Covers every state, every precedence branch + the listed edge cases, confirmation
persistence (including single-day Extreme not reaching the confirmed series), and
explanation determinism.
"""

import pandas as pd
import pytest

from src.volatility.states import (
    VolatilityStateConfig,
    build_latest_volatility_state_table,
    classify_volatility_state,
    compute_confirmed_state_series,
    explain_volatility_state,
)

CFG = VolatilityStateConfig()


def _state(percentile, direction, term_ratio):
    return classify_volatility_state(percentile, direction, term_ratio, CFG)


# --------------------------------------------------------------------------- #
# every state + precedence branches
# --------------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize(
    "percentile, direction, term_ratio, expected",
    [
        (0.30, "Stable", 1.00, "Calm"),                    # Low/Normal, no expansion
        (0.30, "Rising", 1.00, "Early Expansion"),         # Low/Normal, expansion_score 1 (direction)
        (0.30, "Stable", 1.20, "Early Expansion"),         # Low/Normal, expansion_score 1 (ratio)
        (0.85, "Rising", 1.20, "Stress Expansion"),        # High, expansion_score 2
        (0.85, "Falling", 0.80, "Normalisation"),          # High, contraction_score 2
        (0.85, "Stable", 1.00, "Persistent Stress"),       # High, neither strong
        (0.97, "Stable", 1.00, "Shock"),                   # Extreme dominates
        (0.97, "Rising", 1.20, "Shock"),                   # Extreme still wins over expansion
        (None, "Rising", 1.20, "Unknown"),                 # percentile missing
        (0.85, "Unknown", 1.20, "Unknown"),                # direction missing
        (0.85, "Rising", None, "Unknown"),                 # term_ratio missing
    ],
)
def test_every_state(percentile, direction, term_ratio, expected):
    assert _state(percentile, direction, term_ratio) == expected


@pytest.mark.unit
def test_conflicting_direction_and_ratio_is_persistent_stress():
    # Rising direction but Contraction ratio at High: scores 1/1, neither strong.
    assert _state(0.85, "Rising", 0.80) == "Persistent Stress"
    # Symmetric: Falling direction but Expansion ratio.
    assert _state(0.85, "Falling", 1.20) == "Persistent Stress"


@pytest.mark.unit
def test_boundary_percentiles_feed_deterministically():
    # 0.95 is the Extreme edge (upper-band rule) -> Shock.
    assert _state(0.95, "Stable", 1.00) == "Shock"
    # 0.80 is the High edge -> stressed band, not calm.
    assert _state(0.80, "Stable", 1.00) == "Persistent Stress"
    # Just below 0.80 is Elevated... still stressed; just below 0.60 is Normal -> Calm.
    assert _state(0.599, "Stable", 1.00) == "Calm"


@pytest.mark.unit
def test_elevated_falling_to_normal_while_rising_is_early_expansion():
    # Level has dropped to Normal but direction is still Rising -> rule 6.
    assert _state(0.30, "Rising", 1.00) == "Early Expansion"


# --------------------------------------------------------------------------- #
# confirmed-state debounce
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_confirmation_flips_only_after_n_days():
    inst = pd.Series(["A", "A", "A", "B", "B", "B"])
    confirmed = compute_confirmed_state_series(inst, confirmation_days=3)
    # Seeded Unknown; A confirms on its 3rd day; B confirms on its 3rd day.
    assert confirmed.tolist() == ["Unknown", "Unknown", "A", "A", "A", "B"]


@pytest.mark.unit
def test_single_day_extreme_never_confirms():
    inst = pd.Series(["Persistent Stress"] * 3 + ["Shock"] + ["Persistent Stress"] * 3)
    confirmed = compute_confirmed_state_series(inst, confirmation_days=3)
    # The lone Shock day holds the prior confirmed value, never becomes Shock.
    assert "Shock" not in confirmed.tolist()
    assert confirmed.iloc[3] == "Persistent Stress"


@pytest.mark.unit
def test_confirmation_one_day_equals_instantaneous():
    inst = pd.Series(["A", "B", "A", "C"])
    confirmed = compute_confirmed_state_series(inst, confirmation_days=1)
    assert confirmed.tolist() == inst.tolist()


# --------------------------------------------------------------------------- #
# explanation determinism
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_explanation_is_deterministic_and_uses_inputs():
    row = pd.Series(
        {
            "confirmed_state": "Persistent Stress",
            "volatility_level": "High",
            "percentile_ordinal": 88,
            "direction": "Stable",
            "term_state": "Balanced",
            "term_ratio": 1.01,
        }
    )
    first = explain_volatility_state(row)
    assert first == explain_volatility_state(row)          # deterministic
    assert "High volatility" in first and "88th percentile" in first and "1.01" in first


@pytest.mark.unit
def test_explanation_unknown_state_is_safe():
    row = pd.Series({"confirmed_state": "Unknown", "volatility_level": "Insufficient history"})
    assert "Insufficient history" in explain_volatility_state(row)


# --------------------------------------------------------------------------- #
# config version + all-asset table
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_config_version_changes_with_thresholds():
    base = VolatilityStateConfig().version()
    assert VolatilityStateConfig().version() == base               # stable across instances
    assert VolatilityStateConfig(high_percentile=0.96).version() != base


def _features(ticker, percentiles, directions, ratios, start="2021-01-01"):
    dates = pd.bdate_range(start, periods=len(percentiles))
    return pd.DataFrame(
        {
            "date": dates,
            "ticker": ticker,
            "percentile": percentiles,
            "direction": directions,
            "term_ratio": ratios,
            "current_volatility": [0.1] * len(percentiles),
            "percentile_ordinal": [int(p * 100) for p in percentiles],
            "volatility_level": ["High"] * len(percentiles),
            "change_20d": [0.0] * len(percentiles),
            "term_state": ["Balanced"] * len(percentiles),
        }
    )


@pytest.mark.unit
def test_build_latest_state_table_multi_asset():
    # TLT sits at Persistent Stress for >=3 days (confirms); AGG stays calm.
    tlt = _features("TLT", [0.85] * 5, ["Stable"] * 5, [1.0] * 5)
    agg = _features("AGG", [0.30] * 5, ["Stable"] * 5, [1.0] * 5)
    agg["volatility_level"] = "Normal"
    feats = pd.concat([tlt, agg], ignore_index=True)

    table = build_latest_volatility_state_table(feats, feats["date"].max(), CFG)
    assert set(table["ticker"]) == {"TLT", "AGG"}
    by = table.set_index("ticker")
    assert by.loc["TLT", "confirmed_state"] == "Persistent Stress"
    assert by.loc["AGG", "confirmed_state"] == "Calm"
    # Every row carries an instantaneous state and a deterministic explanation.
    assert {"instantaneous_state", "confirmed_state", "state_explanation"} <= set(table.columns)
    assert table["state_explanation"].notna().all()


@pytest.mark.unit
def test_build_latest_state_table_respects_as_of():
    # Before 3 confirming days have elapsed, the confirmed state is still Unknown.
    tlt = _features("TLT", [0.85] * 5, ["Stable"] * 5, [1.0] * 5)
    early = build_latest_volatility_state_table(tlt, tlt["date"].iloc[1], CFG)
    assert early.loc[0, "confirmed_state"] == "Unknown"
