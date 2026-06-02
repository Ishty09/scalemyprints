"""
Reverse image search — image bytes in, ranked matches across all
marketplaces out.

Pipeline:
  1. Embed (pHash + CLIP) — open-source pipeline, no API calls
  2. Persist the embedding (so future searches can reuse it)
  3. Run two ANN queries against EmbeddingStore:
       - phash within Hamming distance threshold (fast, exact-ish)
       - clip cosine similarity above threshold (semantic)
  4. Merge + dedupe hits, then enrich each with the canonical Listing
  5. Score each match 0-100 combining phash distance and CLIP cosine
  6. Sort + cap at `limit`
"""

from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.enums import (
    ImageMatchType,
    SpyFailureReason,
)
from scalemyprints.domain.spy.models import (
    DesignEmbedding,
    ReverseImageMatch,
)
from scalemyprints.domain.spy.ports import (
    ReverseImageSearchResult,
)

if TYPE_CHECKING:
    from scalemyprints.domain.spy.ports import (
        EmbeddingStore,
        ImageEmbedder,
        ListingStore,
    )

logger = get_logger(__name__)


# Tunable thresholds. Kept here (not in Settings) because they're algorithm
# constants rather than deployment config.
PHASH_EXACT_MAX = 4
PHASH_NEAR_MAX = 12
CLIP_SEMANTIC_MIN = 0.85
CLIP_LOOSE_MIN = 0.70


class ReverseImageSearchService:
    """Orchestrates embed → ANN search → enrich + score."""

    def __init__(
        self,
        *,
        embedder: ImageEmbedder,
        embedding_store: EmbeddingStore,
        listing_store: ListingStore,
    ) -> None:
        self._embedder = embedder
        self._embedding_store = embedding_store
        self._listing_store = listing_store

    async def search(
        self,
        image_bytes: bytes,
        *,
        limit: int = 30,
        min_clip_cosine: float = CLIP_LOOSE_MIN,
    ) -> ReverseImageSearchResult:
        start = time.monotonic()

        if not image_bytes:
            return ReverseImageSearchResult(
                query_sha256="",
                error="empty_image",
                failure_reason=SpyFailureReason.IMAGE_INVALID,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        # ---- 1. Embed ---------------------------------------------------------
        embed_result = await self._embedder.embed(image_bytes)
        if embed_result.error:
            logger.warning("reverse_image_embed_failed", error=embed_result.error)
            return ReverseImageSearchResult(
                query_sha256=embed_result.sha256,
                error=embed_result.error,
                failure_reason=SpyFailureReason.EMBEDDING_FAILED,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        sha256 = embed_result.sha256 or _sha256_hex(image_bytes)
        log = logger.bind(query_sha256=sha256)

        # ---- 2. Persist embedding (best-effort) -------------------------------
        try:
            await self._embedding_store.upsert(
                DesignEmbedding(
                    sha256=sha256,
                    phash=embed_result.phash,
                    clip_embedding=embed_result.clip_embedding,
                    width=embed_result.width,
                    height=embed_result.height,
                    bytes_size=embed_result.bytes_size,
                    created_at=datetime.now(UTC),
                )
            )
        except Exception as e:
            log.warning("reverse_image_embedding_persist_failed", error=str(e))

        # ---- 3. ANN searches in parallel-ish ----------------------------------
        phash_hits = await self._embedding_store.search_phash(
            embed_result.phash,
            max_distance=PHASH_NEAR_MAX,
            limit=limit * 2,
        )
        clip_hits = await self._embedding_store.search_clip(
            embed_result.clip_embedding,
            min_cosine=min_clip_cosine,
            limit=limit * 2,
        )

        # ---- 4. Merge + dedupe + enrich ---------------------------------------
        # Track best signal per listing id.
        best: dict[str, dict[str, object]] = {}

        for hit in phash_hits:
            for listing_id in hit.listing_ids:
                slot = best.setdefault(listing_id, {})
                d = hit.phash_distance if hit.phash_distance is not None else 64
                prev_d = slot.get("phash_distance")
                if not isinstance(prev_d, int) or d < prev_d:
                    slot["phash_distance"] = d

        for hit in clip_hits:
            for listing_id in hit.listing_ids:
                slot = best.setdefault(listing_id, {})
                c = hit.clip_cosine if hit.clip_cosine is not None else -1.0
                prev_c = slot.get("clip_cosine")
                if not isinstance(prev_c, float) or c > prev_c:
                    slot["clip_cosine"] = c

        matches: list[ReverseImageMatch] = []
        for listing_id, slot in best.items():
            listing = await self._listing_store.get_listing(listing_id)
            if listing is None:
                continue

            phash_distance = (
                int(slot["phash_distance"]) if isinstance(slot.get("phash_distance"), int) else None
            )
            clip_cosine = (
                float(slot["clip_cosine"]) if isinstance(slot.get("clip_cosine"), float) else None
            )

            match_type = _classify_match(phash_distance, clip_cosine)
            score = _score_match(phash_distance, clip_cosine)

            matches.append(
                ReverseImageMatch(
                    listing=listing,
                    match_type=match_type,
                    phash_distance=phash_distance,
                    clip_cosine=clip_cosine,
                    score=score,
                )
            )

        matches.sort(key=lambda m: m.score, reverse=True)
        matches = matches[:limit]

        log.info(
            "reverse_image_search_completed",
            match_count=len(matches),
            phash_hits=len(phash_hits),
            clip_hits=len(clip_hits),
        )

        return ReverseImageSearchResult(
            query_sha256=sha256,
            matches=matches,
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def _classify_match(
    phash_distance: int | None,
    clip_cosine: float | None,
) -> ImageMatchType:
    if phash_distance is not None and phash_distance <= PHASH_EXACT_MAX:
        return ImageMatchType.PHASH_EXACT
    if clip_cosine is not None and clip_cosine >= CLIP_SEMANTIC_MIN:
        return ImageMatchType.CLIP_SEMANTIC
    if phash_distance is not None and phash_distance <= PHASH_NEAR_MAX:
        return ImageMatchType.PHASH_NEAR
    return ImageMatchType.CLIP_LOOSE


def _score_match(phash_distance: int | None, clip_cosine: float | None) -> int:
    """
    Combine pHash distance and CLIP cosine into a single 0-100 score.

    Strategy:
    - pHash distance 0 → 60 points; distance 12 → 0 points (linear)
    - CLIP cosine 1.0 → 40 points; cosine 0.70 → 0 points (linear)
    - Clamp to [0, 100]
    """
    p_pts = 0.0
    if phash_distance is not None and phash_distance <= PHASH_NEAR_MAX:
        p_pts = max(0.0, 60.0 * (1.0 - phash_distance / PHASH_NEAR_MAX))

    c_pts = 0.0
    if clip_cosine is not None and clip_cosine >= CLIP_LOOSE_MIN:
        denom = 1.0 - CLIP_LOOSE_MIN
        c_pts = max(0.0, 40.0 * (clip_cosine - CLIP_LOOSE_MIN) / denom)

    return max(0, min(100, round(p_pts + c_pts)))


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
