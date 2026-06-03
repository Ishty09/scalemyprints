"""
Supabase-backed ListingStore.

REST-based PostgREST client identical in style to the
SupabaseDesignJobStore used by the Design Engine. Uses the service
role key (bypasses RLS) since this runs from the worker, not a user
session.

Schema lives in `20260603000000_spy_phase_1.sql`:
  spy_listings              (id, marketplace, external_id UNIQUE per marketplace, ...)
  spy_listing_snapshots     (listing_id FK, captured_at, ...)
"""

from __future__ import annotations

import httpx

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.enums import ListingStatus, Marketplace, VelocityClass
from scalemyprints.domain.spy.models import Listing, ListingSnapshot
from scalemyprints.domain.spy.ports import ListingStore

logger = get_logger(__name__)


class SupabaseListingStore(ListingStore):
    """REST-backed Supabase ListingStore."""

    def __init__(
        self,
        *,
        supabase_url: str,
        service_role_key: str,
        timeout_seconds: float = 6.0,
    ) -> None:
        self._url = supabase_url.rstrip("/")
        self._headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout_seconds
        self._client: httpx.AsyncClient | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ----- Upsert listing -------------------------------------------------

    async def upsert_listing(self, listing: Listing) -> str:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_listings"
        headers = {
            **self._headers,
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
        params = {"on_conflict": "marketplace,external_id"}
        payload = _serialize_listing(listing)
        resp = await client.post(url, params=params, headers=headers, json=payload)
        if resp.status_code >= 400:
            logger.warning(
                "spy_upsert_failed",
                status=resp.status_code,
                body=resp.text[:300],
            )
            resp.raise_for_status()
        rows = resp.json()
        if not rows:
            # Some PG versions don't return rep on conflict; fall back to select
            return await self._select_id(listing.marketplace, listing.external_id)
        return rows[0]["id"]

    async def _select_id(
        self,
        marketplace: Marketplace,
        external_id: str,
    ) -> str:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_listings"
        params = {
            "marketplace": f"eq.{marketplace.value}",
            "external_id": f"eq.{external_id}",
            "select": "id",
        }
        resp = await client.get(url, params=params, headers=self._headers)
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            raise RuntimeError("spy_listing_upsert_returned_no_id")
        return rows[0]["id"]

    # ----- Record snapshot ------------------------------------------------

    async def record_snapshot(self, snapshot: ListingSnapshot) -> None:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_listing_snapshots"
        headers = {**self._headers, "Prefer": "return=minimal"}
        payload = {
            "listing_id": snapshot.listing_id,
            "captured_at": snapshot.captured_at.isoformat(),
            "price_usd": snapshot.price_usd,
            "favorites": snapshot.favorites,
            "reviews_count": snapshot.reviews_count,
            "rating": snapshot.rating,
            "est_daily_sales": snapshot.est_daily_sales,
            "rank_within_query": snapshot.rank_within_query,
            "raw_payload": snapshot.raw_payload,
        }
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            logger.warning(
                "spy_snapshot_failed",
                status=resp.status_code,
                body=resp.text[:300],
            )
            resp.raise_for_status()

    # ----- Fetches --------------------------------------------------------

    async def get_listing(self, listing_id: str) -> Listing | None:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_listings"
        params = {"id": f"eq.{listing_id}", "select": "*"}
        resp = await client.get(url, params=params, headers=self._headers)
        resp.raise_for_status()
        rows = resp.json()
        return _row_to_listing(rows[0]) if rows else None

    async def get_by_external(
        self,
        marketplace: Marketplace,
        external_id: str,
    ) -> tuple[str, Listing] | None:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_listings"
        params = {
            "marketplace": f"eq.{marketplace.value}",
            "external_id": f"eq.{external_id}",
            "select": "*",
        }
        resp = await client.get(url, params=params, headers=self._headers)
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            return None
        row = rows[0]
        listing = _row_to_listing(row)
        return row["id"], listing

    async def recent_snapshots(
        self,
        listing_id: str,
        *,
        days: int = 14,
        limit: int = 200,
    ) -> list[ListingSnapshot]:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_listing_snapshots"
        params = {
            "listing_id": f"eq.{listing_id}",
            "select": "*",
            "order": "captured_at.desc",
            "limit": str(limit),
        }
        resp = await client.get(url, params=params, headers=self._headers)
        resp.raise_for_status()
        rows = resp.json()
        return [_row_to_snapshot(r) for r in rows]

    async def candidates_for_refresh(
        self,
        *,
        limit: int = 100,
        max_age_hours: int = 6,
    ) -> list[tuple[str, Listing]]:
        from datetime import UTC, datetime, timedelta  # noqa: PLC0415

        cutoff = (datetime.now(UTC) - timedelta(hours=max_age_hours)).isoformat()
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_listings"
        params = {
            "select": "*",
            "last_seen_at": f"lte.{cutoff}",
            "order": "last_seen_at.asc",
            "limit": str(limit),
        }
        resp = await client.get(url, params=params, headers=self._headers)
        resp.raise_for_status()
        rows = resp.json()
        return [(str(r["id"]), _row_to_listing(r)) for r in rows]


# -----------------------------------------------------------------------------
# (De)serialization
# -----------------------------------------------------------------------------


def _serialize_listing(listing: Listing) -> dict[str, object]:
    return {
        "marketplace": listing.marketplace.value,
        "external_id": listing.external_id,
        "url": str(listing.url),
        "title": listing.title,
        "description": listing.description,
        "tags": listing.tags,
        "price_usd": listing.price_usd,
        "currency": listing.currency,
        "thumbnail_url": str(listing.thumbnail_url) if listing.thumbnail_url else None,
        "image_urls": [str(u) for u in listing.image_urls],
        "shop_external_id": listing.shop_external_id,
        "shop_handle": listing.shop_handle,
        "shop_url": str(listing.shop_url) if listing.shop_url else None,
        "status": listing.status.value,
        "favorites": listing.favorites,
        "reviews_count": listing.reviews_count,
        "rating": listing.rating,
        "est_daily_sales": listing.est_daily_sales,
        "velocity_class": listing.velocity_class.value,
        "first_seen_at": listing.first_seen_at.isoformat(),
        "last_seen_at": listing.last_seen_at.isoformat(),
    }


def _row_to_listing(row: dict[str, object]) -> Listing:
    from datetime import datetime

    return Listing(
        marketplace=Marketplace(row["marketplace"]),  # type: ignore[arg-type]
        external_id=str(row["external_id"]),
        url=row["url"],  # type: ignore[arg-type]
        title=str(row["title"]),
        description=row.get("description"),  # type: ignore[arg-type]
        tags=row.get("tags") or [],  # type: ignore[arg-type]
        price_usd=row.get("price_usd"),  # type: ignore[arg-type]
        currency=row.get("currency"),  # type: ignore[arg-type]
        thumbnail_url=row.get("thumbnail_url"),  # type: ignore[arg-type]
        image_urls=row.get("image_urls") or [],  # type: ignore[arg-type]
        shop_external_id=row.get("shop_external_id"),  # type: ignore[arg-type]
        shop_handle=row.get("shop_handle"),  # type: ignore[arg-type]
        shop_url=row.get("shop_url"),  # type: ignore[arg-type]
        status=ListingStatus(row.get("status") or "active"),  # type: ignore[arg-type]
        favorites=row.get("favorites"),  # type: ignore[arg-type]
        reviews_count=row.get("reviews_count"),  # type: ignore[arg-type]
        rating=row.get("rating"),  # type: ignore[arg-type]
        est_daily_sales=row.get("est_daily_sales"),  # type: ignore[arg-type]
        velocity_class=VelocityClass(row.get("velocity_class") or "steady"),  # type: ignore[arg-type]
        first_seen_at=datetime.fromisoformat(str(row["first_seen_at"]).replace("Z", "+00:00")),
        last_seen_at=datetime.fromisoformat(str(row["last_seen_at"]).replace("Z", "+00:00")),
    )


def _row_to_snapshot(row: dict[str, object]) -> ListingSnapshot:
    from datetime import datetime

    return ListingSnapshot(
        listing_id=str(row["listing_id"]),
        captured_at=datetime.fromisoformat(str(row["captured_at"]).replace("Z", "+00:00")),
        price_usd=row.get("price_usd"),  # type: ignore[arg-type]
        favorites=row.get("favorites"),  # type: ignore[arg-type]
        reviews_count=row.get("reviews_count"),  # type: ignore[arg-type]
        rating=row.get("rating"),  # type: ignore[arg-type]
        est_daily_sales=row.get("est_daily_sales"),  # type: ignore[arg-type]
        rank_within_query=row.get("rank_within_query"),  # type: ignore[arg-type]
        raw_payload=row.get("raw_payload"),  # type: ignore[arg-type]
    )
