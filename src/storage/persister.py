import sqlite3

from config import DATA_DIR
from src.decision.models import Decision
from src.storage.db_writer import insert_decision_trace, insert_regime_trace

def save_run(
    etf_df,
    macro_df,
    price_signals,
    macro_signals,
    decision: Decision,
    decision_trace: list,
    regime_trace: list,
):

    conn = sqlite3.connect(f"{DATA_DIR}/database.db")

    try:
        if decision_trace:
            insert_decision_trace(conn, decision_trace)

        if regime_trace:
            insert_regime_trace(conn, regime_trace)

        conn.commit()
    finally:
        conn.close()