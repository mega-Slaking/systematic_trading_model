"""Benchmark the C++ covariance kernel vs the pure-Python fallback.

Runs ``run_backtests`` for the 1 / 5 / all strategy sets, once with the compiled
``fast_covariance_cpp`` kernel and once with the pandas fallback, and reports
end-to-end wall time and the isolated covariance-kernel time with C++-vs-Python
speedups.

The kernel is import-gated in ``src/covariance/estimator.py``; this script toggles
it by setting ``estimator.fast_covariance_cpp`` to the real module (``cpp``) or to
``None`` (``py``), holding everything else identical.

**One process, warm surface.** The expensive, covariance-irrelevant volatility
surface (GARCH monthly refit) is built once in an untimed warmup, then reused from
its in-memory cache across every sample — so the timings reflect the per-strategy
backtest + covariance work, not a surface rebuild repeated dozens of times. Each
``run_backtests`` call still builds its own covariance cache, so no covariance
result leaks between the C++ and Python runs. Median of repeated samples is
reported.

Designed to be left running in the background — every sample is streamed to a
timestamped log as it finishes, and a markdown summary is written at the end.

Usage (from the repo root)::

    python benchmarks/benchmark_cpp.py                 # 3 repeats, sizes 1/5/all, both modes
    python benchmarks/benchmark_cpp.py --repeats 1     # quick pass
    python benchmarks/benchmark_cpp.py --sizes 1 5     # skip the slow "all" set

By default the real ``data/database.db`` is copied to an isolated benchmark DB so
persisted results are never overwritten; pass ``--no-db-copy`` to use the live DB.
"""

from __future__ import annotations

import argparse
import os
import shutil
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # make the repo root importable when run as a script

RESULTS_DIR = ROOT / "benchmarks" / "results"
KERNEL_LABELS = ("cov.sample_kernel", "cov.ewma_kernel")

# The 1 / 5 / all split. The 1- and 5-strategy sets deliberately use covariance
# (ewma_cov + sample_cov) so the C++ kernel is actually exercised; "all" is the
# full registry (None == every strategy).
SIZES: dict[str, list[str] | None] = {
    "1": ["baseV1_roll20_ewmacov_lam94_tv05"],
    "5": [
        "baseV1_roll20_ewmacov_lam94_tv03",
        "baseV1_roll20_ewmacov_lam94_tv05",
        "baseV1_roll20_ewmacov_lam97_tv05",
        "baseV1_roll20_covlb20_tv03",
        "baseV1_roll20_covlb20_tv05",
    ],
    "all": None,
}


def _stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _median(xs: list[float]) -> float:
    return statistics.median(xs) if xs else float("nan")


