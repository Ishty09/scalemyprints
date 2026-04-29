"""Tests for niche search orchestrator — covers happy path, partial failures, caching."""

from __future__ import annotations

from datetime import date

import pytest

from scalemyprints.domain.niche.enums import Country, EventCategory, NicheHealth
from scalemyprints.domain.niche.models import Event
from scalemyprints.domain.niche.ports import (
    MarketplaceData,
    TrendsData,
)
from scalemyprints.domain.niche.search_service import NicheSearchService
from scalemyprints.infrastructure.cache.niche_memory import NicheMemoryCache


# -----------------------------------------------------------------------------
# Stub providers for isolated unit testing
# -----------------------------------------------------------------------------


class StubTrendsProvider:
    def __init__(self, *, response: TrendsData):
        self.response = response
        self.calls = 0

    async def fetch(self, keyword: str, country: Country) -> TrendsData:
        self.calls += 1
        return self.response


class StubMarketplaceProvider:
    def __init__(self, *, response: MarketplaceData):
        self.response = response
        self.calls = 0

    async def fetch(self, keyword: str, country: Country) -> MarketplaceData:
        self.calls += 1
        return self.response


class StubEventsProvider:
    def __init__(
        self, *,
        nearest: Event | None = None,
        upcoming: list[Event] | None = None,
    ):
        self.nearest = nearest
        self.upcoming = upcoming or []

    async def list_events(
        self, country: Country, start_date: date, end_date: date
    ) -> list[Event]:
        return [
            e for e in self.upcoming
            if start_date <= e.event_date <= end_date and e.country == country
        ]

    async def find_nearest_event(
        self, country: Country, keyword: str, as_of: date
    ) -> Event | None:
        if self.nearest and self.nearest.country == country:
            return self.nearest
        return None


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def good_trends() -> TrendsData:
    return TrendsData(
        search_volume_index=75,
        growth_pct_90d=30.0,
        related_queries=["mom mug", "mama gift"],
        sample_points=12,
        duration_ms=400,
        error=None,
    )


@pytest.fixture
def good_marketplace() -> MarketplaceData:
    return MarketplaceData(
        listing_count=300,
        unique_sellers_estimate=200,
        avg_listing_age_days=120.0,
        avg_price_usd=22.99,
        sample_listings_urls=["https://www.etsy.com/listing/12345/example"],
        sample_size=20,
        duration_ms=600,
        error=None,
    )


@pytest.fixture
def mothers_day_event() -> Event:
    return Event(
        id="us-2026-05-10-mothers-day",
        country=Country.US,
        event_date=date(2026, 5, 10),
        name="Mother's Day",
        category=EventCategory.CULTURAL,
        pod_relevance_score=100,
        suggested_niches=["mom mug", "best mom"],
    )


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------


