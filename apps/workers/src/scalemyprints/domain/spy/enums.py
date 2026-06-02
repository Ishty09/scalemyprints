"""
Spy — domain enums.

Marketplaces we cover, listing lifecycle states, image-match types,
velocity classes, viral signal sources, and risk classifications.

Keep these in lockstep with packages/contracts/src/spy.ts.
"""

from __future__ import annotations

from enum import StrEnum


class Marketplace(StrEnum):
    """POD marketplaces Spy can search and snapshot."""

    ETSY = "etsy"
    AMAZON_MERCH = "amazon_merch"
    REDBUBBLE = "redbubble"
    TEEPUBLIC = "teepublic"
    SOCIETY6 = "society6"
    ZAZZLE = "zazzle"
    SPREADSHIRT = "spreadshirt"
    BONANZA = "bonanza"


class ListingStatus(StrEnum):
    """Lifecycle state of a tracked listing."""

    ACTIVE = "active"
    SOLD_OUT = "sold_out"
    INACTIVE = "inactive"
    DELISTED = "delisted"
    UNKNOWN = "unknown"


class ImageMatchType(StrEnum):
    """How an image match was discovered."""

    PHASH_EXACT = "phash_exact"      # Hamming distance 0-4
    PHASH_NEAR = "phash_near"        # Hamming distance 5-12
    CLIP_SEMANTIC = "clip_semantic"  # CLIP embedding cosine >= 0.85
    CLIP_LOOSE = "clip_loose"        # CLIP embedding cosine 0.70-0.85


class VelocityClass(StrEnum):
    """Bucketed velocity classification for ranking."""

    DORMANT = "dormant"          # < 1 sale / day or no signal
    STEADY = "steady"            # baseline, no spike
    RISING = "rising"            # z-score 1.0-2.5 vs 7d baseline
    SPIKING = "spiking"          # z-score > 2.5
    EXPLOSIVE = "explosive"      # z-score > 4 (rare, real moneymaker)


class SaturationClass(StrEnum):
    """How crowded a niche / design is."""

    OPEN = "open"                # 0-25 near-duplicates
    MILD = "mild"                # 26-150
    CROWDED = "crowded"          # 151-500
    SATURATED = "saturated"      # 501+


class ViralSource(StrEnum):
    """Where a viral signal was harvested from."""

    REDDIT = "reddit"
    TIKTOK = "tiktok"
    TWITTER = "twitter"
    INSTAGRAM = "instagram"
    PINTEREST = "pinterest"
    YOUTUBE_SHORTS = "youtube_shorts"
    GOOGLE_TRENDS = "google_trends"


class ShopAuditDepth(StrEnum):
    """How deep a shop teardown went — cheap to expensive."""

    SHALLOW = "shallow"          # top page only, ~20 listings
    STANDARD = "standard"        # first 5 pages, ~100 listings
    DEEP = "deep"                # full crawl, can be 1000+


class SpyJobStatus(StrEnum):
    """Lifecycle of an async Spy job (reverse-image, shop-audit, etc.)."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"          # some adapters errored but result usable
    FAILED = "failed"
    CANCELLED = "cancelled"


class SpyFailureReason(StrEnum):
    """Categorized failure for SpyJob escalation."""

    QUOTA_EXCEEDED = "quota_exceeded"
    SOURCE_BLOCKED = "source_blocked"             # all adapters got blocked
    SOURCE_RATE_LIMITED = "source_rate_limited"
    INVALID_INPUT = "invalid_input"
    UNSUPPORTED_MARKETPLACE = "unsupported_marketplace"
    IMAGE_TOO_LARGE = "image_too_large"
    IMAGE_INVALID = "image_invalid"
    EMBEDDING_FAILED = "embedding_failed"
    STORAGE_FAILURE = "storage_failure"
    INTERNAL = "internal"
