"""Seasonality forecaster — event matching + window math."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from scalemyprints.domain.niche.enums import Country, EventCategory
from scalemyprints.domain.niche.models import Event
from scalemyprints.domain.niche.ports import EventsProvider
from scalemyprints.domain.spy.seasonality_service import SeasonalityService


class _FakeEvents(EventsProvider):
    def __init__(self, events: list[Event]) -> None:
        self._events = events

    async def upcoming_events(
        self,
        *,
        country: Country,
        as_of: date,
        horizon_days: int = 180,
    ) -> list[Event]:
        cutoff = as_of + timedelta(days=horizon_days)
        return [e for e in self._events if as_of <= e.event_date <= cutoff]


def _event(name: str, days_out: int, tags: list[str] | None = None) -> Event:
    slug = name.lower().replace(" ", "-")
    return Event(
        id=f"us-{slug}-{days_out}",
        name=name,
        event_date=date.today() + timedelta(days=days_out),
        category=EventCategory.HOLIDAY,
        country=Country.US,
        pod_relevance_score=80,
        suggested_niches=tags or [],
    )


@pytest.mark.asyncio
async def test_matches_seed_to_event_name() -> None:
    events = [
        _event("Christmas", days_out=120),
        _event("Independence Day", days_out=60),
    ]
    svc = SeasonalityService(events_provider=_FakeEvents(events))
    forecast = await svc.forecast(seed="christmas mug", horizon_days=365)
    assert len(forecast.windows) == 1
    assert forecast.windows[0].name == "Christmas"
    assert forecast.windows[0].confidence >= 0.5


@pytest.mark.asyncio
async def test_matches_seed_to_tags() -> None:
    events = [_event("BlackOut Friday", days_out=90, tags=["sale", "discount"])]
    svc = SeasonalityService(events_provider=_FakeEvents(events))
    forecast = await svc.forecast(seed="discount tees", horizon_days=180)
    assert len(forecast.windows) == 1
    assert "discount" in forecast.windows[0].rationale.lower()


@pytest.mark.asyncio
async def test_no_matches_returns_empty() -> None:
    events = [_event("Christmas", days_out=200)]
    svc = SeasonalityService(events_provider=_FakeEvents(events))
    forecast = await svc.forecast(seed="vintage motorcycle", horizon_days=365)
    assert forecast.windows == []


@pytest.mark.asyncio
async def test_window_drop_by_subtracts_lag() -> None:
    events = [_event("Halloween", days_out=90)]
    svc = SeasonalityService(events_provider=_FakeEvents(events))
    forecast = await svc.forecast(seed="halloween cat", horizon_days=180, lag_days=30)
    w = forecast.windows[0]
    expected_starts = datetime.combine(events[0].event_date, datetime.min.time(), tzinfo=UTC) - timedelta(days=42)
    expected_drop_by = expected_starts - timedelta(days=30)
    assert abs((w.suggested_drop_by - expected_drop_by).total_seconds()) < 60
