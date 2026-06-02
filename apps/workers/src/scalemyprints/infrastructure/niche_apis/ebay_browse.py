"""
eBay Browse API marketplace adapter — official OAuth2, free 5k/day.

eBay's Browse API is the modern OAuth2 replacement for Finding API,
serving the same listings catalog that powers ebay.com search. POD
products (mugs, t-shirts, stickers, posters) have strong overlap with
eBay's Home & Garden + Crafts + Clothing categories — perfect fallback
for Etsy data when scraping is blocked.

Auth flow:
  1. POST /identity/v1/oauth2/token with client_credentials grant
     - Body: grant_type=client_credentials&scope=https://api.ebay.com/oauth/api_scope
     - Auth: Basic <App-ID:Cert-ID>
  2. Receive Bearer token (TTL ~7200s)
  3. Cache token until ~60s before expiry; refresh on 401

Search request:
  GET /buy/browse/v1/item_summary/search?q=KEYWORD&limit=50&filter=...
  Headers: Authorization, X-EBAY-C-MARKETPLACE-ID, X-EBAY-C-ENDUSERCTX

Returns MarketplaceData with:
  - listing_count: total matching items
  - avg_price_usd: mean of sample prices
  - sample_listings_urls: first 5 itemWebUrl values
  - unique_sellers_estimate: count of distinct seller usernames in sample
"""

from __future__ import annotations

import asyncio
import time
from types import TracebackType
from typing import Any

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.niche.enums import Country
from scalemyprints.domain.niche.ports import MarketplaceData
from scalemyprints.infrastructure.trademark_apis.base import HttpClientFactory

logger = get_logger(__name__)


# eBay OAuth2 application-token scope for Browse API
_OAUTH_SCOPE = "https://api.ebay.com/oauth/api_scope"
_TOKEN_REFRESH_LEEWAY_SECONDS = 60.0
_DEFAULT_PAGE_SIZE = 50  # eBay max per page is 200, 50 is plenty for stats


# Country → eBay marketplace ID
_COUNTRY_MARKETPLACE: dict[Country, str] = {
    Country.US: "EBAY_US",
    Country.UK: "EBAY_GB",
    Country.AU: "EBAY_AU",
    Country.CA: "EBAY_CA",
    Country.DE: "EBAY_DE",
}

# Country → preferred currency for averaging prices
_COUNTRY_CURRENCY: dict[Country, str] = {
    Country.US: "USD",
    Country.UK: "GBP",
    Country.AU: "AUD",
    Country.CA: "CAD",
    Country.DE: "EUR",
}


