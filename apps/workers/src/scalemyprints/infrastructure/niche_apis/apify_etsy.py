"""
Apify Etsy adapter — paid marketplace data via residential proxies.

Solves the problem the free Etsy public scraper hits:
- Etsy actively blocks scrapers (Cloudflare bot manager, 403 responses)
- Residential proxies + automatic CAPTCHA solving in Apify bypass this
- Works from any IP including Bangladesh ISPs (the proxy is the source)

This adapter implements the same MarketplaceProvider Protocol as
EtsyPublicSearchAdapter, so the container can swap them based on config.

Design choices:
- Uses epctex/etsy-scraper actor (most popular, $0.04-0.05 CU per 50 items)
- maxItems=30 to stay budget-friendly while giving enough sample for stats
- timeout_secs=180 — actors typically finish in 30-90s
- Returns same MarketplaceData shape so domain layer doesn't notice the swap
- Honors graceful-degradation contract: never raises, sets `error` instead

Cost model (epctex/etsy-scraper):
- ~$0.04-0.05 CU per 50 items
- $5 free credit ≈ ~100 searches at maxItems=30
- After credit: $25/1000 items ≈ $0.75 per 30-item search

Reference:
- https://apify.com/epctex/etsy-scraper
- https://docs.apify.com/api/client/python
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.niche.enums import Country
from scalemyprints.domain.niche.ports import MarketplaceData

logger = get_logger(__name__)


# Country → Etsy ship_to query param. Used in the URL we feed to the actor.
_COUNTRY_HINTS: dict[Country, str] = {
    Country.US: "US",
    Country.UK: "GB",
    Country.AU: "AU",
    Country.CA: "CA",
    Country.DE: "DE",
}


class ApifyEtsyAdapter:
    """
    Marketplace provider that runs Apify's epctex/etsy-scraper actor.

    Acquires structured listing data (title, price, listing URL, seller, etc.)
    bypassing Etsy's bot detection via Apify's residential proxy network.
    """

    def __init__(
        self,
        *,
        api_token: str,
        actor_id: str = "epctex/etsy-scraper",
        max_items_per_search: int = 30,
        actor_timeout_seconds: int = 180,
    ) -> None:
        if not api_token:
            raise ValueError("ApifyEtsyAdapter requires a non-empty api_token")
        self._api_token = api_token
        self._actor_id = actor_id
        self._max_items = max_items_per_search
        self._actor_timeout = actor_timeout_seconds

    async def fetch(self, keyword: str, country: Country) -> MarketplaceData:
        """
        Run the actor synchronously, parse its dataset, and return MarketplaceData.

        Never raises. Failures are returned as `error` strings so the orchestrator
        can mark the niche as `degraded=True` while still returning a usable record.
        """
        start = time.monotonic()
        log = logger.bind(
            service="apify_etsy",
            actor=self._actor_id,
            keyword=keyword,
            country=country.value,
        )

        # Imported lazily so the module loads even if apify-client isn't installed
        # (graceful behavior matches the rest of the codebase).
        try:
            from apify_client import ApifyClientAsync  # type: ignore[import-not-found]
        except ImportError:
            return MarketplaceData(
                duration_ms=0,
                error="apify_client_missing",
            )

        run_input = self._build_run_input(keyword, country)
        log.debug("apify_run_starting", input_max_items=self._max_items)

        client = ApifyClientAsync(token=self._api_token)
        try:
            actor_call = await client.actor(self._actor_id).call(
                run_input=run_input,
                timeout_secs=self._actor_timeout,
                # max_items caps spend on pay-per-result actors (defensive)
                max_items=self._max_items,
                # Suppress noisy actor-side logs in our worker logs
                logger=None,
            )

            if actor_call is None:
                duration_ms = int((time.monotonic() - start) * 1000)
                log.warning("apify_run_failed", duration_ms=duration_ms)
                return MarketplaceData(
                    duration_ms=duration_ms, error="apify_run_failed"
                )

            status = actor_call.get("status")
            dataset_id = actor_call.get("defaultDatasetId")

            if status != "SUCCEEDED" or not dataset_id:
                duration_ms = int((time.monotonic() - start) * 1000)
                log.warning(
                    "apify_run_unexpected_status",
                    status=status,
                    duration_ms=duration_ms,
                )
                return MarketplaceData(
                    duration_ms=duration_ms,
                    error=f"actor_status_{status or 'unknown'}",
                )

            # Fetch up to max_items records from the run's default dataset
            items: list[dict[str, Any]] = []
            async for item in client.dataset(dataset_id).iterate_items(
                limit=self._max_items, clean=True
            ):
                items.append(item)

            duration_ms = int((time.monotonic() - start) * 1000)
            parsed = _parse_apify_items(items)
            log.info(
                "apify_fetch_complete",
                fetched=len(items),
                avg_price=parsed["avg_price"],
                duration_ms=duration_ms,
            )

            return MarketplaceData(
                listing_count=parsed["listing_count"],
                unique_sellers_estimate=parsed["unique_sellers_estimate"],
                avg_listing_age_days=parsed["avg_listing_age_days"],
                avg_price_usd=parsed["avg_price"],
                sample_listings_urls=parsed["sample_urls"],
                sample_size=parsed["sample_size"],
                duration_ms=duration_ms,
                error=None,
            )

        except Exception as e:  # noqa: BLE001
            duration_ms = int((time.monotonic() - start) * 1000)
            log.warning(
                "apify_unexpected_error",
                error=str(e)[:160],
                error_type=e.__class__.__name__,
                duration_ms=duration_ms,
            )
            return MarketplaceData(
                duration_ms=duration_ms,
                error=f"unexpected:{e.__class__.__name__}",
            )

    def _build_run_input(self, keyword: str, country: Country) -> dict[str, Any]:
        """
        Translate (keyword, country) into the actor's input schema.

        The actor accepts:
        - `search`: keyword string (we use this primarily)
        - `startUrls`: explicit URLs (we use one for ship_to country hint)
        - `maxItems`: bounded for budget control
        - `endPage`: stop after page N (1 is enough for sample data)
        - `includeDescription`: false to reduce data transfer & cost
        - `proxy`: use Apify's residential proxy
        """
        ship_to = _COUNTRY_HINTS.get(country, "US")
        # Build a country-specific search URL as a hint for ship_to filtering
        # The actor will combine startUrls + search keyword
        start_url = (
            f"https://www.etsy.com/search?q={keyword.replace(' ', '+')}"
            f"&ship_to={ship_to}"
        )

        return {
            "search": keyword,
            "startUrls": [start_url],
            "maxItems": self._max_items,
            "endPage": 1,
            "includeDescription": False,
            "proxy": {"useApifyProxy": True},
        }


# -----------------------------------------------------------------------------
# Pure-function parsers — easy to unit test without HTTP
# -----------------------------------------------------------------------------


def _parse_apify_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Extract aggregate signals from a list of actor result items.

    Each item from epctex/etsy-scraper has approximately:
        {
            "url": "https://www.etsy.com/listing/...",
            "title": "Cool Dog Mom Mug",
            "price": {"amount": "24.99", "currencyCode": "USD"} | "24.99",
            "shop": {"name": "ShopName"} | "ShopName",
            "totalResults": 12345,        # search-result-page only
            "listingDate": "2024-03-15",  # optional
            ...
        }

    The schema varies slightly across actor versions; we extract defensively.
    """
    if not items:
        return {
            "listing_count": None,
            "unique_sellers_estimate": None,
            "avg_listing_age_days": None,
            "avg_price": None,
            "sample_urls": [],
            "sample_size": 0,
        }

    # Total result count — the actor often includes this on the first page item
    listing_count = _extract_total_results(items)

    prices = [p for p in (_extract_price(it) for it in items) if p is not None]
    sellers = {s for s in (_extract_seller(it) for it in items) if s}
    urls = _extract_urls(items)
    ages = [a for a in (_extract_listing_age_days(it) for it in items) if a is not None]

    avg_price = round(sum(prices) / len(prices), 2) if prices else None
    avg_age = round(sum(ages) / len(ages), 1) if ages else None

    # If the actor didn't surface totalResults, fall back to len(items) as a
    # lower bound — better than nothing for the scoring service.
    if listing_count is None and len(items) > 0:
        listing_count = len(items)

    # Estimate unique sellers from observed sellers in our sample, scaled up
    # by the same ratio observed in the sample.
    unique_sellers_estimate = _estimate_unique_sellers(
        observed_sellers=len(sellers),
        sample_size=len(items),
        total_listings=listing_count,
    )

    return {
        "listing_count": listing_count,
        "unique_sellers_estimate": unique_sellers_estimate,
        "avg_listing_age_days": avg_age,
        "avg_price": avg_price,
        "sample_urls": urls[:5],
        "sample_size": len(items),
    }


