"""Tiny in-process TTL cache (spec §5.2).

Replicates what Streamlit got "for free" from ``@st.cache_data``: a small
in-process dict keyed on call params with a per-entry TTL, plus an explicit
flush hook (the optional backtest-job worker / ``POST /cache/flush`` calls it).

Phase 0 defines the primitive only; the read and tearsheet endpoints wire it in
their phases. No external store (Redis/Celery) -- single-analyst, single-node.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Hashable


class TTLCache:
    """A minimal thread-safe TTL cache.

    Not an LRU (no size bound) -- the analytics key space is tiny (a handful of
    scenarios x params). If unbounded growth ever matters, swap the dict for an
    ``OrderedDict`` with eviction behind this same interface.
    """

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = float(ttl_seconds)
        self._store: dict[Hashable, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> Any | None:
        """Return the cached value for ``key`` if present and unexpired, else ``None``."""
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if now >= expires_at:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: Hashable, value: Any) -> None:
        """Cache ``value`` under ``key`` for the configured TTL."""
        with self._lock:
            self._store[key] = (time.monotonic() + self._ttl, value)

    def flush(self) -> None:
        """Drop all entries (cache invalidation on backtest completion, §5.2)."""
        with self._lock:
            self._store.clear()
