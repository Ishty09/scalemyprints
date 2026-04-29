"""HTTP-mocked tests for Etsy public adapter."""

from __future__ import annotations

import httpx
import pytest
import respx

from scalemyprints.domain.niche.enums import Country
from scalemyprints.infrastructure.niche_apis.etsy_public import (
    EtsyPublicSearchAdapter,
)


@pytest.fixture
async def adapter():
    a = EtsyPublicSearchAdapter()
    yield a
    await a.aclose()


class TestEtsyPublicAdapterHttp:
    @pytest.mark.asyncio
    async def test_happy_path_returns_data(self, adapter):
        sample_html = '''
        <html><body>
        <div data-search-count="500">
        <a href="https://www.etsy.com/listing/12345/dog-mom-shirt">Dog</a>
        <a href="https://www.etsy.com/listing/67890/cat-mom-mug">Cat</a>
        <span>$24.99</span>
        <span>$19.95</span>
        </body></html>
        '''
        with respx.mock(base_url="https://www.etsy.com") as mock:
            mock.get("/search").mock(
                return_value=httpx.Response(200, text=sample_html)
            )
            result = await adapter.fetch("dog mom", Country.US)

        assert result.error is None
        assert result.listing_count == 500
        assert result.avg_price_usd is not None
        assert len(result.sample_listings_urls) == 2

    @pytest.mark.asyncio
    async def test_403_returns_blocked_error(self, adapter):
        with respx.mock(base_url="https://www.etsy.com") as mock:
            mock.get("/search").mock(return_value=httpx.Response(403))
            result = await adapter.fetch("test", Country.US)

        assert result.error == "blocked_403"
        assert result.listing_count is None

    @pytest.mark.asyncio
    async def test_429_returns_blocked_error(self, adapter):
        with respx.mock(base_url="https://www.etsy.com") as mock:
            mock.get("/search").mock(return_value=httpx.Response(429))
            result = await adapter.fetch("test", Country.US)

        assert result.error == "blocked_429"

    @pytest.mark.asyncio
    async def test_500_returns_http_error(self, adapter):
        with respx.mock(base_url="https://www.etsy.com") as mock:
            mock.get("/search").mock(return_value=httpx.Response(500))
            result = await adapter.fetch("test", Country.US)

        assert result.error == "http_500"

    @pytest.mark.asyncio
    async def test_timeout_returns_timeout_error(self, adapter):
        with respx.mock(base_url="https://www.etsy.com") as mock:
            mock.get("/search").mock(side_effect=httpx.ReadTimeout("timeout"))
            result = await adapter.fetch("test", Country.US)

        assert result.error == "timeout"

    @pytest.mark.asyncio
    async def test_network_error_returns_unexpected(self, adapter):
        with respx.mock(base_url="https://www.etsy.com") as mock:
            mock.get("/search").mock(side_effect=httpx.ConnectError("nope"))
            result = await adapter.fetch("test", Country.US)

        assert result.error is not None
        assert result.error.startswith("unexpected:")

    @pytest.mark.asyncio
    async def test_passes_country_ship_to_param(self, adapter):
        with respx.mock(base_url="https://www.etsy.com") as mock:
            route = mock.get("/search").mock(return_value=httpx.Response(200, text=""))
            await adapter.fetch("test", Country.UK)

        assert route.called
        call = route.calls[0]
        # ship_to=GB for UK
        assert "ship_to=GB" in str(call.request.url)

    @pytest.mark.asyncio
    async def test_empty_html_returns_safe_defaults(self, adapter):
        with respx.mock(base_url="https://www.etsy.com") as mock:
            mock.get("/search").mock(return_value=httpx.Response(200, text=""))
            result = await adapter.fetch("test", Country.US)

        assert result.error is None
        assert result.listing_count is None
        assert result.avg_price_usd is None
