"""
Provider for the GET /api/v1/spy/feed hot-movers endpoint.

Reads from the `spy_hot_movers` view defined in the Phase 1 migration.
Has a memory fallback for local dev / tests when Supabase isn't wired.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

import httpx

from scalemyprints.api.schemas.spy import HotMoverItem
from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.enums import Marketplace, VelocityClass

logger = get_logger(__name__)


@runtime_checkable
class HotMoversProvider(Protocol):
    """Source for `GET /spy/feed`."""

    async def recent(self, *, limit: int = 30) -> list[HotMoverItem]: ...


class MemoryHotMoversProvider(HotMoversProvider):
    """Empty / seeded provider — useful for local dev without Supabase."""

    def __init__(self, seed: list[HotMoverItem] | None = None) -> None:
        self._items = seed or []

    async def recent(self, *, limit: int = 30) -> list[HotMoverItem]:
        return self._items[:limit]

    # Test helper
    def set(self, items: list[HotMoverItem]) -> None:
        self._items = items


class SupabaseHotMoversProvider(HotMoversProvider):
    """Reads from the spy_hot_movers view via PostgREST."""

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

    async def recent(self, *, limit: int = 30) -> list[HotMoverItem]:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_hot_movers"
        params = {
            "select": "*",
            "order": "last_seen_at.desc",
            "limit": str(limit),
        }
        try:
            resp = await client.get(url, params=params, headers=self._headers)
            resp.raise_for_status()
            rows = resp.json()
        except Exception as e:
            logger.warning("spy_hot_movers_query_failed", error=str(e))
            return []

        items: list[HotMoverItem] = []
        for row in rows:
            try:
                items.append(
                    HotMoverItem(
                        id=str(row["id"]),
                        marketplace=Marketplace(row["marketplace"]),
                        title=str(row["title"]),
                        url=row["url"],
                        thumbnail_url=row.get("thumbnail_url"),
                        shop_handle=row.get("shop_handle"),
                        shop_url=row.get("shop_url"),
                        velocity_class=VelocityClass(row.get("velocity_class") or "steady"),
                        est_daily_sales=row.get("est_daily_sales"),
                        price_usd=row.get("price_usd"),
                        favorites=row.get("favorites"),
                        reviews_count=row.get("reviews_count"),
                        last_seen_at=_parse_dt(row.get("last_seen_at")),
                    )
                )
            except Exception:
                continue
        return items


def _parse_dt(raw: object) -> datetime:
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            pass
    return datetime.now(UTC)
