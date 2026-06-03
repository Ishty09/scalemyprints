"""Tests for the in-memory embedding store."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scalemyprints.domain.spy.models import DesignEmbedding
from scalemyprints.infrastructure.image_search.memory_store import MemoryEmbeddingStore


def _embedding(sha: str, phash: int, vec: list[float]) -> DesignEmbedding:
    return DesignEmbedding(
        sha256=sha,
        phash=phash,
        clip_embedding=vec,
        width=10,
        height=10,
        bytes_size=100,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_upsert_and_link() -> None:
    store = MemoryEmbeddingStore()
    vec = [0.1] * 512
    await store.upsert(_embedding("a" * 64, 1, vec))
    await store.link_listing("a" * 64, "listing-1")
    assert store.size() == 1


@pytest.mark.asyncio
async def test_phash_search_returns_within_threshold() -> None:
    store = MemoryEmbeddingStore()
    vec = [0.1] * 512
    await store.upsert(_embedding("a" * 64, 0b0000, vec))
    await store.upsert(_embedding("b" * 64, 0b0001, vec))  # distance 1
    await store.upsert(_embedding("c" * 64, 0xFFFFFFFFFFFFFFFF, vec))  # very far

    hits = await store.search_phash(0b0000, max_distance=5)
    shas = {h.sha256 for h in hits}
    assert "a" * 64 in shas
    assert "b" * 64 in shas
    assert "c" * 64 not in shas


@pytest.mark.asyncio
async def test_clip_search_filters_by_cosine() -> None:
    store = MemoryEmbeddingStore()
    a_vec = [1.0, 0.0, 0.0] + [0.0] * 509
    b_vec = [0.95, 0.31, 0.0] + [0.0] * 509   # ~0.95 cosine to a
    c_vec = [-1.0, 0.0, 0.0] + [0.0] * 509    # -1.0 cosine to a
    await store.upsert(_embedding("a" * 64, 1, a_vec))
    await store.upsert(_embedding("b" * 64, 2, b_vec))
    await store.upsert(_embedding("c" * 64, 3, c_vec))

    hits = await store.search_clip(a_vec, min_cosine=0.8)
    shas = {h.sha256 for h in hits}
    assert "a" * 64 in shas
    assert "b" * 64 in shas
    assert "c" * 64 not in shas
