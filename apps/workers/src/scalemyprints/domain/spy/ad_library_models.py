"""
Ad-library domain models.

Lives in `domain/spy/` because ads are a Spy concept, not a generic
service. Mirrors `spy_ad_hits` rows in the Phase 2 migration.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class AdPlatform(StrEnum):
    """Where the ad was running."""

    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    PINTEREST = "pinterest"
    GOOGLE_ADS = "google_ads"


class AdSpyHit(BaseModel):
    """One ad observation pulled from an ad library."""

    model_config = ConfigDict(frozen=True)

    platform: AdPlatform
    ad_id: str
    page_or_handle: str
    page_id: str | None = None
    ad_creative_url: HttpUrl | None = None
    landing_url: HttpUrl | None = None
    primary_text: str | None = None
    headline: str | None = None
    cta: str | None = None
    started_at: datetime | None = None
    last_seen_at: datetime | None = None
    impressions_lower: int | None = Field(default=None, ge=0)
    impressions_upper: int | None = Field(default=None, ge=0)
    spend_usd_lower: float | None = Field(default=None, ge=0.0)
    spend_usd_upper: float | None = Field(default=None, ge=0.0)
    countries: list[str] = Field(default_factory=list)
