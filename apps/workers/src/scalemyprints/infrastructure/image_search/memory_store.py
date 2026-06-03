"""
In-memory EmbeddingStore — used in unit tests and as a dev fallback
when Supabase pgvector isn't configured.

Stores embeddings + listing links in process memory. Brute-force ANN
search (cosine + Hamming) is fine for small datasets / tests.
"""

from __future__ import annotations

from collections import defaultdict
from math import sqrt
from typing import TYPE_CHECKING

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.ports import EmbeddingSearchHit, EmbeddingStore
from scalemyprints.infrastructure.image_search.phash import hamming_distance

if TYPE_CHECKING:
    from scalemyprints.domain.spy.models import DesignEmbedding

logger = get_logger(__name__)


class MemoryEmbeddingStore(EmbeddingStore):
    """Process-local embedding store. Resets on restart."""

    def __init__(self) -> None:
        self._by_sha: dict[str, DesignEmbedding] = {}
        self._listings_by_sha: dict[str, set[str]] = defaultdict(set)

    async def upsert(self, embedding: DesignEmbedding) -> None:
        self._by_sha[embedding.sha256] = embedding

    async def link_listing(self, sha256: str, listing_id: str) -> None:
        self._listings_by_sha[sha256].add(listing_id)

    async def search_phash(
        self,
        phash: int,
        *,
        max_distance: int = 12,
        limit: int = 50,
    ) -> list[EmbeddingSearchHit]:
        hits: list[tuple[int, EmbeddingSearchHit]] = []
        for sha, emb in self._by_sha.items():
            d = hamming_distance(emb.phash, phash)
            if d > max_distance:
                continue
            hits.append(
                (
                    d,
                    EmbeddingSearchHit(
                        sha256=sha,
                        listing_ids=sorted(self._listings_by_sha.get(sha, set())),
                        phash_distance=d,
                    ),
                )
            )
        hits.sort(key=lambda t: t[0])
        return [h for _, h in hits[:limit]]

    async def search_clip(
        self,
        vector: list[float],
        *,
        min_cosine: float = 0.70,
        limit: int = 50,
    ) -> list[EmbeddingSearchHit]:
        if not vector:
            return []

        # Pre-normalize query if needed
        q_norm = sqrt(sum(x * x for x in vector)) or 1.0

        hits: list[tuple[float, EmbeddingSearchHit]] = []
        for sha, emb in self._by_sha.items():
            if len(emb.clip_embedding) != len(vector):
                continue
            dot = sum(a * b for a, b in zip(emb.clip_embedding, vector, strict=True))
            e_norm = sqrt(sum(x * x for x in emb.clip_embedding)) or 1.0
            cos = dot / (q_norm * e_norm)
            if cos < min_cosine:
                continue
            hits.append(
                (
                    cos,
                    EmbeddingSearchHit(
                        sha256=sha,
                        listing_ids=sorted(self._listings_by_sha.get(sha, set())),
                        clip_cosine=cos,
                    ),
                )
            )
        hits.sort(key=lambda t: t[0], reverse=True)
        return [h for _, h in hits[:limit]]

    # Test helpers ---------------------------------------------------------

    def clear(self) -> None:
        self._by_sha.clear()
        self._listings_by_sha.clear()

    def size(self) -> int:
        return len(self._by_sha)
