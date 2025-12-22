import pandas as pd

class PriceNormalizer:

    @staticmethod
    def normalize_prices(etf_df: pd.DataFrame) -> dict[str, float] | None:
        prices = {}

        for ticker, df_t in etf_df.groupby("ticker"):
            df_t = df_t.sort_values("date")

            valid = df_t["close"].dropna()
            if valid.empty:
                return None  # ticker not live yet

            prices[ticker] = float(valid.iloc[-1])

        return prices
