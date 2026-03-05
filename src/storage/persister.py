import os
import pandas as pd
from config import PROC_DIR
from pathlib import Path


def save_run(etf_df, macro_df, price_signals, macro_signals,
             decision: dict, decision_trace: list, regime_trace: list):

    os.makedirs(PROC_DIR, exist_ok=True)

    # Flatten weights if present
    decision_flat = decision.copy()

    if "weights" in decision_flat:
        weights = decision_flat.pop("weights")
        for tkr, w in weights.items():
            decision_flat[f"w_{tkr}"] = float(w)

    # Append decision to positions log
    positions_path = f"{PROC_DIR}/positions.csv"
    row = pd.DataFrame([decision_flat])

    if os.path.exists(positions_path):
        row.to_csv(positions_path, mode="a", header=False, index=False)
    else:
        row.to_csv(positions_path, index=False)

    # Save traces
    trace_path = Path(f"{PROC_DIR}/decision_trace.csv")
    r_trace_path = Path(f"{PROC_DIR}/regime_trace.csv")

    if decision_trace:
        pd.DataFrame(decision_trace).to_csv(
            trace_path,
            mode="a",
            header=not trace_path.exists(),
            index=False
        )

    if regime_trace:
        pd.DataFrame(regime_trace).to_csv(
            r_trace_path,
            mode="a",
            header=not r_trace_path.exists(),
            index=False
        )