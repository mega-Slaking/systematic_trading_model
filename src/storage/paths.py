"""Canonical filesystem paths for storage.

Single source of truth for the sqlite database location, imported instead of
hardcoding "data/database.db" per module.
"""

import os
from pathlib import Path

# Defaults to the canonical DB; the STM_DB_PATH env override lets a benchmark or
# test point the whole stack at an isolated copy without touching real results.
DB_PATH = Path(os.environ.get("STM_DB_PATH", "data/database.db"))
