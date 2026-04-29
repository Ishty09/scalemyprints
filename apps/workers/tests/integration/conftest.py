"""
Integration test fixtures.

These tests spin up the real FastAPI app with fake TrademarkAPI clients,
exercising middleware, exception handlers, envelope wrapping, and routing
end-to-end.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from scalemyprints.app import create_app
from scalemyprints.core.config import get_settings
from scalemyprints.domain.trademark.enums import JurisdictionCode
from scalemyprints.domain.trademark.ports import TrademarkAPI, TrademarkSearchResult
from scalemyprints.domain.trademark.search_service import TrademarkSearchService
from scalemyprints.infrastructure.cache.memory import MemoryCache
from scalemyprints.infrastructure.common_law.no_op import NoOpCommonLawChecker
from scalemyprints.infrastructure.container import get_container


@dataclass
class FakeTrademarkAPI:
    """Fake TrademarkAPI for integration tests."""

    jurisdiction: JurisdictionCode
    records_to_return: list = field(default_factory=list)
    error_to_return: str | None = None
    call_count: int = 0

    async def search(
        self, phrase: str, nice_classes: list[int]
    ) -> TrademarkSearchResult:
        self.call_count += 1
        return TrademarkSearchResult(
            jurisdiction=self.jurisdiction,
            records=list(self.records_to_return),
            duration_ms=50,
            error=self.error_to_return,
        )


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure every integration test runs in TEST env with minimal config."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("INTERNAL_API_SECRET", "b" * 64)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret")
    monkeypatch.setenv("WORKER_CORS_ORIGINS", "http://localhost:3000")
    get_settings.cache_clear()
    get_container.cache_clear()


@pytest.fixture
def fake_apis() -> dict[JurisdictionCode, FakeTrademarkAPI]:
    """Fresh fake API set per test."""
    return {
        JurisdictionCode.US: FakeTrademarkAPI(jurisdiction=JurisdictionCode.US),
        JurisdictionCode.EU: FakeTrademarkAPI(jurisdiction=JurisdictionCode.EU),
        JurisdictionCode.AU: FakeTrademarkAPI(jurisdiction=JurisdictionCode.AU),
    }


@pytest.fixture
def app_with_fakes(fake_apis: dict[JurisdictionCode, FakeTrademarkAPI]):
    """Build the app and override the trademark search service with fakes."""
    app = create_app()

    # Build a service using the fakes
    def _override_service() -> TrademarkSearchService:
        return TrademarkSearchService(
            trademark_apis=fake_apis,
            cache=MemoryCache(),
            common_law_checker=NoOpCommonLawChecker(),
        )

    from scalemyprints.api.deps import get_trademark_search_service

    app.dependency_overrides[get_trademark_search_service] = _override_service
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app_with_fakes) -> Iterator[TestClient]:
    """Synchronous test client."""
    with TestClient(app_with_fakes) as client:
        yield client


@pytest.fixture
async def async_client(app_with_fakes) -> AsyncIterator[AsyncClient]:
    """Async test client for async-only endpoints."""
    transport = ASGITransport(app=app_with_fakes)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