def _write_summary(samples: dict, sizes: list[str], modes: list[str], path: Path) -> str:
    lines = [
        "# C++ covariance speedup",
        "",
        f"_Generated {_stamp()}. Median of repeated runs; one process, warm volatility surface._",
        "",
        "| Strategies | End-to-end C++ (s) | End-to-end Py (s) | E2E speedup | "
        "Cov-kernel C++ (s) | Cov-kernel Py (s) | Kernel speedup | Cov calls |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for size in sizes:
        cells: dict[str, dict] = {}
        for mode in modes:
            runs = samples.get((mode, size), [])
            if not runs:
                continue
            cells[mode] = {
                "e2e": _median([r["seconds"] for r in runs]),
                "kernel": _median([r["kernel_seconds"] for r in runs]),
                "n": runs[0]["n_strategies"],
                "calls": runs[0]["kernel_calls"],
            }
        if "cpp" not in cells or "py" not in cells:
            continue
        cpp, py = cells["cpp"], cells["py"]
        e2e_speedup = py["e2e"] / cpp["e2e"] if cpp["e2e"] else float("nan")
        k_speedup = py["kernel"] / cpp["kernel"] if cpp["kernel"] else float("nan")
        label = f"all ({cpp['n']})" if size == "all" else f"{size} ({cpp['n']})"
        lines.append(
            f"| {label} | {cpp['e2e']:.3f} | {py['e2e']:.3f} | {e2e_speedup:.2f}x | "
            f"{cpp['kernel']:.3f} | {py['kernel']:.3f} | {k_speedup:.2f}x | {cpp['calls']} |"
        )
    lines += [
        "",
        "- **End-to-end** = `run_backtests` wall time with the volatility surface already "
        "warm (so it reflects the per-strategy backtest + covariance, not the one-time surface build).",
        "- **Cov-kernel** = time inside the covariance estimator only — the sole code path the "
        "C++ swap affects — so it is the true kernel speedup, undiluted by the rest of the engine.",
        "- **Cov calls** = covariance computations actually run (cache misses); data-determined, "
        "so equal across both modes.",
        "",
    ]
    text = "\n".join(lines)
    path.write_text(text, encoding="utf-8")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repeats", type=int, default=3, help="samples per (mode, size) (default 3)")
    parser.add_argument("--sizes", nargs="+", default=["1", "5", "all"], choices=["1", "5", "all"])
    parser.add_argument("--modes", nargs="+", default=["cpp", "py"], choices=["cpp", "py"])
    parser.add_argument("--no-db-copy", action="store_true", help="run against the live data/database.db")
    parser.add_argument("--keep-db", action="store_true", help="keep the benchmark DB copy on exit")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = RESULTS_DIR / f"bench_{ts}.log"
    summary_path = RESULTS_DIR / f"summary_{ts}.md"

    # Set env BEFORE importing src so the accumulators record and the DB override
    # (STM_DB_PATH) is picked up at import by the storage layer.
    os.environ["BENCH_TIMING"] = "1"
    bench_db: Path | None = None
    if not args.no_db_copy:
        source_db = ROOT / "data" / "database.db"
        if not source_db.exists():
            print(f"ERROR: {source_db} not found; populate it or pass --no-db-copy", file=sys.stderr)
            return 1
        bench_db = RESULTS_DIR / f"bench_{ts}.db"
        shutil.copy2(source_db, bench_db)
        os.environ["STM_DB_PATH"] = str(bench_db)

    from src.utils.timing import timed, accumulated, reset_accumulators
    import src.covariance.estimator as cov_est
    from run_backtest import run_backtests

    cpp_module = cov_est.fast_covariance_cpp
    if cpp_module is None:
        print(
            "ERROR: fast_covariance_cpp is not importable; cannot benchmark the C++ "
            "path (would measure python-vs-python). Build the extension first.",
            file=sys.stderr,
        )
        return 2

    fh = log_path.open("w", encoding="utf-8")

    def log(line: str) -> None:
        print(line, flush=True)
        fh.write(line + "\n")
        fh.flush()

    try:
        total = args.repeats * len(args.sizes) * len(args.modes)
        log(f"[{_stamp()}] benchmark start: repeats={args.repeats} sizes={args.sizes} "
            f"modes={args.modes} samples={total}")
        log(f"[{_stamp()}] db={'live data/database.db' if args.no_db_copy else bench_db}")

        # One-time, untimed warmup so the volatility surface is cached for every
        # subsequent run (it is identical and covariance-irrelevant).
        log(f"[{_stamp()}] warmup: building volatility surface (one-time, untimed)...")
        w0 = time.perf_counter()
        run_backtests(SIZES["1"])
        log(f"[{_stamp()}] warmup done in {time.perf_counter() - w0:.1f}s")

        started = time.perf_counter()
        samples: dict[tuple[str, str], list[dict]] = {}
        done = 0
        for size in args.sizes:
            for mode in args.modes:
                for _ in range(args.repeats):
                    cov_est.fast_covariance_cpp = cpp_module if mode == "cpp" else None
                    reset_accumulators()
                    run = timed(f"run_backtests[{mode}/{size}]")(run_backtests)
                    t0 = time.perf_counter()
                    written = run(SIZES[size])
                    elapsed = time.perf_counter() - t0

                    acc = accumulated()
                    kernel_seconds = sum(acc.get(k, (0.0, 0))[0] for k in KERNEL_LABELS)
                    kernel_calls = sum(acc.get(k, (0.0, 0))[1] for k in KERNEL_LABELS)
                    samples.setdefault((mode, size), []).append({
                        "seconds": elapsed,
                        "kernel_seconds": kernel_seconds,
                        "kernel_calls": kernel_calls,
                        "n_strategies": len(written),
                    })
                    done += 1
                    log(f"[{_stamp()}] [{done}/{total}] mode={mode} size={size} "
                        f"end_to_end={elapsed:.3f}s kernel={kernel_seconds:.3f}s "
                        f"(cov_calls={kernel_calls})")

        cov_est.fast_covariance_cpp = cpp_module  # restore
        log(f"[{_stamp()}] all samples done in {time.perf_counter() - started:.1f}s")

        summary = _write_summary(samples, args.sizes, args.modes, summary_path)
        log("\n" + summary)
        log(f"[{_stamp()}] log:     {log_path}")
        log(f"[{_stamp()}] summary: {summary_path}")
    finally:
        fh.close()
        if bench_db is not None and not args.keep_db:
            bench_db.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
