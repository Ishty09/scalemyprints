"""
Teepublic spy adapter.

Teepublic exposes product data via inline JSON-LD on every listing
page and as a `window.__APOLLO_STATE__` blob on search/shop pages.
We scrape via curl_cffi with chrome impersonation (no Apify
needed — Teepublic is not aggressively bot-protected).

URL patterns:
- Search:    /t-shirt/search?query=...&context=all
- Listing:   /t-shirt/{id}-{slug}
- Shop:      /user/{handle}
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
from scalemyprints.domain.spy.models import Listing, ShopProfile, SpyQuery
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


TEEPUBLIC_ID_RE = re.compile(r"/(?:t-shirt|sticker|tote|mug)/(?P<id>\d+)")
_JSONLD_RE = re.compile(
    r'<script\s+type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_APOLLO_STATE_RE = re.compile(
    r"window\.__APOLLO_STATE__\s*=\s*(\{.+?\});",
    re.DOTALL,
)


class TeepublicSpyAdapter(SpyMarketplaceAdapter):
    """curl_cffi + chrome124 impersonation scrape of Teepublic."""

    @property
    def marketplace(self) -> Marketplace:
        return Marketplace.TEEPUBLIC

    def __init__(
        self,
        *,
        proxy_url: str | None = None,
        timeout_seconds: float = 12.0,
    ) -> None:
        self._proxy_url = proxy_url
        self._timeout = timeout_seconds

    async def search(
        self,
        query: SpyQuery,
        *,
        limit: int = 20,
    ) -> MarketplaceSearchResult:
        start = time.monotonic()

        if query.listing_url is not None:
            m = TEEPUBLIC_ID_RE.search(str(query.listing_url))
            if m:
                detail = await self.fetch_listing(m.group("id"))
                if detail.listing:
                    return MarketplaceSearchResult(
                        marketplace=Marketplace.TEEPUBLIC,
                        listings=[detail.listing],
                        duration_ms=int((time.monotonic() - start) * 1000),
                    )
                return MarketplaceSearchResult(
                    marketplace=Marketplace.TEEPUBLIC,
                    error=detail.error or "listing_not_found",
                    duration_ms=int((time.monotonic() - start) * 1000),
                )

        if not query.text:
            return MarketplaceSearchResult(
                marketplace=Marketplace.TEEPUBLIC,
                error="empty_query",
                failure_reason=SpyFailureReason.INVALID_INPUT,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        url = f"https://www.teepublic.com/t-shirt/search?query={quote(query.text)}&context=all"
        html, err = await self._fetch(url)
        if err:
            return MarketplaceSearchResult(
                marketplace=Marketplace.TEEPUBLIC,
                error=err,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        listings = _parse_search(html, limit=limit)
        return MarketplaceSearchResult(
            marketplace=Marketplace.TEEPUBLIC,
            listings=listings,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    async def fetch_listing(self, external_id: str) -> ListingDetailResult:
        start = time.monotonic()
        url = f"https://www.teepublic.com/t-shirt/{external_id}"
        html, err = await self._fetch(url)
        if err:
            return ListingDetailResult(
                error=err,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        listing = _parse_listing(html, external_id, url)
        return ListingDetailResult(
            listing=listing,
            duration_ms=int((time.monotonic() - start) * 1000),
            error=None if listing else "could_not_parse",
        )

    async def fetch_shop(
        self,
        handle_or_id: str,
        *,
        depth: ShopAuditDepth = ShopAuditDepth.STANDARD,
    ) -> ShopFetchResult:
        start = time.monotonic()
        handle = handle_or_id.split("/")[-1]
        url = f"https://www.teepublic.com/user/{handle}"
        html, err = await self._fetch(url)
        if err:
            return ShopFetchResult(
                error=err,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        profile = _parse_shop(html, handle, url)
        listings = _parse_search(html, limit=24)  # listings inline on shop page
        return ShopFetchResult(
            profile=profile,
            listings=listings,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    async def _fetch(self, url: str) -> tuple[str, str | None]:
        try:
            from curl_cffi.requests import AsyncSession  # noqa: PLC0415
        except ImportError:
            import httpx  # noqa: PLC0415

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
                proxies=(
                    {"https": self._proxy_url, "http": self._proxy_url}
                    if self._proxy_url
                    else None
                ),
            ) as s:
                resp = await s.get(url, headers=rotating_headers(), allow_redirects=True)
                if resp.status_code in (403, 429):
                    return "", f"http_{resp.status_code}"
                if resp.status_code >= 400:
                    return "", f"http_{resp.status_code}"
                body = resp.text if hasattr(resp, "text") else resp.content.decode("utf-8", "ignore")
                return body, None
        except Exception as e:
            logger.warning("teepublic_fetch_failed", url=url, error=str(e))
            return "", f"fetch_failed: {e}"


# -----------------------------------------------------------------------------
# Parsers
# -----------------------------------------------------------------------------


def _parse_search(html: str, *, limit: int) -> list[Listing]:
    listings: list[Listing] = []
    now = datetime.now(UTC)

    m = _APOLLO_STATE_RE.search(html)
    if m:
        try:
            state = json.loads(m.group(1))
        except json.JSONDecodeError:
            state = None
        if isinstance(state, dict):
            # Apollo stores entities as keys like "Design:12345"
            for key, val in state.items():
                if not isinstance(val, dict) or not key.startswith("Design:"):
                    continue
                external_id = str(val.get("id") or key.split(":", 1)[1])
                title = val.get("title")
                if not isinstance(title, str):
                    continue
                slug = val.get("slug") or ""
                url = f"https://www.teepublic.com/t-shirt/{external_id}-{slug}"
                image = val.get("imageUrl") or val.get("squareImageUrl")
                price = safe_float(val.get("price"))
                handle = (val.get("user") or {}).get("username") if isinstance(val.get("user"), dict) else None
                try:
                    listings.append(
                        Listing(
                            marketplace=Marketplace.TEEPUBLIC,
                            external_id=external_id,
                            url=url,  # type: ignore[arg-type]
                            title=title[:400],
                            price_usd=price,
                            currency="USD",
                            thumbnail_url=image if isinstance(image, str) else None,  # type: ignore[arg-type]
                            shop_handle=handle if isinstance(handle, str) else None,
                            shop_url=(  # type: ignore[arg-type]
                                f"https://www.teepublic.com/user/{handle}" if handle else None
                            ),
                            status=ListingStatus.ACTIVE,
                            first_seen_at=now,
                            last_seen_at=now,
                        )
                    )
                except Exception:
                    continue
                if len(listings) >= limit:
                    return listings

    return listings


def _parse_listing(html: str, external_id: str, url: str) -> Listing | None:
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

        image = data.get("image")
        thumb: str | None = None
        if isinstance(image, str):
            thumb = image
        elif isinstance(image, list) and image:
            thumb = str(image[0])

        try:
            return Listing(
                marketplace=Marketplace.TEEPUBLIC,
                external_id=external_id,
                url=url,  # type: ignore[arg-type]
                title=str(data.get("name") or "")[:400],
                description=str(data.get("description") or "")[:4000] or None,
                price_usd=price if currency in (None, "USD") else None,
                currency=currency,
                thumbnail_url=thumb,  # type: ignore[arg-type]
                status=ListingStatus.ACTIVE,
                first_seen_at=now,
                last_seen_at=now,
            )
        except Exception:
            return None
    return None


def _parse_shop(html: str, handle: str, url: str) -> ShopProfile | None:
    now = datetime.now(UTC)
    display_name = handle
    sales: int | None = None

    name_match = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
    if name_match:
        display_name = name_match.group(1)

    sales_match = re.search(
        r"(\d[\d,]*)\s+designs?",
        html,
        re.IGNORECASE,
    )
    if sales_match:
        sales = safe_int(sales_match.group(1).replace(",", ""))

    try:
        return ShopProfile(
            marketplace=Marketplace.TEEPUBLIC,
            external_id=handle,
            handle=handle,
            display_name=display_name,
            url=url,  # type: ignore[arg-type]
            listings_count=sales,
            first_seen_at=now,
            last_seen_at=now,
        )
    except Exception:
        return None