class EbayBrowseAdapter:
    """eBay Browse API client (OAuth2 client-credentials)."""

    def __init__(
        self,
        *,
        app_id: str,
        cert_id: str,
        environment: str = "production",
        http_factory: HttpClientFactory | None = None,
        request_timeout_seconds: float = 12.0,
    ) -> None:
        if not app_id or not cert_id:
            raise ValueError("eBay app_id and cert_id are required")

        if environment == "sandbox":
            token_host = "https://api.sandbox.ebay.com"
            api_host = "https://api.sandbox.ebay.com"
        else:
            token_host = "https://api.ebay.com"
            api_host = "https://api.ebay.com"

        self._app_id = app_id
        self._cert_id = cert_id
        self._token_url = f"{token_host}/identity/v1/oauth2/token"
        self._api_base = api_host
        self._timeout = request_timeout_seconds

        factory = http_factory or HttpClientFactory()
        self._token_client = factory.build(base_url=token_host)
        self._api_client = factory.build(base_url=api_host)

        # Token cache
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def __aenter__(self) -> EbayBrowseAdapter:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._token_client.aclose()
        await self._api_client.aclose()

    # ------------------------------------------------------------------
    # OAuth2 token management
    # ------------------------------------------------------------------

    async def _get_token(self, *, force_refresh: bool = False) -> str:
        async with self._token_lock:
            now = time.monotonic()
            if (
                not force_refresh
                and self._access_token
                and now < self._token_expires_at - _TOKEN_REFRESH_LEEWAY_SECONDS
            ):
                return self._access_token

            response = await self._token_client.post(
                "/identity/v1/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "scope": _OAUTH_SCOPE,
                },
                auth=(self._app_id, self._cert_id),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            payload = response.json()

            access_token = payload.get("access_token")
            if not access_token:
                raise RuntimeError("eBay token response missing access_token")
            self._access_token = access_token
            self._token_expires_at = now + float(payload.get("expires_in", 7200))
            logger.info("ebay_token_refresh", expires_in=payload.get("expires_in"))
            return access_token

    # ------------------------------------------------------------------
    # MarketplaceProvider: fetch
    # ------------------------------------------------------------------

    async def fetch(self, keyword: str, country: Country) -> MarketplaceData:
        start = time.monotonic()
        log = logger.bind(service="ebay_browse", keyword=keyword, country=country.value)

        marketplace_id = _COUNTRY_MARKETPLACE.get(country, "EBAY_US")
        preferred_currency = _COUNTRY_CURRENCY.get(country, "USD")

        try:
            payload = await self._search_with_token_refresh(
                keyword=keyword,
                marketplace_id=marketplace_id,
            )
            duration_ms = int((time.monotonic() - start) * 1000)

            stats = _summarize(payload, preferred_currency=preferred_currency)
            log.info(
                "ebay_search_complete",
                listings=stats["listing_count"],
                samples=stats["sample_size"],
                avg_price=stats["avg_price"],
                duration_ms=duration_ms,
            )
            return MarketplaceData(
                listing_count=stats["listing_count"],
                unique_sellers_estimate=stats["unique_sellers"],
                avg_listing_age_days=None,  # not in summary endpoint
                avg_price_usd=stats["avg_price"],
                sample_listings_urls=stats["sample_urls"],
                sample_size=stats["sample_size"],
                duration_ms=duration_ms,
                error=None,
            )

        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            log.warning(
                "ebay_search_error",
                error=str(e)[:120],
                duration_ms=duration_ms,
            )
            return MarketplaceData(
                duration_ms=duration_ms,
                error=f"unexpected:{e.__class__.__name__}",
            )

    async def _search_with_token_refresh(
        self, *, keyword: str, marketplace_id: str,
    ) -> dict[str, Any]:
        token = await self._get_token()
        params = {
            "q": keyword,
            "limit": str(_DEFAULT_PAGE_SIZE),
            # Restrict to currently buyable items to match Etsy's "active listings"
            "filter": "buyingOptions:{FIXED_PRICE|AUCTION},itemLocationCountry:US",
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": marketplace_id,
            "Accept": "application/json",
        }
        response = await self._api_client.get(
            "/buy/browse/v1/item_summary/search",
            params=params,
            headers=headers,
            timeout=self._timeout,
        )
        if response.status_code == 401:
            # token may have expired between cache hit and request; refresh once
            token = await self._get_token(force_refresh=True)
            headers["Authorization"] = f"Bearer {token}"
            response = await self._api_client.get(
                "/buy/browse/v1/item_summary/search",
                params=params,
                headers=headers,
                timeout=self._timeout,
            )
        response.raise_for_status()
        return response.json()


# -----------------------------------------------------------------------------
# Pure helpers — easily testable
# -----------------------------------------------------------------------------


def _summarize(
    payload: dict[str, Any], *, preferred_currency: str
) -> dict[str, Any]:
    """Map an eBay item_summary/search payload → MarketplaceData fields."""
    total = payload.get("total")
    items = payload.get("itemSummaries") or []
    if not isinstance(items, list):
        items = []

    prices: list[float] = []
    seller_names: set[str] = set()
    sample_urls: list[str] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        price_obj = item.get("price")
        if isinstance(price_obj, dict):
            value = price_obj.get("value")
            currency = price_obj.get("currency")
            try:
                price_val = float(value) if value is not None else None
            except (TypeError, ValueError):
                price_val = None
            # Only include prices in the preferred currency to avoid mixing
            # GBP/EUR into a USD average. Acceptable filter, simpler than FX.
            if (
                price_val is not None
                and 1 < price_val < 500
                and currency == preferred_currency
            ):
                prices.append(price_val)

        seller = item.get("seller")
        if isinstance(seller, dict):
            username = seller.get("username")
            if isinstance(username, str) and username:
                seller_names.add(username)

        if len(sample_urls) < 5:
            url = item.get("itemWebUrl")
            if isinstance(url, str) and url.startswith("http"):
                sample_urls.append(url)

    avg_price = round(sum(prices) / len(prices), 2) if prices else None

    return {
        "listing_count": int(total) if isinstance(total, int) else None,
        "unique_sellers": len(seller_names) or None,
        "avg_price": avg_price,
        "sample_urls": sample_urls,
        "sample_size": len(prices),
    }
