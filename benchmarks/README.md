# Benchmarks

## C++ covariance kernel vs pure-Python

Measures the effect of the compiled `fast_covariance_cpp` extension (added in
V1.8.3) by running the backtest engine **with** and **without** it and comparing
runtimes. The kernel is import-gated in
[`src/covariance/estimator.py`](../src/covariance/estimator.py) — the benchmark
toggles it by setting `estimator.fast_covariance_cpp = None` (the pandas
fallback), holding *everything else* constant. This isolates the kernel far more
cleanly than diffing the v1.8.2 and v1.8.3 commits (which also predate the
returns-view + covariance cache added in V1.8.4).

### Results (2026-06-28, uvicorn off)

| Strategies | E2E C++ (s) | E2E Py (s) | E2E speedup | Kernel C++ (s) | Kernel Py (s) | Kernel speedup | Cov calls |
|---|---|---|---|---|---|---|---|
| 1 | 421.0 | 2198.2 | **5.22×** | 4.29 | 1759.3 | **410×** | 4,144 |
| 5 | 2431.9 | 5709.3 | **2.35×** | 15.17 | 3508.8 | **231×** | 12,432 |
| all (18) | 7848.6 | 11093.2 | **1.41×** | 12.91 | 3512.9 | **272×** | 12,432 |

The **kernel speedup (~230–410×)** is the direct measure of the C++ code — pandas
ewma covariance ≈ 400 ms/call vs C++ ≈ 1 ms/call. The **end-to-end speedup shrinks
with strategy count** because covariance is cached across strategies: note `cov_calls`
is identical (12,432) for 5 and 18 strategies — all 18 share only 3 distinct covariance
configs — so covariance is a smaller fraction of total runtime on larger runs.

### Run it

```bash
python benchmarks/benchmark_cpp.py                 # 3 repeats, sizes 1/5/all, both modes
python benchmarks/benchmark_cpp.py --repeats 1     # quick pass
python benchmarks/benchmark_cpp.py --sizes 1 5     # skip the slow "all" set
```

Leave it running in the background; each sample is streamed to a timestamped log
as it finishes:

```bash
# Git Bash
nohup python benchmarks/benchmark_cpp.py > /dev/null 2>&1 &
# PowerShell
Start-Process python -ArgumentList "benchmarks/benchmark_cpp.py" -WindowStyle Hidden
```

### Output

Written to `benchmarks/results/` (gitignored):

- `bench_<timestamp>.log` — every sample with ISO-timestamped `START`/`END` lines.
- `summary_<timestamp>.md` — the speedup table (end-to-end **and** isolated
  covariance-kernel, with C++-vs-Python ratios).

### Notes

- **One process, warm surface.** The GARCH volatility surface (covariance-irrelevant
  and identical every run) is built once in an untimed warmup and reused from cache,
  so timings reflect the per-strategy backtest + covariance — not a surface rebuild
  repeated dozens of times. Each `run_backtests` still builds its own covariance
  cache, so no covariance result leaks between the C++ and Python runs.
- **Your real DB is safe**: by default `data/database.db` is copied to an isolated
  benchmark DB (via the `STM_DB_PATH` override) and the copy is deleted on exit.
  Pass `--no-db-copy` to run against the live DB, `--keep-db` to retain the copy.
- The **`cpp` mode fails fast** if the compiled extension isn't importable, so you
  never accidentally measure Python-vs-Python.
- Instrumentation lives in [`src/utils/timing.py`](../src/utils/timing.py):
  `@timed` (per-call START/END log) and `@accumulate` (summed kernel time, active
  only when `BENCH_TIMING` is set — production pays one env lookup per call).
