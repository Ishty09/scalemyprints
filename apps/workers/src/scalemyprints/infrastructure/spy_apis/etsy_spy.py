"""
Etsy spy adapter.

Returns marketplace listings + shop profiles for ScaleMyPrints Spy.
Wraps the existing curl_cffi-backed Etsy HTML scraper (already proven
in the niche pipeline) with the SpyMarketplaceAdapter contract.

Search strategy:
- text query → /search?q=...&ref=search_bar
- listing URL → extract canonical ID from /listing/{id}/... slug
- shop fetch → /shop/{handle} HTML scrape

We never raise — failures land in MarketplaceSearchResult.error. Etsy
aggressively rate-limits scrapers from datacenter IPs; 403/429 returns
an error string the orchestrator can surface to the user.
"""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from urllib.parse import quote

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.enums import (
    ListingStatus,
    Marketplace,
    ShopAuditDepth,
    SpyFailureReason,
)
from scalemyprints.domain.spy.models import (
    Listing,
    ShopProfile,
    SpyQuery,
)
from scalemyprints.domain.spy.ports import (
    ListingDetailResult,
    MarketplaceSearchResult,
    ShopFetchResult,
    SpyMarketplaceAdapter,
)
from scalemyprints.infrastructure.spy_apis.base import (
    rotating_headers,
    safe_float,
    safe_int,
)

logger = get_logger(__name__)


ETSY_LISTING_RE = re.compile(r"/listing/(?P<id>\d+)(?:/|$)")
ETSY_SHOP_RE = re.compile(r"/shop/(?P<handle>[A-Za-z0-9_-]+)(?:/|$)")


