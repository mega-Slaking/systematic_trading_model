"""Dataclass -> JSON-safe dict helpers (spec §6).

A frozen dataclass of plain scalars (e.g. ``TearsheetMetrics``) serializes via
``dataclasses.asdict`` followed by the NaN/Inf sanitizer. The bespoke walker that
expands ``TearsheetResult``'s DataFrame fields into ``NamedSeries`` / ``TableModel``
lands with the tearsheet endpoint (Phase 3); this Phase-0 module provides only the
scalar path so the layout and the sanitizer contract exist from the start.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from api.serialization.frames import sanitize_obj


def dataclass_to_dict(obj: Any) -> dict:
    """``dataclasses.asdict`` then recursively NaN/Inf -> null sanitize.

    Raises ``TypeError`` (via ``asdict``) if ``obj`` is not a dataclass instance.
    """
    return sanitize_obj(dataclasses.asdict(obj))
