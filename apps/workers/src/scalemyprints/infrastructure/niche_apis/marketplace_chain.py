"""
Marketplace provider chain — first-success wins.

Used to layer marketplace adapters: Apify Etsy (paid, when in trial) →
eBay Browse (free OAuth) → Etsy public scrape (last-resort, often
blocked from datacenter IPs).

Mirrors trends_chain — adapters return MarketplaceData with `error`
set on failure, chain walks them in order.
"""

from __future__ import annotations

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.niche.enums import Country
from scalemyprints.domain.niche.ports import MarketplaceData, MarketplaceProvider

logger = get_logger(__name__)


class MarketplaceProviderChain:
    """First-success-wins chain over multiple MarketplaceProvider adapters."""

    def __init__(self, providers: list[tuple[str, MarketplaceProvider]]) -> None:
        if not providers:
            raise ValueError("marketplace chain requires at least one provider")
        self._providers = providers

    async def aclose(self) -> None:
        for _, provider in self._providers:
            close_method = getattr(provider, "aclose", None)
            if close_method:
                try:
                    await close_method()
                except Exception:
                    logger.warning(
                        "marketplace_chain_close_failed",
                        provider=type(provider).__name__,
                    )

    async def fetch(self, keyword: str, country: Country) -> MarketplaceData:
        log = logger.bind(keyword=keyword, country=country.value)
        attempt_errors: list[str] = []
        last_result: MarketplaceData | None = None

        for name, provider in self._providers:
            try:
                result = await provider.fetch(keyword, country)
            except Exception as e:
                log.warning(
                    "marketplace_chain_provider_raised",
                    provider=name,
                    error=str(e)[:120],
                )
                attempt_errors.append(f"{name}:raised_{e.__class__.__name__}")
                continue

            if result.error is None and result.listing_count is not None:
                # Real success: provider returned a listing count.
                log.info(
                    "marketplace_chain_success",
                    provider=name,
                    listings=result.listing_count,
                )
                return result

            attempt_errors.append(f"{name}:{result.error or 'no_listings'}")
            last_result = result
            log.info(
                "marketplace_chain_provider_failed",
                provider=name,
                error=result.error,
            )

        log.warning("marketplace_chain_exhausted", attempts=attempt_errors)
        if last_result is None:
            return MarketplaceData(
                error=f"all_providers_failed:{','.join(attempt_errors)}",
            )
        return last_result.model_copy(
            update={"error": f"all_providers_failed:{','.join(attempt_errors)}"}
        )
