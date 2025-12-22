import pandas as pd
from pathlib import Path

def save_backtest_results(results, output_path="output/backtests/backtest_results.csv"):
    if not results:
        print("No backtest results to save.")
        return

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(results)
    df.to_csv(output_path, index=False)

    print(f"Backtest results saved to {output_path}")