def _extract_total_results(items: Iterable[dict[str, Any]]) -> int | None:
    """Find totalResults on any item (some actor versions only set it on item[0])."""
    for it in items:
        total = it.get("totalResults") or it.get("total_results")
        if isinstance(total, int) and total > 0:
            return total
        if isinstance(total, str) and total.isdigit():
            return int(total)
    return None


def _extract_price(item: dict[str, Any]) -> float | None:
    """Pull a USD-equivalent price from an item (handles multiple shapes)."""
    raw = item.get("price")
    if raw is None:
        return None

    # Direct numeric
    if isinstance(raw, (int, float)):
        return float(raw) if 1 < float(raw) < 1000 else None

    # String "24.99"
    if isinstance(raw, str):
        try:
            value = float(raw.replace("$", "").replace(",", "").strip())
            return value if 1 < value < 1000 else None
        except ValueError:
            return None

    # Dict {"amount": "24.99", "currencyCode": "USD"}
    if isinstance(raw, dict):
        amount = raw.get("amount") or raw.get("value")
        currency = (raw.get("currencyCode") or raw.get("currency") or "USD").upper()
        if currency != "USD":
            return None  # skip non-USD; conversion adds complexity, sample size enough
        if isinstance(amount, (int, float)):
            return float(amount) if 1 < float(amount) < 1000 else None
        if isinstance(amount, str):
            try:
                value = float(amount.replace(",", "").strip())
                return value if 1 < value < 1000 else None
            except ValueError:
                return None

    return None


