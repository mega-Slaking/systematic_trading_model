"""Canonical filesystem paths for storage.

Single source of truth for the sqlite database location, imported instead of
hardcoding "data/database.db" per module.
"""

from pathlib import Path

DB_PATH = Path("data/database.db")
