"""
Printful catalog adapter.

Uses Printful's public products endpoint at
`https://api.printful.com/products` — no auth required for read-only
catalog browsing. We pick the cheapest variant matching each of our
internal `ProductType` values.

Catalog → ProductType mapping is kept in `_CATEGORY_MAP` so we don't
hard-code Printful's category IDs all over the codebase.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx

from scalemyprints.core.logging import get_logger
from scalemyprints.infrastructure.printer_apis.ports import (
    LivePriceQuote,
    PrinterPriceProvider,
)

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


PRINTFUL_API_BASE = "https://api.printful.com"


# Maps our internal product_type → (Printful category_id, optional
# keyword filter). Printful's category list is at
# https://www.printful.com/api/products/categories. The IDs below are
# the public, stable category IDs from the 2026 catalog snapshot.
_CATEGORY_MAP: dict[str, tuple[int, tuple[str, ...]]] = {
    "t_shirt":       (24, ("unisex", "bella", "gildan")),
    "tank_top":      (24, ("tank",)),
    "long_sleeve":   (24, ("long",)),
    "hoodie":        (24, ("hoodie",)),
    "sweatshirt":    (24, ("sweatshirt",)),
    "mug_11oz":      (8, ("11oz", "11 oz")),
    "mug_15oz":      (8, ("15oz", "15 oz")),
    "tote_bag":      (10, ("tote",)),
    "phone_case":    (16, ("case",)),
    "poster_18x24":  (1, ("poster",)),
    "sticker":       (171, ()),
    "blanket_50x60": (148, ("50",)),
    "pillow_18x18":  (40, ("18",)),
}


class PrintfulPriceProvider(PrinterPriceProvider):
    """Fetches live catalog prices from Printful."""

    @property
    def printer(self) -> str:
        return "printful"

    def __init__(self, *, timeout_seconds: float = 8.0) -> None:
        self._timeout = timeout_seconds
        self._cache: dict[str, tuple[float, LivePriceQuote]] = {}
        self._cache_ttl_seconds = 3600.0  # 1 hour — catalog prices don't move often

    async def quote(self, product_type: str) -> LivePriceQuote:
        now = time.monotonic()
        cached = self._cache.get(product_type)
        if cached and (now - cached[0]) < self._cache_ttl_seconds:
            return cached[1]

        mapping = _CATEGORY_MAP.get(product_type)
        if mapping is None:
            return _empty(
                product_type=product_type,
                error=f"unsupported_product_type: {product_type}",
            )

        category_id, keywords = mapping
        url = f"{PRINTFUL_API_BASE}/products?category_id={category_id}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as c:
                resp = await c.get(url, headers={"Accept": "application/json"})
                if resp.status_code >= 400:
                    return _empty(
                        product_type=product_type,
                        error=f"http_{resp.status_code}",
                    )
                data = resp.json()
        except Exception as e:
            logger.warning("printful_quote_failed", error=str(e), pt=product_type)
            return _empty(product_type=product_type, error=f"fetch_failed: {e}")

        cheapest = _pick_cheapest(data, keywords)
        if cheapest is None:
            return _empty(
                product_type=product_type,
                error="no_matching_variant",
            )

        quote = LivePriceQuote(
            printer="printful",
            product_type=product_type,
            base_cost_usd=cheapest,
            source_url=f"https://www.printful.com/products?category_id={category_id}",
            fetched_at=datetime.now(UTC).isoformat(),
        )
        self._cache[product_type] = (now, quote)
        return quote


# -----------------------------------------------------------------------------
# Parsing helpers
# -----------------------------------------------------------------------------


def _pick_cheapest(catalog: object, keywords: tuple[str, ...]) -> float | None:
    """Walk the catalog JSON for the lowest matching variant price."""
    products = _coerce_products(catalog)
    cheapest: float | None = None

    for p in products:
        title = str(p.get("title") or p.get("name") or "").lower()
        if keywords and not any(k.lower() in title for k in keywords):
            continue

        variants = p.get("variants") or []
        if not isinstance(variants, list):
            continue
        for v in variants:
            if not isinstance(v, dict):
                continue
            raw_price = v.get("price") or v.get("retail_price") or v.get("base_price")
            try:
                price = float(raw_price)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            if cheapest is None or price < cheapest:
                cheapest = price
    return cheapest


def _coerce_products(catalog: object) -> list[dict[str, object]]:
    if isinstance(catalog, dict):
        if isinstance(catalog.get("result"), list):
            return [p for p in catalog["result"] if isinstance(p, dict)]
        if isinstance(catalog.get("products"), list):
            return [p for p in catalog["products"] if isinstance(p, dict)]
    if isinstance(catalog, list):
        return [p for p in catalog if isinstance(p, dict)]
    return []


def _empty(*, product_type: str, error: str) -> LivePriceQuote:
    return LivePriceQuote(
        printer="printful",
        product_type=product_type,
        base_cost_usd=0.0,
        fetched_at=datetime.now(UTC).isoformat(),
        error=error,
    )