def _extract_seller(item: dict[str, Any]) -> str | None:
    """Pull seller/shop name (handles multiple shapes)."""
    shop = item.get("shop") or item.get("seller")
    if isinstance(shop, str):
        return shop.strip() or None
    if isinstance(shop, dict):
        name = shop.get("name") or shop.get("shopName")
        if isinstance(name, str):
            return name.strip() or None
    return None


def _extract_urls(items: Iterable[dict[str, Any]]) -> list[str]:
    """Extract listing URLs from a sequence of items, deduplicated, ordered."""
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        url = it.get("url") or it.get("listingUrl") or it.get("link")
        if isinstance(url, str) and url.startswith("https://www.etsy.com/listing/"):
            # Strip query string for cleanliness
            clean_url = url.split("?")[0]
            if clean_url not in seen:
                seen.add(clean_url)
                out.append(clean_url)
    return out


def _extract_listing_age_days(item: dict[str, Any]) -> int | None:
    """Extract listing age in days if available (varies by actor version)."""
    # Accept common field names
    age = (
        item.get("listingAgeDays")
        or item.get("ageDays")
        or item.get("listing_age_days")
    )
    if isinstance(age, (int, float)) and age >= 0:
        return int(age)
    return None


def _estimate_unique_sellers(
    *,
    observed_sellers: int,
    sample_size: int,
    total_listings: int | None,
) -> int | None:
    """
    Estimate unique sellers across the entire result set.

    If our sample of N listings comes from M unique sellers, scale that ratio
    onto the total population. Caps at total_listings (can't have more sellers
    than listings).
    """
    if observed_sellers == 0 or sample_size == 0 or total_listings is None:
        return None

    ratio = observed_sellers / sample_size
    estimated = int(total_listings * ratio)
    return max(1, min(estimated, total_listings))
