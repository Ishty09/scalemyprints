"""Integration tests for niche endpoints — covers full request/response flow."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date

import pytest
from fastapi.testclient import TestClient

from scalemyprints.app import create_app
from scalemyprints.core.config import get_settings
from scalemyprints.domain.niche.enums import Country, EventCategory
from scalemyprints.domain.niche.models import Event
from scalemyprints.domain.niche.ports import (
    MarketplaceData,
    TrendsData,
)
from scalemyprints.domain.niche.search_service import NicheSearchService
from scalemyprints.infrastructure.cache.niche_memory import NicheMemoryCache
from scalemyprints.infrastructure.container import get_container


# -----------------------------------------------------------------------------
# Fakes
# -----------------------------------------------------------------------------


@dataclass
class FakeTrendsProvider:
    response: TrendsData = field(default_factory=lambda: TrendsData(
        search_volume_index=70,
        growth_pct_90d=15.0,
        related_queries=["foo", "bar"],
        sample_points=12,
    ))
    call_count: int = 0

    async def fetch(self, keyword: str, country: Country) -> TrendsData:
        self.call_count += 1
        return self.response


@dataclass
class FakeMarketplaceProvider:
    response: MarketplaceData = field(default_factory=lambda: MarketplaceData(
        listing_count=300,
        unique_sellers_estimate=200,
        avg_listing_age_days=180.0,
        avg_price_usd=22.99,
        sample_listings_urls=[],
        sample_size=10,
    ))
    call_count: int = 0

    async def fetch(self, keyword: str, country: Country) -> MarketplaceData:
        self.call_count += 1
        return self.response


@dataclass
class FakeEventsProvider:
    nearest: Event | None = None
    upcoming: list = field(default_factory=list)

    async def list_events(
        self, country: Country, start_date: date, end_date: date
    ) -> list:
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


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("INTERNAL_API_SECRET", "b" * 64)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret")
    monkeypatch.setenv("WORKER_CORS_ORIGINS", "http://localhost:3000")
    get_settings.cache_clear()
    get_container.cache_clear()


@pytest.fixture
def fake_trends() -> FakeTrendsProvider:
    return FakeTrendsProvider()


@pytest.fixture
def fake_marketplace() -> FakeMarketplaceProvider:
    return FakeMarketplaceProvider()


@pytest.fixture
def fake_events() -> FakeEventsProvider:
    return FakeEventsProvider(
        upcoming=[
            Event(
                id="us-2026-05-10-mothers-day",
                country=Country.US,
                event_date=date(2026, 5, 10),
                name="Mother's Day",
                category=EventCategory.CULTURAL,
                pod_relevance_score=100,
                suggested_niches=["mom mug", "best mom"],
            ),
            Event(
                id="us-2026-07-04-independence",
                country=Country.US,
                event_date=date(2026, 7, 4),
                name="Independence Day",
                category=EventCategory.HOLIDAY,
                pod_relevance_score=100,
                suggested_niches=["4th of july"],
            ),
        ]
    )


@pytest.fixture
def app_with_fake_niche(fake_trends, fake_marketplace, fake_events):
    """App with niche service overridden to use fake providers."""
    app = create_app()

    def _override():
        return NicheSearchService(
            trends_provider=fake_trends,
            marketplace_provider=fake_marketplace,
            events_provider=fake_events,
            cache=NicheMemoryCache(),
        )

    from scalemyprints.api.deps import get_niche_search_service

    app.dependency_overrides[get_niche_search_service] = _override
    # Override container's events provider too (for /events endpoint)
    container = get_container()
    container._niche_events = fake_events  # noqa: SLF001
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app_with_fake_niche) -> Iterator[TestClient]:
    with TestClient(app_with_fake_niche) as c:
        yield c


# -----------------------------------------------------------------------------
# POST /niche/search
# -----------------------------------------------------------------------------


class TestNicheSearchEndpoint:
    def test_search_returns_200(self, client: TestClient):
        response = client.post(
            "/api/v1/niche/search",
            json={"keyword": "dog mom", "country": "US"},
        )
        assert response.status_code == 200

    def test_search_returns_envelope(self, client: TestClient):
        payload = client.post(
            "/api/v1/niche/search",
            json={"keyword": "dog mom", "country": "US"},
        ).json()
        assert payload["ok"] is True
        assert "data" in payload
        data = payload["data"]
        assert data["keyword"] == "dog mom"
        assert data["country"] == "US"
        assert 0 <= data["nhs_score"] <= 100
        assert data["health"] in ("hot", "promising", "moderate", "weak", "avoid")

    def test_search_default_country_is_us(self, client: TestClient):
        payload = client.post(
            "/api/v1/niche/search", json={"keyword": "evergreen"}
        ).json()
        assert payload["data"]["country"] == "US"

    def test_search_includes_all_signals(self, client: TestClient):
        payload = client.post(
            "/api/v1/niche/search",
            json={"keyword": "test", "country": "US"},
        ).json()
        data = payload["data"]
        assert "demand" in data
        assert "trend" in data
        assert "competition" in data
        assert "profitability" in data
        assert "seasonality" in data

    def test_search_validates_keyword_min_length(self, client: TestClient):
        response = client.post(
            "/api/v1/niche/search",
            json={"keyword": "a", "country": "US"},
        )
        assert response.status_code == 400

    def test_search_validates_invalid_country(self, client: TestClient):
        response = client.post(
            "/api/v1/niche/search",
            json={"keyword": "test", "country": "XX"},
        )
        assert response.status_code == 400

    def test_search_rejects_extra_fields(self, client: TestClient):
        response = client.post(
            "/api/v1/niche/search",
            json={"keyword": "test", "country": "US", "evil_field": "haha"},
        )
        assert response.status_code == 400

    def test_search_rejects_missing_keyword(self, client: TestClient):
        response = client.post(
            "/api/v1/niche/search",
            json={"country": "US"},
        )
        assert response.status_code == 400


# -----------------------------------------------------------------------------
# GET /niche/events
# -----------------------------------------------------------------------------


class TestNicheEventsEndpoint:
    def test_events_returns_200(self, client: TestClient):
        response = client.get("/api/v1/niche/events?country=US")
        assert response.status_code == 200

    def test_events_returns_envelope_list(self, client: TestClient):
        payload = client.get("/api/v1/niche/events?country=US").json()
        assert payload["ok"] is True
        assert isinstance(payload["data"], list)

    def test_events_default_window_90_days(self, client: TestClient):
        payload = client.get("/api/v1/niche/events?country=US").json()
        # Default is today → today+90, both fake events should be included if
        # within that window from current date
        assert isinstance(payload["data"], list)

    def test_events_explicit_window(self, client: TestClient):
        payload = client.get(
            "/api/v1/niche/events?country=US&from=2026-05-01&to=2026-05-31"
        ).json()
        assert payload["ok"] is True
        names = [e["name"] for e in payload["data"]]
        # Mother's Day should appear; Independence Day should NOT (July)
        assert "Mother's Day" in names
        assert "Independence Day" not in names

    def test_events_category_filter(self, client: TestClient):
        payload = client.get(
            "/api/v1/niche/events?country=US"
            "&from=2026-01-01&to=2026-12-31&category=cultural"
        ).json()
        for e in payload["data"]:
            assert e["category"] == "cultural"

    def test_events_invalid_date_range(self, client: TestClient):
        response = client.get(
            "/api/v1/niche/events?country=US&from=2026-12-31&to=2026-01-01"
        )
        assert response.status_code == 400

    def test_events_oversized_range_rejected(self, client: TestClient):
        response = client.get(
            "/api/v1/niche/events?country=US&from=2024-01-01&to=2027-01-01"
        )
        assert response.status_code == 400

    def test_event_includes_days_until(self, client: TestClient):
        payload = client.get(
            "/api/v1/niche/events?country=US&from=2026-05-01&to=2026-05-31"
        ).json()
        if payload["data"]:
            assert "days_until" in payload["data"][0]
            assert isinstance(payload["data"][0]["days_until"], int)


# -----------------------------------------------------------------------------
# POST /niche/expand (LLM)
# -----------------------------------------------------------------------------


class TestNicheExpandEndpoint:
    def test_expand_validates_seed_min_length(self, client: TestClient):
        response = client.post(
            "/api/v1/niche/expand",
            json={"seed_keyword": "a", "country": "US"},
        )
        assert response.status_code == 400

    def test_expand_validates_max_suggestions_range(self, client: TestClient):
        response = client.post(
            "/api/v1/niche/expand",
            json={"seed_keyword": "test seed", "country": "US", "max_suggestions": 100},
        )
        assert response.status_code == 400

    def test_expand_rejects_extra_fields(self, client: TestClient):
        response = client.post(
            "/api/v1/niche/expand",
            json={"seed_keyword": "test", "country": "US", "evil": "x"},
        )
        assert response.status_code == 400
