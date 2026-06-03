"""
Tag/SEO mining — cross-platform tag extraction at scale.

Given a phrase or seed query, search every marketplace, harvest the
tags from every returned listing, and rank by:
- Frequency (how often the tag appears)
- Concentration (Herfindahl across marketplaces — tags that span
  multiple platforms are stronger)
- Co-occurrence with the seed phrase

Returns a TagMiningResult with the top-N tags + per-tag metadata.
"""

from __future__ import annotations

import time
from collections import Counter
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from scalemyprints.core.logging import get_logger

if TYPE_CHECKING:
    from scalemyprints.domain.spy.enums import Marketplace
    from scalemyprints.domain.spy.search_service import SpySearchService

logger = get_logger(__name__)


class MinedTag(BaseModel):
    """A tag's metadata across marketplaces."""

    model_config = ConfigDict(frozen=True)

    tag: str
    total_count: int = Field(ge=0)
    by_marketplace: dict[str, int] = Field(default_factory=dict)
    distinct_marketplaces: int = Field(ge=0)
    sample_listings: list[str] = Field(default_factory=list)  # listing IDs/URLs


class TagMiningResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    seed: str
    tags: list[MinedTag] = Field(default_factory=list)
    total_listings_scanned: int = Field(ge=0)
    duration_ms: int = Field(ge=0)


class TagMiningService:
    """Cross-marketplace tag harvester."""

    def __init__(self, *, search_service: SpySearchService) -> None:
        self._search = search_service

    async def mine(
        self,
        *,
        seed: str,
        marketplaces: list[Marketplace] | None = None,
        per_marketplace_limit: int = 50,
        top_n: int = 40,
    ) -> TagMiningResult:
        start = time.monotonic()

        from scalemyprints.domain.spy.models import SpyQuery  # noqa: PLC0415

        result = await self._search.run(
            SpyQuery(
                text=seed,
                marketplaces=marketplaces or [],
                limit=per_marketplace_limit,
            )
        )

        # Aggregate
        total_counter: Counter[str] = Counter()
        per_mkt_counter: dict[str, Counter[str]] = {}
        sample_by_tag: dict[str, list[str]] = {}

        for listing in result.listings:
            mkt = listing.marketplace.value
            mkt_counter = per_mkt_counter.setdefault(mkt, Counter())
            for raw in listing.tags:
                tag = _normalize_tag(raw)
                if not tag:
                    continue
                total_counter[tag] += 1
                mkt_counter[tag] += 1
                samples = sample_by_tag.setdefault(tag, [])
                if len(samples) < 5:
                    samples.append(str(listing.url))

        mined: list[MinedTag] = []
        for tag, total in total_counter.most_common(top_n):
            by_mkt = {
                m: int(c.get(tag, 0))
                for m, c in per_mkt_counter.items()
                if c.get(tag, 0) > 0
            }
            mined.append(
                MinedTag(
                    tag=tag,
                    total_count=total,
                    by_marketplace=by_mkt,
                    distinct_marketplaces=len(by_mkt),
                    sample_listings=sample_by_tag.get(tag, [])[:5],
                )
            )

        return TagMiningResult(
            seed=seed,
            tags=mined,
            total_listings_scanned=len(result.listings),
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def _normalize_tag(raw: str) -> str:
    return (raw or "").strip().lower()
