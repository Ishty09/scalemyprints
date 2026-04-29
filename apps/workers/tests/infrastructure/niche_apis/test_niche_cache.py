"""Tests for in-memory niche cache."""

from __future__ import annotations

import asyncio

import pytest

from scalemyprints.infrastructure.cache.niche_memory import NicheMemoryCache


class TestNicheMemoryCache:
    @pytest.mark.asyncio
    async def test_set_and_get(self):
        cache = NicheMemoryCache()
        await cache.set("key1", {"value": 42}, ttl_seconds=60)
        result = await cache.get("key1")
        assert result == {"value": 42}

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self):
        cache = NicheMemoryCache()
        result = await cache.get("never-set")
        assert result is None

    @pytest.mark.asyncio
    async def test_ttl_expiration(self):
        cache = NicheMemoryCache()
        # 0 second TTL = immediately expired
        await cache.set("expiring", {"x": 1}, ttl_seconds=0)
        await asyncio.sleep(0.01)
        result = await cache.get("expiring")
        assert result is None

    @pytest.mark.asyncio
    async def test_overwrite_existing_key(self):
        cache = NicheMemoryCache()
        await cache.set("k", {"v": 1}, 60)
        await cache.set("k", {"v": 2}, 60)
        assert (await cache.get("k")) == {"v": 2}

    @pytest.mark.asyncio
    async def test_clear_removes_all(self):
        cache = NicheMemoryCache()
        await cache.set("a", {"x": 1}, 60)
        await cache.set("b", {"x": 2}, 60)
        await cache.clear()
        assert (await cache.get("a")) is None
        assert (await cache.get("b")) is None

    @pytest.mark.asyncio
    async def test_eviction_at_max_entries(self):
        cache = NicheMemoryCache(max_entries=3)
        await cache.set("a", {"v": 1}, 600)
        await cache.set("b", {"v": 2}, 600)
        await cache.set("c", {"v": 3}, 600)
        # Adding 4th should evict oldest ("a")
        await cache.set("d", {"v": 4}, 600)
        # The newly added entry must be readable
        assert (await cache.get("d")) is not None
        # The oldest ("a") was evicted; b and c should survive
        remaining = 0
        for k in ("a", "b", "c"):
            if (await cache.get(k)) is not None:
                remaining += 1
        assert remaining == 2

    @pytest.mark.asyncio
    async def test_concurrent_writes_no_corruption(self):
        cache = NicheMemoryCache()

        async def writer(idx: int):
            for i in range(50):
                await cache.set(f"k-{idx}", {"i": i}, 60)

        await asyncio.gather(*(writer(i) for i in range(5)))

        # All keys should be readable, last write per key should win
        for idx in range(5):
            value = await cache.get(f"k-{idx}")
            assert value == {"i": 49}
