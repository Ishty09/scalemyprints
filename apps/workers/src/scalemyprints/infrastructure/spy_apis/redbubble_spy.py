"""
Redbubble spy adapter.

Redbubble is more scrape-friendly than Etsy/Amazon — they don't deploy
Akamai or aggressive CF challenges. curl_cffi w/ chrome impersonation
typically gets through from datacenter IPs.

Approach:
- Search:    GET /shop/{quoted_query}?iaCode=u-tee
- Listing:   GET /people/{handle}/works/{work_id}-{slug}
- Shop:      GET /people/{handle}/shop

Their HTML embeds results as `window.__INITIAL_STATE__ = {...}` JSON
which is much easier to parse than raw HTML.
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


INITIAL_STATE_RE = re.compile(
    r"window\.__INITIAL_STATE__\s*=\s*(\{.+?\});",
    re.DOTALL,
)
REDBUBBLE_WORK_RE = re.compile(
    r"/people/(?P<handle>[A-Za-z0-9_-]+)/works/(?P<id>\d+)",
)


class RedbubbleSpyAdapter(SpyMarketplaceAdapter):
    """Redbubble search + listing + shop adapter."""

    @property
    def marketplace(self) -> Marketplace:
        return Marketplace.REDBUBBLE

    def __init__(
        self,
        *,
        proxy_url: str | None = None,
        timeout_seconds: float = 12.0,
    ) -> None:
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

        if query.listing_url is not None:
            m = REDBUBBLE_WORK_RE.search(str(query.listing_url))
            if m:
                detail = await self.fetch_listing(m.group("id"))
                if detail.listing:
                    return MarketplaceSearchResult(
                        marketplace=Marketplace.REDBUBBLE,
                        listings=[detail.listing],
                        duration_ms=int((time.monotonic() - start) * 1000),
                    )
                return MarketplaceSearchResult(
                    marketplace=Marketplace.REDBUBBLE,
                    error=detail.error or "listing_not_found",
                    duration_ms=int((time.monotonic() - start) * 1000),
                )

        if not query.text:
            return MarketplaceSearchResult(
                marketplace=Marketplace.REDBUBBLE,
                error="empty_query",
                failure_reason=SpyFailureReason.INVALID_INPUT,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        url = f"https://www.redbubble.com/shop/{quote(query.text)}?iaCode=u-tee"
        html, err = await self._fetch(url)
        if err:
            return MarketplaceSearchResult(
                marketplace=Marketplace.REDBUBBLE,
                error=err,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        listings = _parse_search(html, limit=limit)
        return MarketplaceSearchResult(
            marketplace=Marketplace.REDBUBBLE,
            listings=listings,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    async def fetch_listing(self, external_id: str) -> ListingDetailResult:
        start = time.monotonic()
        # Redbubble URLs need both handle and id; if we only have id we
        # fall through to a search by id (best-effort).
        url = f"https://www.redbubble.com/shop/work/{external_id}"
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
        handle = handle_or_id.rsplit("/", maxsplit=1)[-1]
        url = f"https://www.redbubble.com/people/{handle}/shop"
        html, err = await self._fetch(url)
        if err:
            return ShopFetchResult(
                error=err,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        profile = _parse_shop(html, handle, url)
        return ShopFetchResult(
            profile=profile,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    # ----- HTTP -----------------------------------------------------------

    async def _fetch(self, url: str) -> tuple[str, str | None]:
        try:
            from curl_cffi.requests import AsyncSession
        except ImportError:
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
                    return "", f"http_{resp.status_code}"
                if resp.status_code >= 400:
                    return "", f"http_{resp.status_code}"
                body = resp.text if hasattr(resp, "text") else resp.content.decode("utf-8", "ignore")
                return body, None
        except Exception as e:
            logger.warning("redbubble_fetch_failed", url=url, error=str(e))
            return "", f"fetch_failed: {e}"


# -----------------------------------------------------------------------------
# Parsers
# -----------------------------------------------------------------------------


def _parse_search(html: str, *, limit: int) -> list[Listing]:
    now = datetime.now(UTC)
    listings: list[Listing] = []

    m = INITIAL_STATE_RE.search(html)
    if not m:
        return listings

    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return listings

    # Walk a few likely paths into the state for search results.
    candidates: list[dict[str, object]] = []
    for key_path in (
        ("searchPage", "works"),
        ("search", "results"),
        ("works", "items"),
    ):
        cur: object = data
        for k in key_path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                cur = None
                break
        if isinstance(cur, list):
            candidates = [w for w in cur if isinstance(w, dict)]
            break

    for w in candidates[:limit]:
        external_id = str(w.get("id") or w.get("workId") or "")
        handle = w.get("artistUsername") or w.get("artist") or ""
        title = w.get("title") or ""
        if not external_id or not isinstance(title, str):
            continue
        url = (
            f"https://www.redbubble.com/people/{handle}/works/{external_id}"
            if handle else f"https://www.redbubble.com/shop/work/{external_id}"
        )
        thumb = (
            w.get("imageUrl")
            or w.get("imageDataUrl")
            or (w.get("image") if isinstance(w.get("image"), str) else None)
        )
        price = safe_float((w.get("price") or {}).get("amount") if isinstance(w.get("price"), dict) else w.get("price"))

        try:
            listings.append(
                Listing(
                    marketplace=Marketplace.REDBUBBLE,
                    external_id=external_id,
                    url=url,  # type: ignore[arg-type]
                    title=title[:400],
                    price_usd=price,
                    currency="USD",
                    thumbnail_url=thumb if isinstance(thumb, str) else None,  # type: ignore[arg-type]
                    shop_handle=str(handle) if handle else None,
                    shop_url=(  # type: ignore[arg-type]
                        f"https://www.redbubble.com/people/{handle}/shop" if handle else None
                    ),
                    status=ListingStatus.ACTIVE,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        except Exception:
            continue

    return listings


def _parse_listing(html: str, external_id: str, url: str) -> Listing | None:
    now = datetime.now(UTC)
    m = INITIAL_STATE_RE.search(html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None

    # Best-effort: search nested for an entry whose id matches
    target = _find_work_node(data, external_id)
    if not isinstance(target, dict):
        return None

    title = target.get("title") or ""
    if not isinstance(title, str):
        return None
    handle = target.get("artistUsername") or target.get("artist") or None
    thumb = target.get("imageUrl") or target.get("imageDataUrl")
    price = safe_float((target.get("price") or {}).get("amount") if isinstance(target.get("price"), dict) else target.get("price"))
    description = str(target.get("description") or "")[:4000] or None

    try:
        return Listing(
            marketplace=Marketplace.REDBUBBLE,
            external_id=external_id,
            url=url,  # type: ignore[arg-type]
            title=title[:400],
            description=description,
            price_usd=price,
            currency="USD",
            thumbnail_url=thumb if isinstance(thumb, str) else None,  # type: ignore[arg-type]
            shop_handle=str(handle) if handle else None,
            shop_url=(  # type: ignore[arg-type]
                f"https://www.redbubble.com/people/{handle}/shop" if handle else None
            ),
            status=ListingStatus.ACTIVE,
            first_seen_at=now,
            last_seen_at=now,
        )
    except Exception:
        return None


def _parse_shop(html: str, handle: str, url: str) -> ShopProfile | None:
    now = datetime.now(UTC)
    m = INITIAL_STATE_RE.search(html)

    display_name = handle
    location: str | None = None
    sales: int | None = None
    listings_count: int | None = None

    if m:
        try:
            data = json.loads(m.group(1))
            artist = _find_artist_node(data, handle)
            if isinstance(artist, dict):
                if isinstance(artist.get("displayName"), str):
                    display_name = artist["displayName"]
                if isinstance(artist.get("location"), str):
                    location = artist["location"]
                sales = safe_int(artist.get("salesCount"))
                listings_count = safe_int(artist.get("worksCount"))
        except json.JSONDecodeError:
            pass

    try:
        return ShopProfile(
            marketplace=Marketplace.REDBUBBLE,
            external_id=handle,
            handle=handle,
            display_name=display_name,
            url=url,  # type: ignore[arg-type]
            location=location,
            total_sales=sales,
            listings_count=listings_count,
            first_seen_at=now,
            last_seen_at=now,
        )
    except Exception:
        return None


def _find_work_node(data: object, work_id: str) -> object | None:
    """DFS through the initial state for a work matching the id."""
    if isinstance(data, dict):
        wid = data.get("id") or data.get("workId")
        if str(wid) == work_id and data.get("title"):
            return data
        for v in data.values():
            found = _find_work_node(v, work_id)
            if found is not None:
                return found
    elif isinstance(data, list):
        for v in data:
            found = _find_work_node(v, work_id)
            if found is not None:
                return found
    return None


def _find_artist_node(data: object, handle: str) -> object | None:
    if isinstance(data, dict):
        if (
            data.get("username") == handle
            or data.get("urlname") == handle
            or data.get("artistUsername") == handle
        ):
            return data
        for v in data.values():
            found = _find_artist_node(v, handle)
            if found is not None:
                return found
    elif isinstance(data, list):
        for v in data:
            found = _find_artist_node(v, handle)
            if found is not None:
                return found
    return None
