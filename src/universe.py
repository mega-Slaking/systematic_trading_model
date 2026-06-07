"""Canonical tradable asset universe.

Single source of truth for the ticker set, imported everywhere instead of
re-declaring `["TLT", "AGG", "SHY"]` per module. Order is fixed
(long-duration -> intermediate -> short/defensive).
"""

UNIVERSE = ("TLT", "AGG", "SHY")
