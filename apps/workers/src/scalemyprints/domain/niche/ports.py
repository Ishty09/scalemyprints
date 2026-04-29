"""
Niche Radar — ports (interfaces).

Domain depends on these Protocols, never on concrete adapters.
Each port can have multiple implementations (free + paid fallback).

Adapters NEVER raise — they return Result objects with `error` set
when something goes wrong. The orchestrator decides how to handle
partial data.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from scalemyprints.domain.niche.enums import Country
from scalemyprints.domain.niche.models import Event


# -----------------------------------------------------------------------------
# Result objects — what adapters return
# -----------------------------------------------------------------------------


class TrendsData(BaseModel):
    """Search-volume signal from a trends provider."""

    model_config = ConfigDict(frozen=True)

    search_volume_index: int  # 0-100
    growth_pct_90d: float | None = None
    related_queries: list[str] = Field(default_factory=list)
    sample_points: int = 0
    duration_ms: int = 0
    error: str | None = None


class MarketplaceData(BaseModel):
    """Listings/competition data from a marketplace scraper."""

    model_config = ConfigDict(frozen=True)

    listing_count: int | None = None
    unique_sellers_estimate: int | None = None
    avg_listing_age_days: float | None = None
    avg_price_usd: float | None = None
    sample_listings_urls: list[str] = Field(default_factory=list)
    sample_size: int = 0
    duration_ms: int = 0
    error: str | None = None


class NicheExpansionResult(BaseModel):
    """LLM-generated sub-niches from a seed keyword."""

    model_config = ConfigDict(frozen=True)

    suggestions: list[str] = Field(default_factory=list)
    rationale: str | None = None
    duration_ms: int = 0
    error: str | None = None


# -----------------------------------------------------------------------------
# Ports — Protocol interfaces
# -----------------------------------------------------------------------------


@runtime_checkable
class TrendsProvider(Protocol):
    """Search-trend signal source (Google Trends, etc.)."""

    async def fetch(self, keyword: str, country: Country) -> TrendsData:
        ...


@runtime_checkable
class MarketplaceProvider(Protocol):
    """Marketplace-listings signal source (Etsy, Amazon Merch, etc.)."""

    async def fetch(self, keyword: str, country: Country) -> MarketplaceData:
        ...


@runtime_checkable
class EventsProvider(Protocol):
    """Calendar-events source (static DB, Calendarific, etc.)."""

    async def list_events(
        self,
        country: Country,
        start_date: date,
        end_date: date,
    ) -> list[Event]:
        ...

    async def find_nearest_event(
        self,
        country: Country,
        keyword: str,
        as_of: date,
    ) -> Event | None:
        ...


@runtime_checkable
class NicheExpander(Protocol):
    """LLM-based niche idea generator."""

    async def expand(
        self,
        seed_keyword: str,
        country: Country,
        max_suggestions: int = 20,
    ) -> NicheExpansionResult:
        ...


@runtime_checkable
class NicheCacheStore(Protocol):
    """Cache for expensive niche lookups."""

    async def get(self, key: str) -> dict | None:
        ...

    async def set(self, key: str, value: dict, ttl_seconds: int) -> None:
        ...
