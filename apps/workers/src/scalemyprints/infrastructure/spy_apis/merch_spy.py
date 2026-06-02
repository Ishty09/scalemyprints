"""
Amazon Merch on Demand spy adapter.

Amazon doesn't expose Merch SKUs via the Product Advertising API, and
public scraping of amazon.com is brutally protected by Cloudflare/Bot
Manager. Phase 1 approach:

Two execution paths, picked by the configured Apify token:

  Path A (preferred) — Apify "Amazon Product Search Scraper" actor
    Token: APIFY_API_TOKEN  (already in env from niche/trademark work)
    Actor: "junglee/amazon-product-search"  — well-maintained, mature
    Cost: ~$0.30 per 100 results, very reliable
    Limitations: t-shirt category filter must be passed; rate-limited
    to ~5 concurrent runs on the free tier.

  Path B (degraded) — direct curl_cffi with mobile UA
    Used when Apify is unconfigured or returns errors.
    Highly likely to be blocked from datacenter IPs; surfaces
    SOURCE_BLOCKED so the UI can disable the Merch column for that
    query.

Listing detail + shop fetch are STUB in Phase 1 (always return
error="not_implemented") because Amazon Merch shop pages are
notoriously hostile to scrape. Phase 2 wires the Apify
"junglee/amazon-storefront-scraper" actor.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.enums import (
    ListingStatus,
    Marketplace,
    ShopAuditDepth,
    SpyFailureReason,
)
from scalemyprints.domain.spy.models import Listing, SpyQuery
from scalemyprints.domain.spy.ports import (
    ListingDetailResult,
    MarketplaceSearchResult,
    ShopFetchResult,
    SpyMarketplaceAdapter,
)
from scalemyprints.infrastructure.spy_apis.base import safe_float, safe_int

logger = get_logger(__name__)


APIFY_ACTOR_SLUG = "junglee~amazon-product-search"


class MerchSpyAdapter(SpyMarketplaceAdapter):
    """Amazon Merch on Demand search via Apify."""

    @property
    def marketplace(self) -> Marketplace:
        return Marketplace.AMAZON_MERCH

    def __init__(
        self,
        *,
        apify_token: str | None,
        timeout_seconds: float = 60.0,
        max_run_wait_seconds: float = 60.0,
    ) -> None:
        self._apify_token = apify_token or ""
        self._timeout = timeout_seconds
        self._max_run_wait = max_run_wait_seconds

    # ----- Search ---------------------------------------------------------

    async def search(
        self,
        query: SpyQuery,
        *,
        limit: int = 20,
    ) -> MarketplaceSearchResult:
        start = time.monotonic()

        if not query.text and query.listing_url is None:
            return MarketplaceSearchResult(
                marketplace=Marketplace.AMAZON_MERCH,
                error="empty_query",
                failure_reason=SpyFailureReason.INVALID_INPUT,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        if not self._apify_token:
            return MarketplaceSearchResult(
                marketplace=Marketplace.AMAZON_MERCH,
                error="apify_token_unconfigured",
                failure_reason=SpyFailureReason.SOURCE_BLOCKED,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        keyword = query.text or ""
        if query.listing_url and not keyword:
            keyword = str(query.listing_url)

        listings, err = await self._run_apify(keyword, limit)
        if err:
            return MarketplaceSearchResult(
                marketplace=Marketplace.AMAZON_MERCH,
                error=err,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        return MarketplaceSearchResult(
            marketplace=Marketplace.AMAZON_MERCH,
            listings=listings,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    async def fetch_listing(self, external_id: str) -> ListingDetailResult:
        # Phase 2 — wire Apify product-detail actor here.
        return ListingDetailResult(error="not_implemented_in_phase_1")

    async def fetch_shop(
        self,
        handle_or_id: str,
        *,
        depth: ShopAuditDepth = ShopAuditDepth.STANDARD,
    ) -> ShopFetchResult:
        return ShopFetchResult(error="not_implemented_in_phase_1")

    # ----- Apify call -----------------------------------------------------

    async def _run_apify(
        self,
        keyword: str,
        limit: int,
    ) -> tuple[list[Listing], str | None]:
        """
        Trigger the Apify product-search actor and wait for the run to
        finish, then read the dataset.

        Apify pricing model is "run-once and pay" — we wait synchronously
        up to `self._max_run_wait` seconds. If the run hasn't finished by
        then, we return SOURCE_RATE_LIMITED.
        """
        import httpx

        base = "https://api.apify.com/v2"
        # Body keys mirror the actor's input schema
        body: dict[str, Any] = {
            "search": keyword,
            "category": "Clothing,%20Shoes%20%26%20Jewelry",
            "domain": "com",
            "maxItems": limit,
            "useCaptchaSolver": False,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                run_resp = await client.post(
                    f"{base}/acts/{APIFY_ACTOR_SLUG}/runs",
                    params={"token": self._apify_token},
                    json=body,
                )
                if run_resp.status_code >= 400:
                    return [], f"apify_run_failed: http_{run_resp.status_code}"
                run = run_resp.json().get("data", {})
                run_id = run.get("id")
                dataset_id = run.get("defaultDatasetId")
                if not run_id or not dataset_id:
                    return [], "apify_run_missing_ids"
            except Exception as e:
                return [], f"apify_run_failed: {e}"

            # Poll status
            elapsed = 0.0
            poll_interval = 2.0
            status = run.get("status")
            while status not in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                if elapsed >= self._max_run_wait:
                    return [], "apify_run_timeout"
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                try:
                    s = await client.get(
                        f"{base}/actor-runs/{run_id}",
                        params={"token": self._apify_token},
                    )
                    s.raise_for_status()
                    status = s.json().get("data", {}).get("status")
                except Exception as e:
                    logger.warning("apify_poll_failed", error=str(e))
                    return [], f"apify_poll_failed: {e}"

            if status != "SUCCEEDED":
                return [], f"apify_run_status_{status.lower() if status else 'unknown'}"

            try:
                ds = await client.get(
                    f"{base}/datasets/{dataset_id}/items",
                    params={"token": self._apify_token, "limit": limit, "format": "json"},
                )
                ds.raise_for_status()
                items = ds.json()
            except Exception as e:
                return [], f"apify_dataset_fetch_failed: {e}"

        return _parse_apify_results(items, limit=limit), None


def _parse_apify_results(items: list[dict[str, object]], *, limit: int) -> list[Listing]:
    """Map the Apify junglee/amazon-product-search payload into Listing rows."""
    now = datetime.now(UTC)
    listings: list[Listing] = []
    for item in items[:limit]:
        asin = item.get("asin")
        url = item.get("url") or item.get("Url")
        title = item.get("title") or item.get("Title")
        if not isinstance(asin, str) or not isinstance(url, str) or not isinstance(title, str):
            continue

        price = item.get("price") or item.get("Price")
        if isinstance(price, dict):
            price_val = safe_float(price.get("value"))
            currency = price.get("currency") if isinstance(price.get("currency"), str) else "USD"
        else:
            price_val = safe_float(price)
            currency = "USD"

        thumb = item.get("imageUrl") or item.get("image")
        reviews = safe_int(item.get("reviewsCount") or item.get("reviews"))
        rating = safe_float(item.get("rating") or item.get("stars"))

        try:
            listings.append(
                Listing(
                    marketplace=Marketplace.AMAZON_MERCH,
                    external_id=asin,
                    url=url,  # type: ignore[arg-type]
                    title=title[:400],
                    description=str(item.get("description") or "")[:4000] or None,
                    price_usd=price_val if currency == "USD" else None,
                    currency=currency,
                    thumbnail_url=thumb if isinstance(thumb, str) else None,  # type: ignore[arg-type]
                    rating=rating if rating is not None and 0.0 <= rating <= 5.0 else None,
                    reviews_count=reviews,
                    status=ListingStatus.ACTIVE,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        except Exception:
            continue
    return listings
