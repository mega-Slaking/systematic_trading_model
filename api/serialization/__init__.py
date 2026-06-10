"""Serialization boundary: DataFrame / Series / dataclass -> JSON-safe structures.

The whole core speaks DataFrame / Series / dataclass / dict (spec §2.3). This
package centralizes the conversion so every endpoint is consistent. The three
classic hazards -- dates, NaN/Inf, and float precision -- are handled in exactly
one place (``frames.py``); see the module docstring there.
"""

from api.serialization.frames import (
    df_to_series,
    df_to_table,
    nan_to_none,
    sanitize_obj,
    series_to_points,
    to_iso,
)

__all__ = [
    "nan_to_none",
    "sanitize_obj",
    "to_iso",
    "series_to_points",
    "df_to_series",
    "df_to_table",
]
