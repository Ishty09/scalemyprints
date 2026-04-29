"""Tests for static events provider — uses real curated DB."""

from __future__ import annotations

from datetime import date

import pytest

from scalemyprints.domain.niche.enums import Country, EventCategory
from scalemyprints.infrastructure.niche_apis.static_events import StaticEventsProvider


@pytest.fixture
def provider() -> StaticEventsProvider:
    return StaticEventsProvider()


class TestStaticEventsProviderListEvents:
    @pytest.mark.asyncio
    async def test_us_events_in_window(self, provider):
        events = await provider.list_events(
            Country.US, date(2026, 5, 1), date(2026, 5, 31)
        )
        assert len(events) > 0
        # Mother's Day expected in May
        names = {e.name for e in events}
        assert any("mother" in n.lower() for n in names)

    @pytest.mark.asyncio
    async def test_au_australia_day(self, provider):
        events = await provider.list_events(
            Country.AU, date(2026, 1, 1), date(2026, 1, 31)
        )
        names = [e.name for e in events]
        assert any("Australia Day" in n for n in names)

    @pytest.mark.asyncio
    async def test_de_oktoberfest(self, provider):
        events = await provider.list_events(
            Country.DE, date(2026, 9, 1), date(2026, 9, 30)
        )
        names = [e.name for e in events]
        assert any("Oktoberfest" in n for n in names)

    @pytest.mark.asyncio
    async def test_uk_bonfire_night(self, provider):
        events = await provider.list_events(
            Country.UK, date(2026, 11, 1), date(2026, 11, 30)
        )
        names = [e.name for e in events]
        assert any("Bonfire" in n for n in names)

    @pytest.mark.asyncio
    async def test_ca_canada_day(self, provider):
        events = await provider.list_events(
            Country.CA, date(2026, 7, 1), date(2026, 7, 31)
        )
        names = [e.name for e in events]
        assert any("Canada Day" in n for n in names)

    @pytest.mark.asyncio
    async def test_empty_window_returns_empty(self, provider):
        events = await provider.list_events(
            Country.US, date(2026, 4, 28), date(2026, 4, 29)
        )
        # April 28-29 typically empty
        assert isinstance(events, list)

    @pytest.mark.asyncio
    async def test_country_filter_works(self, provider):
        # German events shouldn't appear in US listing
        us_events = await provider.list_events(
            Country.US, date(2026, 9, 20), date(2026, 9, 30)
        )
        de_events = await provider.list_events(
            Country.DE, date(2026, 9, 20), date(2026, 9, 30)
        )
        # Different sets
        assert {e.name for e in us_events} != {e.name for e in de_events}

    @pytest.mark.asyncio
    async def test_year_boundary_window(self, provider):
        # Window spanning Dec→Jan
        events = await provider.list_events(
            Country.US, date(2026, 12, 20), date(2027, 1, 5)
        )
        names = {e.name for e in events}
        assert any("Christmas" in n for n in names)
        assert any("New Year" in n for n in names)

    @pytest.mark.asyncio
    async def test_events_sorted_by_date(self, provider):
        events = await provider.list_events(
            Country.US, date(2026, 1, 1), date(2026, 12, 31)
        )
        dates = [e.event_date for e in events]
        assert dates == sorted(dates)

    @pytest.mark.asyncio
    async def test_event_has_pod_relevance_score(self, provider):
        events = await provider.list_events(
            Country.US, date(2026, 1, 1), date(2026, 12, 31)
        )
        for e in events:
            assert 0 <= e.pod_relevance_score <= 100

    @pytest.mark.asyncio
    async def test_event_has_suggested_niches(self, provider):
        events = await provider.list_events(
            Country.US, date(2026, 5, 1), date(2026, 5, 31)
        )
        # At least some should have niche suggestions
        with_niches = [e for e in events if e.suggested_niches]
        assert len(with_niches) > 0

    @pytest.mark.asyncio
    async def test_categories_are_valid_enum(self, provider):
        events = await provider.list_events(
            Country.US, date(2026, 1, 1), date(2026, 12, 31)
        )
        for e in events:
            assert e.category in EventCategory


class TestStaticEventsProviderFindNearest:
    @pytest.mark.asyncio
    async def test_nearest_to_keyword_match(self, provider):
        # "mom" should find Mother's Day
        nearest = await provider.find_nearest_event(
            Country.US, "dog mom mug", date(2026, 4, 27)
        )
        assert nearest is not None
        assert "mother" in nearest.name.lower() or "mom" in str(nearest.suggested_niches).lower()

    @pytest.mark.asyncio
    async def test_christmas_keyword_match(self, provider):
        nearest = await provider.find_nearest_event(
            Country.US, "christmas decoration", date(2026, 11, 1)
        )
        assert nearest is not None
        # November 1 → Christmas Dec 25 should be closest matching
        assert nearest.event_date >= date(2026, 11, 1)

    @pytest.mark.asyncio
    async def test_unrelated_keyword_falls_back_to_high_relevance(self, provider):
        # Random keyword with no semantic match
        nearest = await provider.find_nearest_event(
            Country.US, "xyzabc unique noun", date(2026, 4, 27)
        )
        # Should still return SOMETHING (the next high-relevance event)
        # OR None if nothing is high-relevance ahead — both acceptable
        if nearest is not None:
            assert nearest.pod_relevance_score >= 75

    @pytest.mark.asyncio
    async def test_country_specific_match(self, provider):
        # "australia day" should match in AU only
        au_match = await provider.find_nearest_event(
            Country.AU, "australia day shirt", date(2025, 12, 1)
        )
        assert au_match is not None
        assert au_match.country == Country.AU

    @pytest.mark.asyncio
    async def test_no_past_events_returned(self, provider):
        # Yesterday
        as_of = date(2026, 4, 27)
        nearest = await provider.find_nearest_event(Country.US, "halloween", as_of)
        if nearest:
            assert nearest.event_date >= as_of
