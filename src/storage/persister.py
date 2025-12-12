import os
import json
import pandas as pd
from config import PROC_DIR

def save_run(etf_df, macro_df, price_signals, macro_signals, decision: dict):
    os.makedirs(PROC_DIR, exist_ok=True)

    # Append decision to positions log
    positions_path = f"{PROC_DIR}/positions.csv"
    row = pd.DataFrame([decision])

    if os.path.exists(positions_path):
        row.to_csv(positions_path, mode="a", header=False, index=False)
    else:
        row.to_csv(positions_path, index=False)

    #can also snapshot raw/signals occasionally
