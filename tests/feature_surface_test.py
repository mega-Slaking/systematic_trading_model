import pandas as pd

from src.storage.db_reader import get_etf_history
from src.volatility.feature_surface import build_volatility_feature_surface
from src.volatility.models import (
    VolatilityFeatureConfig,
    VolatilityConfig,
    VolatilityRequest,
)
from src.volatility.estimator import estimate_volatility
from src.context.backtest import BacktestContext


TOLERANCE = 1e-9

# Surface config under test. The point estimator can reproduce each of these
# four base methods, so all of them can be cross-validated (not just eyeballed).
SURFACE_CONFIG = VolatilityFeatureConfig(
    rolling_windows=(20, 60),
    ewma_lambdas=(0.94, 0.97),
    include_garch=False,
    min_history=20,
)

# Maps each surface column to the point-estimator config that should reproduce it.
METHOD_REFERENCES = {
    "rolling_20": VolatilityConfig(method="rolling_std", lookback_days=20, min_history=20),
    "rolling_60": VolatilityConfig(method="rolling_std", lookback_days=60, min_history=20),
    "ewma_94": VolatilityConfig(method="ewma", ewma_lambda=0.94, min_history=20),
    "ewma_97": VolatilityConfig(method="ewma", ewma_lambda=0.97, min_history=20),
}

BASE_COLUMNS = list(METHOD_REFERENCES.keys())


def _point_vols(etf_history, as_of_date, tickers, config) -> dict[str, float]:
    estimate = estimate_volatility(
        request=VolatilityRequest(
            etf_history=etf_history,
            as_of_date=as_of_date,
            tickers=tickers,
        ),
        config=config,
    )
    return estimate.vols


def _pick_random_dates(surface_values, tickers, n, seed, columns=None) -> list[pd.Timestamp]:
    """Random dates where every required feature is populated for all tickers."""
    complete = surface_values.dropna(subset=columns or BASE_COLUMNS)
    per_date = complete.groupby("date")["ticker"].nunique()
    good_dates = per_date[per_date >= len(tickers)].index

    sampled = (
        pd.Series(list(good_dates))
        .sample(n=min(n, len(good_dates)), random_state=seed)
        .sort_values()
    )
    return [pd.Timestamp(d) for d in sampled]


def test_all_methods_across_random_dates(etf_history, tickers, n=25, seed=42) -> bool:
    surface = build_volatility_feature_surface(
        etf_history=etf_history,
        tickers=tickers,
        config=SURFACE_CONFIG,
        lag_features_days=1,
    )

    dates = _pick_random_dates(surface.values, tickers, n=n, seed=seed)

    print("\n" + "#" * 78)
    print(f"# VOLATILITY FEATURE SURFACE - {len(dates)} random dates (seed={seed})")
    print("#" * 78)

    pd.set_option("display.float_format", lambda v: f"{v:>12.6f}")
    pd.set_option("display.width", 200)

    method_failures = 0
    ratio_failures = 0
    checks = 0

    for as_of_date in dates:
        snapshot = surface.get_snapshot(as_of_date)

        # --- 1. Print every column for this date -------------------------------
        print(f"\n----- {as_of_date.date()} -----")
        print(snapshot.drop(columns=["date"]).to_string(index=False))

        # --- 2. Cross-validate the four base methods vs the point estimator -----
        for column, ref_config in METHOD_REFERENCES.items():
            surface_vols = {
                row["ticker"]: float(row[column])
                for _, row in snapshot.iterrows()
                if pd.notna(row[column])
            }
            point_vols = _point_vols(etf_history, as_of_date, tickers, ref_config)

            for ticker in tickers:
                s = surface_vols.get(ticker)
                p = point_vols.get(ticker)
                if s is None or p is None:
                    continue
                checks += 1
                if abs(s - p) > TOLERANCE:
                    method_failures += 1
                    print(
                        f"   MISMATCH {column} {ticker}: "
                        f"surface={s:.10f} point={p:.10f} diff={abs(s - p):.2e}"
                    )

        # --- 3. Self-check the comparison ratios (ewma / rolling_20) ------------
        for _, row in snapshot.iterrows():
            for ewma_col in ("ewma_94", "ewma_97"):
                ratio_col = f"{ewma_col}_to_rolling_20"
                if ratio_col not in snapshot.columns:
                    continue
                if pd.isna(row[ratio_col]) or pd.isna(row["rolling_20"]):
                    continue
                expected = row[ewma_col] / row["rolling_20"]
                if abs(expected - row[ratio_col]) > TOLERANCE:
                    ratio_failures += 1
                    print(
                        f"   RATIO MISMATCH {ratio_col} {row['ticker']}: "
                        f"expected={expected:.10f} got={row[ratio_col]:.10f}"
                    )

    print("\n" + "=" * 78)
    print(f"Base-method checks (vs point estimator): {checks} compared, {method_failures} mismatches")
    print(f"Comparison-ratio self-checks: {ratio_failures} mismatches")
    ok = method_failures == 0 and ratio_failures == 0
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")
    print("=" * 78)
    return ok