class TestNicheSearchService:
    @pytest.mark.asyncio
    async def test_happy_path(self, good_trends, good_marketplace, mothers_day_event):
        service = NicheSearchService(
            trends_provider=StubTrendsProvider(response=good_trends),
            marketplace_provider=StubMarketplaceProvider(response=good_marketplace),
            events_provider=StubEventsProvider(
                nearest=mothers_day_event, upcoming=[mothers_day_event]
            ),
            cache=NicheMemoryCache(),
        )
        record = await service.analyze("dog mom", Country.US)

        assert record.keyword == "dog mom"
        assert record.country == Country.US
        assert 0 <= record.nhs_score <= 100
        assert record.health in NicheHealth
        assert record.degraded is False
        assert "trends:ok" in record.data_sources_used
        assert "marketplace:ok" in record.data_sources_used

    @pytest.mark.asyncio
    async def test_trends_failure_marks_degraded(self, good_marketplace, mothers_day_event):
        broken_trends = TrendsData(
            search_volume_index=0, error="rate_limited", duration_ms=100
        )
        service = NicheSearchService(
            trends_provider=StubTrendsProvider(response=broken_trends),
            marketplace_provider=StubMarketplaceProvider(response=good_marketplace),
            events_provider=StubEventsProvider(
                nearest=mothers_day_event, upcoming=[mothers_day_event]
            ),
            cache=NicheMemoryCache(),
        )
        record = await service.analyze("dog mom", Country.US)

        assert record.degraded is True
        assert "trends:failed" in record.data_sources_used
        # Should still complete with default scores
        assert record.demand.score >= 0

    @pytest.mark.asyncio
    async def test_marketplace_failure_marks_degraded(
        self, good_trends, mothers_day_event
    ):
        broken_marketplace = MarketplaceData(error="blocked_403", duration_ms=100)
        service = NicheSearchService(
            trends_provider=StubTrendsProvider(response=good_trends),
            marketplace_provider=StubMarketplaceProvider(response=broken_marketplace),
            events_provider=StubEventsProvider(
                nearest=mothers_day_event, upcoming=[mothers_day_event]
            ),
            cache=NicheMemoryCache(),
        )
        record = await service.analyze("dog mom", Country.US)

        assert record.degraded is True
        assert "marketplace:failed" in record.data_sources_used

    @pytest.mark.asyncio
    async def test_no_events_uses_baseline_seasonality(self, good_trends, good_marketplace):
        service = NicheSearchService(
            trends_provider=StubTrendsProvider(response=good_trends),
            marketplace_provider=StubMarketplaceProvider(response=good_marketplace),
            events_provider=StubEventsProvider(nearest=None, upcoming=[]),
            cache=NicheMemoryCache(),
        )
        record = await service.analyze("evergreen niche", Country.US)

        # No event = baseline seasonality (30)
        assert record.seasonality.score == 30
        assert record.seasonality.nearest_event_name is None
        assert record.upcoming_events == []

    @pytest.mark.asyncio
    async def test_caching_returns_same_result(
        self, good_trends, good_marketplace, mothers_day_event
    ):
        cache = NicheMemoryCache()
        trends_stub = StubTrendsProvider(response=good_trends)
        marketplace_stub = StubMarketplaceProvider(response=good_marketplace)
        service = NicheSearchService(
            trends_provider=trends_stub,
            marketplace_provider=marketplace_stub,
            events_provider=StubEventsProvider(
                nearest=mothers_day_event, upcoming=[mothers_day_event]
            ),
            cache=cache,
        )

        record1 = await service.analyze("dog mom", Country.US)
        record2 = await service.analyze("dog mom", Country.US)

        # Second call should hit cache → providers only called once
        assert trends_stub.calls == 1
        assert marketplace_stub.calls == 1
        assert record1.nhs_score == record2.nhs_score
        assert record1.keyword == record2.keyword

    @pytest.mark.asyncio
    async def test_cache_separated_by_country(
        self, good_trends, good_marketplace
    ):
        trends_stub = StubTrendsProvider(response=good_trends)
        marketplace_stub = StubMarketplaceProvider(response=good_marketplace)
        service = NicheSearchService(
            trends_provider=trends_stub,
            marketplace_provider=marketplace_stub,
            events_provider=StubEventsProvider(),
            cache=NicheMemoryCache(),
        )

        await service.analyze("test phrase", Country.US)
        await service.analyze("test phrase", Country.UK)

        # Different countries = different cache keys
        assert trends_stub.calls == 2
        assert marketplace_stub.calls == 2

    @pytest.mark.asyncio
    async def test_cache_normalizes_case_and_whitespace(
        self, good_trends, good_marketplace
    ):
        trends_stub = StubTrendsProvider(response=good_trends)
        marketplace_stub = StubMarketplaceProvider(response=good_marketplace)
        service = NicheSearchService(
            trends_provider=trends_stub,
            marketplace_provider=marketplace_stub,
            events_provider=StubEventsProvider(),
            cache=NicheMemoryCache(),
        )

        # Same logical keyword in different forms
        await service.analyze("Dog Mom", Country.US)
        await service.analyze("dog mom", Country.US)
        await service.analyze("  dog mom  ", Country.US)

        # All three should hit the same cache after the first
        assert trends_stub.calls == 1

    @pytest.mark.asyncio
    async def test_upcoming_events_capped_to_5(self, good_trends, good_marketplace):
        # Create 8 events, all relevant
        events = [
            Event(
                id=f"us-2026-05-{10 + i:02d}-event-{i}",
                country=Country.US,
                event_date=date(2026, 5, 10 + i),
                name=f"Event {i}",
                category=EventCategory.CULTURAL,
                pod_relevance_score=80,
                suggested_niches=[],
            )
            for i in range(8)
        ]
        service = NicheSearchService(
            trends_provider=StubTrendsProvider(response=good_trends),
            marketplace_provider=StubMarketplaceProvider(response=good_marketplace),
            events_provider=StubEventsProvider(upcoming=events),
            cache=NicheMemoryCache(),
        )
        record = await service.analyze("test", Country.US)
        assert len(record.upcoming_events) == 5

    @pytest.mark.asyncio
    async def test_upcoming_events_sorted_by_relevance(
        self, good_trends, good_marketplace
    ):
        events = [
            Event(
                id="us-2026-05-10-low",
                country=Country.US,
                event_date=date(2026, 5, 10),
                name="Low Relevance",
                category=EventCategory.QUIRKY,
                pod_relevance_score=30,
                suggested_niches=[],
            ),
            Event(
                id="us-2026-05-15-high",
                country=Country.US,
                event_date=date(2026, 5, 15),
                name="High Relevance",
                category=EventCategory.CULTURAL,
                pod_relevance_score=95,
                suggested_niches=[],
            ),
        ]
        service = NicheSearchService(
            trends_provider=StubTrendsProvider(response=good_trends),
            marketplace_provider=StubMarketplaceProvider(response=good_marketplace),
            events_provider=StubEventsProvider(upcoming=events),
            cache=NicheMemoryCache(),
        )
        record = await service.analyze("test", Country.US)
        # High relevance first
        assert record.upcoming_events[0].name == "High Relevance"

    @pytest.mark.asyncio
    async def test_related_keywords_capped_to_10(self, good_marketplace, mothers_day_event):
        many_related = [f"related-{i}" for i in range(20)]
        trends = TrendsData(
            search_volume_index=70,
            growth_pct_90d=10.0,
            related_queries=many_related,
            sample_points=12,
        )
        service = NicheSearchService(
            trends_provider=StubTrendsProvider(response=trends),
            marketplace_provider=StubMarketplaceProvider(response=good_marketplace),
            events_provider=StubEventsProvider(nearest=mothers_day_event),
            cache=NicheMemoryCache(),
        )
        record = await service.analyze("test", Country.US)
        assert len(record.related_keywords) == 10

    @pytest.mark.asyncio
    async def test_sample_listings_capped_to_5(self, good_trends, mothers_day_event):
        many_urls = [f"https://www.etsy.com/listing/{i}/x" for i in range(20)]
        marketplace = MarketplaceData(
            listing_count=500,
            unique_sellers_estimate=300,
            avg_listing_age_days=180.0,
            avg_price_usd=25.0,
            sample_listings_urls=many_urls,
            sample_size=20,
        )
        service = NicheSearchService(
            trends_provider=StubTrendsProvider(response=good_trends),
            marketplace_provider=StubMarketplaceProvider(response=marketplace),
            events_provider=StubEventsProvider(nearest=mothers_day_event),
            cache=NicheMemoryCache(),
        )
        record = await service.analyze("test", Country.US)
        assert len(record.sample_listings_urls) == 5

    @pytest.mark.asyncio
    async def test_record_includes_duration(self, good_trends, good_marketplace):
        service = NicheSearchService(
            trends_provider=StubTrendsProvider(response=good_trends),
            marketplace_provider=StubMarketplaceProvider(response=good_marketplace),
            events_provider=StubEventsProvider(),
            cache=NicheMemoryCache(),
        )
        record = await service.analyze("test", Country.US)
        assert record.duration_ms >= 0
        assert record.analyzed_at is not None
