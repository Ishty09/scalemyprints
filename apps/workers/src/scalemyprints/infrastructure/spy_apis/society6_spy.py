"""
Society6 spy adapter.

Society6 embeds product data as `window.__INITIAL_STATE__ = {...}` on
every page. We pull that JSON tree generically (Society6 occasionally
reshapes their schema; we walk for any list of objects with
`id`+`title`+`previewImageUrl`).

URL patterns:
- Search:    /search?context=all&q=...
- Listing:   /product/{id}
- Shop:      /artist/{handle}
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


SOCIETY6_ID_RE = re.compile(r"/product/(?P<id>\d+)")
_INITIAL_STATE_RE = re.compile(
    r"window\.__INITIAL_STATE__\s*=\s*(\{.+?\});",
    re.DOTALL,
)


class Society6SpyAdapter(SpyMarketplaceAdapter):
    """Society6 search + listing + shop scrape."""

    @property
    def marketplace(self) -> Marketplace:
        return Marketplace.SOCIETY6

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
            m = SOCIETY6_ID_RE.search(str(query.listing_url))
            if m:
                detail = await self.fetch_listing(m.group("id"))
                if detail.listing:
                    return MarketplaceSearchResult(
                        marketplace=Marketplace.SOCIETY6,
                        listings=[detail.listing],
                        duration_ms=int((time.monotonic() - start) * 1000),
                    )
                return MarketplaceSearchResult(
                    marketplace=Marketplace.SOCIETY6,
                    error=detail.error or "listing_not_found",
                    duration_ms=int((time.monotonic() - start) * 1000),
                )

        if not query.text:
            return MarketplaceSearchResult(
                marketplace=Marketplace.SOCIETY6,
                error="empty_query",
                failure_reason=SpyFailureReason.INVALID_INPUT,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        url = f"https://society6.com/search?context=all&q={quote(query.text)}"
        html, err = await self._fetch(url)
        if err:
            return MarketplaceSearchResult(
                marketplace=Marketplace.SOCIETY6,
                error=err,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        listings = _parse_search(html, limit=limit)
        return MarketplaceSearchResult(
            marketplace=Marketplace.SOCIETY6,
            listings=listings,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    async def fetch_listing(self, external_id: str) -> ListingDetailResult:
        start = time.monotonic()
        url = f"https://society6.com/product/{external_id}"
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
        url = f"https://society6.com/artist/{handle}"
        html, err = await self._fetch(url)
        if err:
            return ShopFetchResult(
                error=err,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        profile = _parse_shop(html, handle, url)
        listings = _parse_search(html, limit=24)
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
            logger.warning("society6_fetch_failed", url=url, error=str(e))
            return "", f"fetch_failed: {e}"


# -----------------------------------------------------------------------------
# Parsers
# -----------------------------------------------------------------------------


def _parse_search(html: str, *, limit: int) -> list[Listing]:
    listings: list[Listing] = []
    now = datetime.now(UTC)

    m = _INITIAL_STATE_RE.search(html)
    if not m:
        return listings
    try:
        state = json.loads(m.group(1))
    except json.JSONDecodeError:
        return listings

    seen: set[str] = set()

    def _recur(node: object) -> None:
        if len(listings) >= limit:
            return
        if isinstance(node, dict):
            pid = node.get("id") or node.get("artworkId") or node.get("productId")
            title = node.get("title") or node.get("artworkTitle")
            image = (
                node.get("previewImageUrl")
                or node.get("imageUrl")
                or node.get("image")
            )
            if (
                isinstance(pid, (str, int))
                and isinstance(title, str)
                and isinstance(image, str)
            ):
                eid = str(pid)
                if eid in seen:
                    return
                seen.add(eid)
                handle = (node.get("artist") or {}).get("username") if isinstance(node.get("artist"), dict) else None
                price = safe_float(node.get("price"))
                try:
                    listings.append(
                        Listing(
                            marketplace=Marketplace.SOCIETY6,
                            external_id=eid,
                            url=f"https://society6.com/product/{eid}",  # type: ignore[arg-type]
                            title=title[:400],
                            price_usd=price,
                            currency="USD",
                            thumbnail_url=image,  # type: ignore[arg-type]
                            shop_handle=handle if isinstance(handle, str) else None,
                            shop_url=(  # type: ignore[arg-type]
                                f"https://society6.com/artist/{handle}" if handle else None
                            ),
                            status=ListingStatus.ACTIVE,
                            first_seen_at=now,
                            last_seen_at=now,
                        )
                    )
                except Exception:
                    pass
                return
            for v in node.values():
                _recur(v)
        elif isinstance(node, list):
            for el in node:
                _recur(el)

    _recur(state)
    return listings


def _parse_listing(html: str, external_id: str, url: str) -> Listing | None:
    listings = _parse_search(html, limit=5)
    for l in listings:
        if l.external_id == external_id:
            return l
    if listings:
        return listings[0]
    return None


def _parse_shop(html: str, handle: str, url: str) -> ShopProfile | None:
    now = datetime.now(UTC)
    display_name = handle

    name_match = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
    if name_match:
        display_name = name_match.group(1)

    works: int | None = None
    works_match = re.search(r"(\d[\d,]*)\s+(?:works?|designs?)", html, re.IGNORECASE)
    if works_match:
        works = safe_int(works_match.group(1).replace(",", ""))

    try:
        return ShopProfile(
            marketplace=Marketplace.SOCIETY6,
            external_id=handle,
            handle=handle,
            display_name=display_name,
            url=url,  # type: ignore[arg-type]
            listings_count=works,
            first_seen_at=now,
            last_seen_at=now,
        )
    except Exception:
        return None
