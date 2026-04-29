"""
Etsy public search adapter — free marketplace data.

Etsy doesn't expose a public REST API for non-affiliated developers
(their API is partner-only). But Etsy's search results page is HTML
that we can parse for:
- Total listing count for a keyword
- Sample listing URLs
- Price ranges from visible cards

This is a "best effort" free adapter. Apify (paid) provides cleaner
data but costs $49/mo. We use this for Phase 1 free build.

Etsy may rate-limit aggressive requests. We:
- Use realistic browser headers
- Respect robots.txt logically (one request per search)
- Cap to 1 search per keyword per 6 hours via cache
- Graceful degrade on 403/429
"""

from __future__ import annotations

import re
import time
from types import TracebackType

import httpx

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.niche.enums import Country
from scalemyprints.domain.niche.ports import MarketplaceData
from scalemyprints.infrastructure.trademark_apis.base import HttpClientFactory

logger = get_logger(__name__)


ETSY_SEARCH_URL = "https://www.etsy.com/search"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Country → Etsy search hint (ship-to filter, approximated)
_COUNTRY_HINTS: dict[Country, str] = {
    Country.US: "US",
    Country.UK: "GB",
    Country.AU: "AU",
    Country.CA: "CA",
    Country.DE: "DE",
}


# Patterns used to extract data from Etsy search HTML
# Etsy DOM changes occasionally — we use multiple fallback patterns
_LISTING_COUNT_PATTERNS = (
    re.compile(r'data-search-count="(\d[\d,]*)"', re.IGNORECASE),
    re.compile(r'>(\d[\d,]+)\s+results?\s+for', re.IGNORECASE),
    re.compile(r'"listingResultsCount":\s*(\d+)', re.IGNORECASE),
)
_PRICE_PATTERN = re.compile(r'\$([\d.]+)(?:\s|<)')
_LISTING_URL_PATTERN = re.compile(
    r'href="(https://www\.etsy\.com/listing/\d+/[^"?]+)(?:\?[^"]*)?"'
)


class EtsyPublicSearchAdapter:
    """Best-effort free Etsy marketplace data via public search page."""

    def __init__(
        self,
        *,
        http_factory: HttpClientFactory | None = None,
        client: httpx.AsyncClient | None = None,
        request_timeout_seconds: float = 10.0,
    ) -> None:
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            factory = http_factory or HttpClientFactory()
            self._client = factory.build(
                base_url="https://www.etsy.com",
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            self._owns_client = True
        self._timeout = request_timeout_seconds

    async def __aenter__(self) -> "EtsyPublicSearchAdapter":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch(self, keyword: str, country: Country) -> MarketplaceData:
        start = time.monotonic()
        log = logger.bind(service="etsy_public", keyword=keyword, country=country.value)

        try:
            params = {
                "q": keyword,
                "ship_to": _COUNTRY_HINTS.get(country, "US"),
            }
            response = await self._client.get(
                "/search", params=params, timeout=self._timeout
            )
            duration_ms = int((time.monotonic() - start) * 1000)

            if response.status_code in (403, 429):
                log.warning("etsy_blocked", status=response.status_code)
                return MarketplaceData(
                    duration_ms=duration_ms,
                    error=f"blocked_{response.status_code}",
                )
            if response.status_code != 200:
                log.warning("etsy_http_error", status=response.status_code)
                return MarketplaceData(
                    duration_ms=duration_ms,
                    error=f"http_{response.status_code}",
                )

            html = response.text
            parsed = _parse_etsy_html(html)
            log.info(
                "etsy_fetch_complete",
                listings=parsed["listing_count"],
                samples=len(parsed["sample_urls"]),
                duration_ms=duration_ms,
            )

            return MarketplaceData(
                listing_count=parsed["listing_count"],
                unique_sellers_estimate=parsed["unique_sellers_estimate"],
                avg_listing_age_days=None,  # not available from public page
                avg_price_usd=parsed["avg_price"],
                sample_listings_urls=parsed["sample_urls"],
                sample_size=parsed["sample_size"],
                duration_ms=duration_ms,
                error=None,
            )

        except (httpx.TimeoutException, httpx.ReadTimeout):
            duration_ms = int((time.monotonic() - start) * 1000)
            log.warning("etsy_timeout", duration_ms=duration_ms)
            return MarketplaceData(duration_ms=duration_ms, error="timeout")
        except Exception as e:  # noqa: BLE001
            duration_ms = int((time.monotonic() - start) * 1000)
            log.warning("etsy_error", error=str(e)[:120], duration_ms=duration_ms)
            return MarketplaceData(
                duration_ms=duration_ms,
                error=f"unexpected:{e.__class__.__name__}",
            )


# -----------------------------------------------------------------------------
# HTML parsing helpers — pure functions, easily testable
# -----------------------------------------------------------------------------


def _parse_etsy_html(html: str) -> dict:
    """Extract structured data from Etsy search HTML."""
    listing_count = _extract_listing_count(html)
    sample_urls = _extract_listing_urls(html)
    prices = _extract_prices(html)

    avg_price = None
    if prices:
        avg_price = round(sum(prices) / len(prices), 2)

    # Rough heuristic: 70-80% of unique listings come from unique sellers
    # in moderate-competition niches. Without seller data we approximate.
    unique_sellers_estimate = None
    if listing_count is not None and listing_count > 0:
        if listing_count < 50:
            unique_sellers_estimate = listing_count  # likely 1:1
        elif listing_count < 1000:
            unique_sellers_estimate = int(listing_count * 0.75)
        else:
            unique_sellers_estimate = int(listing_count * 0.50)

    return {
        "listing_count": listing_count,
        "unique_sellers_estimate": unique_sellers_estimate,
        "avg_price": avg_price,
        "sample_urls": sample_urls[:5],
        "sample_size": len(prices),
    }


def _extract_listing_count(html: str) -> int | None:
    for pattern in _LISTING_COUNT_PATTERNS:
        match = pattern.search(html)
        if match:
            try:
                count_str = match.group(1).replace(",", "")
                return int(count_str)
            except ValueError:
                continue
    return None


def _extract_listing_urls(html: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for match in _LISTING_URL_PATTERN.finditer(html):
        url = match.group(1)
        if url not in seen:
            seen.add(url)
            urls.append(url)
        if len(urls) >= 20:
            break
    return urls


def _extract_prices(html: str) -> list[float]:
    prices: list[float] = []
    for match in _PRICE_PATTERN.finditer(html):
        try:
            price = float(match.group(1))
            # Filter sane price range for POD ($1-$200)
            if 1 < price < 200:
                prices.append(price)
        except ValueError:
            continue
        if len(prices) >= 30:  # cap sample size
            break
    return prices
