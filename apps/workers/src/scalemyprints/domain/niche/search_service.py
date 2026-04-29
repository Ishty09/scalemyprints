"""
Niche search orchestrator.

Composes signal providers (trends, marketplace, events) and scoring to
produce a complete NicheRecord. Handles partial failures gracefully —
if one provider fails, the niche still gets analyzed with the remaining
data, and `degraded=True` flags it for UI.

This is the only place that knows about all providers at once.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.niche.enums import Country
from scalemyprints.domain.niche.models import Event, NicheRecord
from scalemyprints.domain.niche.ports import (
    EventsProvider,
    MarketplaceProvider,
    NicheCacheStore,
    TrendsProvider,
)
from scalemyprints.domain.niche.scoring_service import (
    build_competition_score,
    build_demand_score,
    build_profitability_score,
    build_seasonality_score,
    build_trend_score,
    calculate_nhs,
)

logger = get_logger(__name__)


CACHE_TTL_SECONDS = 60 * 60 * 6  # 6 hours — niche data is slow-changing


class NicheSearchService:
    """Orchestrator for niche analysis."""

    def __init__(
        self,
        *,
        trends_provider: TrendsProvider,
        marketplace_provider: MarketplaceProvider,
        events_provider: EventsProvider,
        cache: NicheCacheStore,
    ) -> None:
        self._trends = trends_provider
        self._marketplace = marketplace_provider
        self._events = events_provider
        self._cache = cache

    async def analyze(
        self, keyword: str, country: Country
    ) -> NicheRecord:
        """
        Run all providers in parallel, score, return NicheRecord.

        Each provider is wrapped — failures don't crash analysis.
        """
        start = time.monotonic()
        keyword_clean = keyword.strip()
        log = logger.bind(keyword=keyword_clean, country=country.value)

        # Cache lookup
        cache_key = f"niche:{country.value}:{keyword_clean.lower()}"
        try:
            cached = await self._cache.get(cache_key)
            if cached:
                log.info("niche_cache_hit")
                return NicheRecord.model_validate(cached)
        except Exception:  # noqa: BLE001
            log.warning("niche_cache_lookup_failed")

        log.info("niche_analyze_start")

        # Run providers in parallel
        as_of_date = datetime.now(timezone.utc).date()
        trends_task = self._trends.fetch(keyword_clean, country)
        marketplace_task = self._marketplace.fetch(keyword_clean, country)
        nearest_event_task = self._events.find_nearest_event(country, keyword_clean, as_of_date)
        upcoming_events_task = self._events.list_events(
            country, as_of_date, as_of_date + timedelta(days=90)
        )

        trends, marketplace, nearest_event, upcoming_events = await asyncio.gather(
            trends_task,
            marketplace_task,
            nearest_event_task,
            upcoming_events_task,
            return_exceptions=False,  # adapters guarantee no raise
        )

        sources_used: list[str] = []
        degraded = False

        # Build sub-scores
        if trends.error:
            log.warning("trends_provider_error", error=trends.error)
            degraded = True
        sources_used.append(f"trends:{'ok' if not trends.error else 'failed'}")

        if marketplace.error:
            log.warning("marketplace_provider_error", error=marketplace.error)
            degraded = True
        sources_used.append(f"marketplace:{'ok' if not marketplace.error else 'failed'}")

        demand = build_demand_score(
            search_volume_index=trends.search_volume_index,
            listing_count=marketplace.listing_count,
            source="google_trends" if not trends.error else "fallback",
        )
        trend = build_trend_score(
            growth_pct_90d=trends.growth_pct_90d,
            sample_points=trends.sample_points,
        )
        competition = build_competition_score(
            listing_count=marketplace.listing_count,
            unique_sellers_estimate=marketplace.unique_sellers_estimate,
            avg_listing_age_days=marketplace.avg_listing_age_days,
        )
        profitability = build_profitability_score(
            avg_price_usd=marketplace.avg_price_usd,
            sample_size=marketplace.sample_size,
        )
        seasonality = build_seasonality_score(
            nearest_event_name=nearest_event.name if nearest_event else None,
            nearest_event_date=nearest_event.event_date if nearest_event else None,
            nearest_event_pod_relevance=nearest_event.pod_relevance_score if nearest_event else None,
            as_of=as_of_date,
        )

        # Headline score
        nhs_score, health = calculate_nhs(
            demand=demand,
            trend=trend,
            competition=competition,
            profitability=profitability,
            seasonality=seasonality,
        )

        duration_ms = int((time.monotonic() - start) * 1000)

        # Filter upcoming events to top-5 most POD-relevant
        relevant_upcoming = sorted(
            upcoming_events,
            key=lambda e: (-e.pod_relevance_score, e.event_date),
        )[:5]

        record = NicheRecord(
            keyword=keyword_clean,
            country=country,
            nhs_score=nhs_score,
            health=health,
            demand=demand,
            trend=trend,
            competition=competition,
            profitability=profitability,
            seasonality=seasonality,
            related_keywords=trends.related_queries[:10],
            sample_listings_urls=marketplace.sample_listings_urls[:5],
            upcoming_events=relevant_upcoming,
            analyzed_at=datetime.now(timezone.utc),
            duration_ms=duration_ms,
            data_sources_used=sources_used,
            degraded=degraded,
        )

        log.info(
            "niche_analyze_complete",
            nhs_score=nhs_score,
            health=health.value,
            degraded=degraded,
            duration_ms=duration_ms,
        )

        # Cache the result (best effort)
        try:
            await self._cache.set(cache_key, record.model_dump(mode="json"), CACHE_TTL_SECONDS)
        except Exception:  # noqa: BLE001
            log.warning("niche_cache_set_failed")

        return record
