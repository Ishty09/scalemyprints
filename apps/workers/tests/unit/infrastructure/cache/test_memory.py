"""Tests for MemoryCache."""

from __future__ import annotations

import asyncio

import pytest

from scalemyprints.infrastructure.cache.memory import MemoryCache


@pytest.fixture
def cache() -> MemoryCache:
    return MemoryCache(max_entries=100)


class TestMemoryCacheBasic:
    async def test_get_missing_returns_none(self, cache: MemoryCache) -> None:
        assert await cache.get("missing") is None

    async def test_set_then_get_round_trips_bytes(self, cache: MemoryCache) -> None:
        await cache.set("key", b"value", ttl_seconds=60)
        assert await cache.get("key") == b"value"

    async def test_delete_removes_entry(self, cache: MemoryCache) -> None:
        await cache.set("key", b"value", ttl_seconds=60)
        await cache.delete("key")
        assert await cache.get("key") is None

    async def test_delete_missing_is_noop(self, cache: MemoryCache) -> None:
        # Should not raise
        await cache.delete("never-existed")


class TestMemoryCacheTTL:
    async def test_zero_ttl_not_cached(self, cache: MemoryCache) -> None:
        await cache.set("key", b"value", ttl_seconds=0)
        assert await cache.get("key") is None

    async def test_negative_ttl_not_cached(self, cache: MemoryCache) -> None:
        await cache.set("key", b"value", ttl_seconds=-5)
        assert await cache.get("key") is None

    async def test_entry_expires(self, cache: MemoryCache) -> None:
        await cache.set("key", b"value", ttl_seconds=1)
        # Not expired yet
        assert await cache.get("key") == b"value"
        # Wait past TTL
        await asyncio.sleep(1.05)
        assert await cache.get("key") is None


class TestMemoryCacheEviction:
    async def test_evicts_when_over_capacity(self) -> None:
        cache = MemoryCache(max_entries=10)
        # Fill past capacity
        for i in range(15):
            await cache.set(f"key{i}", b"v", ttl_seconds=60)
        # Some were evicted
        assert cache.size < 15


class TestMemoryCacheConcurrency:
    async def test_concurrent_sets_no_corruption(self, cache: MemoryCache) -> None:
        """Hammer the cache from 50 concurrent tasks — no corruption."""
        async def writer(i: int) -> None:
            for _ in range(10):
                await cache.set(f"key{i}", f"value{i}".encode(), ttl_seconds=60)

        await asyncio.gather(*(writer(i) for i in range(50)))

        # All 50 keys should have their final value
        for i in range(50):
            assert await cache.get(f"key{i}") == f"value{i}".encode()
