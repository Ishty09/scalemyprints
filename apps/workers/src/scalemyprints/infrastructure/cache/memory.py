"""
In-memory TTL cache.

Phase A default — no Redis/Memcache required. Thread-safe for single-process
async workers. Each entry has an absolute expiry timestamp.

Not suitable for multi-worker production (each worker has its own cache).
When `CACHE_PROVIDER=redis`, the Redis adapter replaces this transparently.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.shared.clock import Clock, SystemClock

logger = get_logger(__name__)


@dataclass(slots=True)
class _Entry:
    value: bytes
    expires_at: float  # monotonic seconds


class MemoryCache:
    """
    LRU+TTL in-memory cache implementing CacheStore.

    Capacity is soft-limited; when exceeded, oldest entries are evicted.
    """

    def __init__(
        self,
        *,
        max_entries: int = 10_000,
        clock: Clock | None = None,
    ) -> None:
        self._max_entries = max_entries
        self._store: dict[str, _Entry] = {}
        self._lock = asyncio.Lock()
        # Clock is kept for injection symmetry; monotonic() is used for TTLs
        # since wall-clock can jump backwards (NTP adjustments).
        self._clock = clock or SystemClock()

    async def get(self, key: str) -> bytes | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at <= monotonic():
                # Expired — evict
                del self._store[key]
                return None
            return entry.value

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        expires_at = monotonic() + ttl_seconds
        async with self._lock:
            self._store[key] = _Entry(value=value, expires_at=expires_at)
            if len(self._store) > self._max_entries:
                self._evict_oldest_unsafe()

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        """Test helper — not part of CacheStore protocol."""
        async with self._lock:
            self._store.clear()

    # Must be called while holding self._lock
    def _evict_oldest_unsafe(self) -> None:
        # Evict the 10% of entries with earliest expiry
        if not self._store:
            return
        count = max(1, len(self._store) // 10)
        oldest = sorted(self._store.items(), key=lambda kv: kv[1].expires_at)[:count]
        for key, _ in oldest:
            del self._store[key]
        logger.debug("memory_cache_evicted", count=count, remaining=len(self._store))

    @property
    def size(self) -> int:
        """Approximate size (may include expired-but-not-yet-evicted entries)."""
        return len(self._store)