def test_context_can_retrieve_snapshot(etf_history, tickers, seed=42) -> bool:
    """Prove the backtest plumbing: surface attached to context, snapshot retrievable per date."""
    surface = build_volatility_feature_surface(
        etf_history=etf_history,
        tickers=tickers,
        config=SURFACE_CONFIG,
        lag_features_days=1,
    )
    as_of_date = _pick_random_dates(surface.values, tickers, n=1, seed=seed)[0]

    print(f"\n=== CONTEXT RETRIEVAL @ {as_of_date.date()} ===")

    context = BacktestContext(etf_history, macro_history=None, portfolio=None)
    context.volatility_feature_surface = surface
    context.set_date(as_of_date)

    features = context.volatility_snapshot_to_dict(context.get_volatility_snapshot())

    all_ok = True
    for ticker in tickers:
        present = features.get(ticker, {})
        ok = all(present.get(c) is not None for c in BASE_COLUMNS)
        all_ok = all_ok and ok
        flag = "" if ok else "  <-- MISSING"
        print(f"{ticker:<6} {present}{flag}")

    print(f"RESULT: {'PASS' if all_ok else 'FAIL'}")
    return all_ok


def test_garch_across_random_dates(
    etf_history, tickers, n=25, seed=42, history=240, lookback=120
) -> bool:
    """GARCH across 25 random dates, cross-validated against the point estimator.

    The point estimator computes vol using ONLY returns with date < t
    (src/volatility/estimator.py: `df[df["date"] < as_of_date]`). If the surface
    snapshot at t matches it, the surface is provably using no data on/after t -
    i.e. no lookahead bias - while also confirming GARCH functionality per date.

    Daily refit makes the point estimator an exact reference on every date (not
    just refit days); history is trimmed because daily refit fits once per date.
    """
    df = etf_history.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df = df[df["ticker"].isin(tickers)]

    keep_dates = sorted(df["date"].unique())[-history:]
    df = df[df["date"].isin(keep_dates)]

    surface = build_volatility_feature_surface(
        etf_history=df,
        tickers=tickers,
        config=VolatilityFeatureConfig(
            rolling_windows=(),
            ewma_lambdas=(),
            include_garch=True,
            garch_refit_frequency="daily",
            garch_lookback_days=lookback,
            min_history=20,
        ),
        use_cache=False,
        lag_features_days=1,
    )

    dates = _pick_random_dates(surface.values, tickers, n=n, seed=seed, columns=["garch"])

    print("\n" + "#" * 78)
    print(
        f"# GARCH(1,1) - {len(dates)} random dates, daily refit, "
        f"vs point estimator (returns < t)"
    )
    print("#" * 78)
    print(f"{'date':<12}{'ticker':<7}{'surface':>14}{'point(<t)':>14}{'abs_diff':>12}")

    ref_config = VolatilityConfig(
        method="garch", garch_lookback_days=lookback, min_history=20
    )
    failures = 0
    checks = 0

    for as_of_date in dates:
        snapshot = surface.get_snapshot(as_of_date)
        surface_vols = {
            row["ticker"]: float(row["garch"])
            for _, row in snapshot.iterrows()
            if pd.notna(row["garch"])
        }
        point_vols = _point_vols(df, as_of_date, tickers, ref_config)

        for ticker in tickers:
            s = surface_vols.get(ticker)
            p = point_vols.get(ticker)
            if s is None or p is None:
                continue
            checks += 1
            diff = abs(s - p)
            flag = "" if diff <= 1e-6 else "  <-- MISMATCH"
            print(
                f"{str(as_of_date.date()):<12}{ticker:<7}"
                f"{s:>14.8f}{p:>14.8f}{diff:>12.2e}{flag}"
            )
            if diff > 1e-6:
                failures += 1

    print("=" * 78)
    print(f"GARCH checks: {checks} compared, {failures} mismatches")
    ok = failures == 0 and checks > 0
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    etf_history = get_etf_history()
    tickers = ["TLT", "AGG", "SHY"]

    results = [
        test_all_methods_across_random_dates(etf_history, tickers, n=25, seed=42),
        test_context_can_retrieve_snapshot(etf_history, tickers, seed=42),
        test_garch_across_random_dates(etf_history, tickers, n=25, seed=42),
    ]

    print("\n" + "=" * 40)
    print(f"OVERALL: {'ALL PASS' if all(results) else 'SOME FAILED'}")
    print("=" * 40)


if __name__ == "__main__":
    main()