class EtsySpyAdapter(SpyMarketplaceAdapter):
    """curl_cffi-backed Etsy spy adapter."""

    @property
    def marketplace(self) -> Marketplace:
        return Marketplace.ETSY

    def __init__(
        self,
        *,
        country: str = "US",
        proxy_url: str | None = None,
        timeout_seconds: float = 12.0,
    ) -> None:
        self._country = country
        self._proxy_url = proxy_url
        self._timeout = timeout_seconds

    # ----- Search ---------------------------------------------------------

    async def search(
        self,
        query: SpyQuery,
        *,
        limit: int = 20,
    ) -> MarketplaceSearchResult:
        start = time.monotonic()

        # If they passed a URL, treat it as a single-listing lookup
        if query.listing_url is not None:
            external_id = _extract_listing_id(str(query.listing_url))
            if external_id is None:
                return MarketplaceSearchResult(
                    marketplace=Marketplace.ETSY,
                    error="not_an_etsy_listing_url",
                    failure_reason=SpyFailureReason.INVALID_INPUT,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            detail = await self.fetch_listing(external_id)
            if detail.error or detail.listing is None:
                return MarketplaceSearchResult(
                    marketplace=Marketplace.ETSY,
                    error=detail.error or "listing_not_found",
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            return MarketplaceSearchResult(
                marketplace=Marketplace.ETSY,
                listings=[detail.listing],
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        if not query.text:
            return MarketplaceSearchResult(
                marketplace=Marketplace.ETSY,
                error="empty_query",
                failure_reason=SpyFailureReason.INVALID_INPUT,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        url = (
            f"https://www.etsy.com/search?q={quote(query.text)}"
            f"&ship_to={self._country}&order=most_relevant"
        )

        html, err = await self._fetch_html(url)
        if err:
            return MarketplaceSearchResult(
                marketplace=Marketplace.ETSY,
                error=err,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        listings = _parse_search_results(html, limit=limit)
        return MarketplaceSearchResult(
            marketplace=Marketplace.ETSY,
            listings=listings,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    # ----- Listing detail -------------------------------------------------

    async def fetch_listing(self, external_id: str) -> ListingDetailResult:
        start = time.monotonic()
        url = f"https://www.etsy.com/listing/{external_id}/"

        html, err = await self._fetch_html(url)
        if err:
            return ListingDetailResult(
                error=err,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        listing = _parse_listing_detail(html, external_id, url)
        return ListingDetailResult(
            listing=listing,
            duration_ms=int((time.monotonic() - start) * 1000),
            error=None if listing else "could_not_parse_listing",
        )

    # ----- Shop fetch -----------------------------------------------------

    async def fetch_shop(
        self,
        handle_or_id: str,
        *,
        depth: ShopAuditDepth = ShopAuditDepth.STANDARD,
    ) -> ShopFetchResult:
        start = time.monotonic()

        handle = _extract_shop_handle(handle_or_id) or handle_or_id
        url = f"https://www.etsy.com/shop/{handle}"

        html, err = await self._fetch_html(url)
        if err:
            return ShopFetchResult(
                error=err,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        profile = _parse_shop_profile(html, handle, url)
        # Phase 1: don't fetch shop listings here (expensive). Phase 2
        # adds full crawl with `depth`.
        return ShopFetchResult(
            profile=profile,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    # ----- HTTP helper ----------------------------------------------------

    async def _fetch_html(self, url: str) -> tuple[str, str | None]:
        """Fetch URL via curl_cffi w/ TLS impersonation. Returns (body, error)."""
        try:
            from curl_cffi.requests import AsyncSession
        except ImportError:
            # Fallback to httpx
            import httpx

            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout, follow_redirects=True
                ) as c:
                    resp = await c.get(url, headers=rotating_headers())
                    if resp.status_code in (403, 429):
                        return "", f"http_{resp.status_code}"
                    resp.raise_for_status()
                    return resp.text, None
            except Exception as e:
                return "", f"httpx_failed: {e}"

        try:
            async with AsyncSession(
                impersonate="chrome124",
                timeout=self._timeout,
                proxies={"https": self._proxy_url, "http": self._proxy_url}
                if self._proxy_url
                else None,
            ) as s:
                resp = await s.get(url, headers=rotating_headers(), allow_redirects=True)
                if resp.status_code in (403, 429):
                    logger.info("etsy_spy_blocked", status=resp.status_code, url=url)
                    return "", f"http_{resp.status_code}"
                if resp.status_code >= 400:
                    return "", f"http_{resp.status_code}"
                # curl_cffi returns bytes
                body = resp.text if hasattr(resp, "text") else resp.content.decode("utf-8", "ignore")
                return body, None
        except Exception as e:
            logger.warning("etsy_spy_fetch_failed", url=url, error=str(e))
            return "", f"fetch_failed: {e}"


# -----------------------------------------------------------------------------
# Parsers — pulled out to keep the adapter focused on I/O
# -----------------------------------------------------------------------------


_JSONLD_RE = re.compile(
    r'<script\s+type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def _parse_search_results(html: str, *, limit: int) -> list[Listing]:
    """
    Parse Etsy search results page.

    Etsy embeds search hits as JSON-LD `ItemList` and also as inline
    React data. We try JSON-LD first (most stable), then fall back to
    HTML attribute scraping.
    """
    listings: list[Listing] = []
    now = datetime.now(UTC)

    for block in _JSONLD_RE.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue

        items = []
        if isinstance(data, dict) and data.get("@type") in ("ItemList", "Product"):
            items.append(data) if data.get("@type") == "Product" else items.extend(
                data.get("itemListElement") or []
            )
        for el in items:
            if isinstance(el, dict) and "item" in el:
                el = el["item"]
            if not isinstance(el, dict):
                continue
            url = el.get("url") or ""
            if not isinstance(url, str) or "/listing/" not in url:
                continue
            external = _extract_listing_id(url)
            if not external:
                continue
            offers = el.get("offers") or {}
            price = None
            currency = None
            if isinstance(offers, dict):
                price = safe_float(offers.get("price"))
                currency = offers.get("priceCurrency") if isinstance(offers, dict) else None
            try:
                listings.append(
                    Listing(
                        marketplace=Marketplace.ETSY,
                        external_id=external,
                        url=url,  # type: ignore[arg-type]
                        title=str(el.get("name") or "")[:400],
                        thumbnail_url=el.get("image") if isinstance(el.get("image"), str) else None,
                        price_usd=price if currency in (None, "USD") else None,
                        currency=currency,
                        status=ListingStatus.ACTIVE,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
            except Exception:  # pydantic validation can choke on bad inputs
                continue
            if len(listings) >= limit:
                return listings

    return listings


def _parse_listing_detail(html: str, external_id: str, url: str) -> Listing | None:
    """
    Parse a single-listing page.

    JSON-LD `Product` block contains everything we need.
    """
    now = datetime.now(UTC)
    for block in _JSONLD_RE.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or data.get("@type") != "Product":
            continue

        offers = data.get("offers") or {}
        price = None
        currency = None
        if isinstance(offers, dict):
            price = safe_float(offers.get("price"))
            currency = offers.get("priceCurrency")
        elif isinstance(offers, list) and offers:
            first = offers[0]
            price = safe_float(first.get("price"))
            currency = first.get("priceCurrency")

        agg = data.get("aggregateRating") or {}
        rating = safe_float(agg.get("ratingValue")) if isinstance(agg, dict) else None
        reviews = safe_int(agg.get("reviewCount")) if isinstance(agg, dict) else None

        image = data.get("image")
        images: list[str] = []
        if isinstance(image, str):
            images = [image]
        elif isinstance(image, list):
            images = [str(x) for x in image if isinstance(x, str)]

        try:
            return Listing(
                marketplace=Marketplace.ETSY,
                external_id=external_id,
                url=url,  # type: ignore[arg-type]
                title=str(data.get("name") or "")[:400],
                description=str(data.get("description") or "")[:4000] or None,
                price_usd=price if currency in (None, "USD") else None,
                currency=currency,
                thumbnail_url=images[0] if images else None,  # type: ignore[arg-type]
                image_urls=images,  # type: ignore[arg-type]
                rating=rating if rating is not None and 0.0 <= rating <= 5.0 else None,
                reviews_count=reviews,
                status=ListingStatus.ACTIVE,
                first_seen_at=now,
                last_seen_at=now,
            )
        except Exception:
            return None

    return None


def _parse_shop_profile(html: str, handle: str, url: str) -> ShopProfile | None:
    """
    Minimal shop profile parser — display name + best-effort sales count.

    Phase 2 will add joined-year, location, reviews, etc.
    """
    now = datetime.now(UTC)

    name_match = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
    display_name = name_match.group(1) if name_match else handle

    sales: int | None = None
    sales_match = re.search(
        r'"shop_sales"\s*:\s*(\d+)|>([\d,]+)\s*sales?<',
        html,
        re.IGNORECASE,
    )
    if sales_match:
        raw = sales_match.group(1) or sales_match.group(2) or ""
        sales = safe_int(raw.replace(",", "")) if raw else None

    try:
        return ShopProfile(
            marketplace=Marketplace.ETSY,
            external_id=handle,
            handle=handle,
            display_name=display_name,
            url=url,  # type: ignore[arg-type]
            total_sales=sales,
            first_seen_at=now,
            last_seen_at=now,
        )
    except Exception:
        return None


def _extract_listing_id(url: str) -> str | None:
    m = ETSY_LISTING_RE.search(url)
    return m.group("id") if m else None


def _extract_shop_handle(url_or_handle: str) -> str | None:
    m = ETSY_SHOP_RE.search(url_or_handle)
    return m.group("handle") if m else None
