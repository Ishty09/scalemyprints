"""
In-memory niche cache.

Same TTL pattern as trademark cache. Process-local, lost on restart.
For Phase B, swap to Redis with same interface.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass(slots=True)
class _Entry:
    value: dict
    expires_at: float


class NicheMemoryCache:
    """
    Simple async-safe in-memory cache implementing NicheCacheStore.

    Eviction is lazy (on read) — entries past expiry return None.
    """

    def __init__(self, *, max_entries: int = 5_000) -> None:
        self._store: dict[str, _Entry] = {}
        self._lock = asyncio.Lock()
        self._max_entries = max_entries

    async def get(self, key: str) -> dict | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.monotonic() >= entry.expires_at:
                self._store.pop(key, None)
                return None
            return entry.value

    async def set(self, key: str, value: dict, ttl_seconds: int) -> None:
        async with self._lock:
            if len(self._store) >= self._max_entries:
                # crude FIFO eviction — pop the first key
                oldest = next(iter(self._store))
                self._store.pop(oldest, None)
            self._store[key] = _Entry(
                value=value,
                expires_at=time.monotonic() + ttl_seconds,
            )

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()
