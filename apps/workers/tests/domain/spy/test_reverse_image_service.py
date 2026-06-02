"""End-to-end reverse image search test using memory adapters."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scalemyprints.domain.spy.enums import (
    ImageMatchType,
    ListingStatus,
    Marketplace,
    VelocityClass,
)
from scalemyprints.domain.spy.models import Listing
from scalemyprints.domain.spy.reverse_image_service import ReverseImageSearchService
from scalemyprints.infrastructure.image_search.clip_embedder import StubImageEmbedder
from scalemyprints.infrastructure.image_search.memory_store import MemoryEmbeddingStore
from scalemyprints.infrastructure.spy_storage.memory_listing_store import (
    MemoryListingStore,
)


def _listing(idx: int) -> Listing:
    now = datetime.now(UTC)
    return Listing(
        marketplace=Marketplace.ETSY,
        external_id=f"L{idx}",
        url=f"https://example.com/{idx}",  # type: ignore[arg-type]
        title=f"design {idx}",
        status=ListingStatus.ACTIVE,
        velocity_class=VelocityClass.STEADY,
        first_seen_at=now,
        last_seen_at=now,
    )


@pytest.fixture
def stack() -> tuple[
    ReverseImageSearchService,
    MemoryEmbeddingStore,
    MemoryListingStore,
    StubImageEmbedder,
]:
    embedder = StubImageEmbedder()
    e_store = MemoryEmbeddingStore()
    l_store = MemoryListingStore()
    svc = ReverseImageSearchService(
        embedder=embedder,
        embedding_store=e_store,
        listing_store=l_store,
    )
    return svc, e_store, l_store, embedder


@pytest.mark.asyncio
async def test_empty_bytes_returns_image_invalid_failure(
    stack: tuple[
        ReverseImageSearchService,
        MemoryEmbeddingStore,
        MemoryListingStore,
        StubImageEmbedder,
    ],
) -> None:
    svc, *_ = stack
    result = await svc.search(b"")
    assert result.error == "empty_image"


@pytest.mark.asyncio
async def test_no_hits_returns_empty_matches(
    stack: tuple[
        ReverseImageSearchService,
        MemoryEmbeddingStore,
        MemoryListingStore,
        StubImageEmbedder,
    ],
) -> None:
    svc, *_ = stack
    result = await svc.search(b"some-image-bytes")
    assert result.error is None
    assert result.matches == []
    assert len(result.query_sha256) == 64


@pytest.mark.asyncio
async def test_identical_bytes_match_exactly(
    stack: tuple[
        ReverseImageSearchService,
        MemoryEmbeddingStore,
        MemoryListingStore,
        StubImageEmbedder,
    ],
) -> None:
    svc, e_store, l_store, embedder = stack

    # 1. Embed once, link to a listing, persist embedding
    image = b"same-design-everywhere"
    pre = await embedder.embed(image)

    listing_id = await l_store.upsert_listing(_listing(1))
    from scalemyprints.domain.spy.models import DesignEmbedding

    await e_store.upsert(
        DesignEmbedding(
            sha256=pre.sha256,
            phash=pre.phash,
            clip_embedding=pre.clip_embedding,
            width=pre.width,
            height=pre.height,
            bytes_size=pre.bytes_size,
            created_at=datetime.now(UTC),
        )
    )
    await e_store.link_listing(pre.sha256, listing_id)

    # 2. Now query with the same image — should find listing back
    result = await svc.search(image)
    assert result.error is None
    assert len(result.matches) == 1
    match = result.matches[0]
    assert match.listing.external_id == "L1"
    assert match.match_type == ImageMatchType.PHASH_EXACT
    assert match.score >= 90  # near 100, since exact match


@pytest.mark.asyncio
async def test_different_bytes_do_not_match(
    stack: tuple[
        ReverseImageSearchService,
        MemoryEmbeddingStore,
        MemoryListingStore,
        StubImageEmbedder,
    ],
) -> None:
    svc, e_store, l_store, embedder = stack

    pre = await embedder.embed(b"original-image-A")
    listing_id = await l_store.upsert_listing(_listing(1))
    from scalemyprints.domain.spy.models import DesignEmbedding

    await e_store.upsert(
        DesignEmbedding(
            sha256=pre.sha256,
            phash=pre.phash,
            clip_embedding=pre.clip_embedding,
            width=pre.width,
            height=pre.height,
            bytes_size=pre.bytes_size,
            created_at=datetime.now(UTC),
        )
    )
    await e_store.link_listing(pre.sha256, listing_id)

    # Query with totally different image
    result = await svc.search(b"completely-different-image-B")
    # The deterministic stub will produce unrelated vectors — should not match
    # at default cosine threshold of 0.70 and the pHash will differ a lot.
    assert all(m.listing.external_id != "L1" for m in result.matches) or result.matches == []
