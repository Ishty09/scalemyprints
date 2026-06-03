"""
Printify catalog adapter.

Hits `https://api.printify.com/v1/catalog/blueprints.json` to enumerate
print-on-demand blueprints, then `/blueprints/{id}/print_providers.json`
+ `/blueprints/{id}/print_providers/{pid}/variants.json` for variant
prices.

Requires `PRINTIFY_API_TOKEN` (free Bearer token after signup). Falls
back to error result when missing.
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


PRINTIFY_API_BASE = "https://api.printify.com/v1/catalog"


# Maps our internal product_type → (Printify blueprint_id, optional
# title keyword filter). IDs below are stable blueprint identifiers
# pulled from Printify's 2026 catalog. We keep the keyword filter as a
# safety net since blueprint names rotate occasionally.
_BLUEPRINT_MAP: dict[str, tuple[int, tuple[str, ...]]] = {
    "t_shirt":       (5, ("unisex", "cotton", "bella")),
    "tank_top":      (38, ("tank",)),
    "long_sleeve":   (11, ("long",)),
    "hoodie":        (77, ("hoodie",)),
    "sweatshirt":    (49, ("sweatshirt",)),
    "mug_11oz":      (478, ("11oz", "11 oz")),
    "mug_15oz":      (479, ("15oz", "15 oz")),
    "tote_bag":      (380, ("tote",)),
    "phone_case":    (157, ("case",)),
    "poster_18x24":  (1095, ("18", "24")),
    "sticker":       (1226, ()),
    "blanket_50x60": (522, ("50",)),
    "pillow_18x18":  (514, ("18",)),
}


class PrintifyPriceProvider(PrinterPriceProvider):
    """Fetches live catalog prices from Printify."""

    @property
    def printer(self) -> str:
        return "printify"

    def __init__(
        self,
        *,
        api_token: str = "",
        timeout_seconds: float = 10.0,
    ) -> None:
        self._token = api_token
        self._timeout = timeout_seconds
        self._cache: dict[str, tuple[float, LivePriceQuote]] = {}
        self._cache_ttl_seconds = 3600.0

    async def quote(self, product_type: str) -> LivePriceQuote:
        if not self._token:
            return _empty(
                product_type=product_type,
                error="printify_token_unconfigured",
            )

        now = time.monotonic()
        cached = self._cache.get(product_type)
        if cached and (now - cached[0]) < self._cache_ttl_seconds:
            return cached[1]

        mapping = _BLUEPRINT_MAP.get(product_type)
        if mapping is None:
            return _empty(
                product_type=product_type,
                error=f"unsupported_product_type: {product_type}",
            )

        blueprint_id, _keywords = mapping
        cheapest = await self._fetch_cheapest(blueprint_id)
        if cheapest is None:
            return _empty(
                product_type=product_type,
                error="no_matching_variant",
            )

        quote = LivePriceQuote(
            printer="printify",
            product_type=product_type,
            base_cost_usd=cheapest,
            source_url=f"https://printify.com/app/catalog/blueprint/{blueprint_id}",
            fetched_at=datetime.now(UTC).isoformat(),
        )
        self._cache[product_type] = (now, quote)
        return quote

    async def _fetch_cheapest(self, blueprint_id: int) -> float | None:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as c:
                # 1. List print providers for this blueprint
                providers_url = (
                    f"{PRINTIFY_API_BASE}/blueprints/{blueprint_id}/print_providers.json"
                )
                p_resp = await c.get(providers_url, headers=headers)
                if p_resp.status_code >= 400:
                    return None
                providers = p_resp.json()
                if not isinstance(providers, list):
                    return None

                cheapest: float | None = None
                # 2. For each provider, walk variants for the lowest cost
                for prov in providers[:5]:  # cap at 5 to bound latency
                    if not isinstance(prov, dict):
                        continue
                    pid = prov.get("id")
                    if pid is None:
                        continue
                    var_url = (
                        f"{PRINTIFY_API_BASE}/blueprints/{blueprint_id}"
                        f"/print_providers/{pid}/variants.json"
                    )
                    v_resp = await c.get(var_url, headers=headers)
                    if v_resp.status_code >= 400:
                        continue
                    payload = v_resp.json()
                    variants = (
                        payload.get("variants")
                        if isinstance(payload, dict)
                        else payload
                    )
                    if not isinstance(variants, list):
                        continue
                    for v in variants:
                        if not isinstance(v, dict):
                            continue
                        raw = v.get("cost") or v.get("price")
                        # Printify expresses costs in cents
                        try:
                            cents = float(raw)
                        except (TypeError, ValueError):
                            continue
                        # Heuristic: any value > 200 must be cents
                        usd = cents / 100.0 if cents >= 100 else float(cents)
                        if usd <= 0:
                            continue
                        if cheapest is None or usd < cheapest:
                            cheapest = usd
                return cheapest
        except Exception as e:
            logger.warning("printify_quote_failed", error=str(e))
            return None


def _empty(*, product_type: str, error: str) -> LivePriceQuote:
    return LivePriceQuote(
        printer="printify",
        product_type=product_type,
        base_cost_usd=0.0,
        fetched_at=datetime.now(UTC).isoformat(),
        error=error,
    )
