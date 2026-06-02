"""
Trends provider chain — tries adapters in order, returns first success.

Used to layer Wikipedia (free, reliable) → Google Trends (richer signal
when not blocked) → fallback. Each adapter implements the TrendsProvider
port and returns a TrendsData with `error` set on failure.

This is a simpler version of trademark's provider_chain — no circuit
breakers; trends signal is non-critical so we just walk through the
list on every request and let the orchestrator deal with degraded data.
"""

from __future__ import annotations

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.niche.enums import Country
from scalemyprints.domain.niche.ports import TrendsData, TrendsProvider

logger = get_logger(__name__)


class TrendsProviderChain:
    """First-success-wins chain over multiple TrendsProvider adapters."""

    def __init__(self, providers: list[tuple[str, TrendsProvider]]) -> None:
        if not providers:
            raise ValueError("trends chain requires at least one provider")
        self._providers = providers

    async def aclose(self) -> None:
        """Close any providers that hold open HTTP clients."""
        for _, provider in self._providers:
            close_method = getattr(provider, "aclose", None)
            if close_method:
                try:
                    await close_method()
                except Exception:
                    logger.warning(
                        "trends_chain_close_failed",
                        provider=type(provider).__name__,
                    )

    async def fetch(self, keyword: str, country: Country) -> TrendsData:
        log = logger.bind(keyword=keyword, country=country.value)
        attempt_errors: list[str] = []
        last_result: TrendsData | None = None

        for name, provider in self._providers:
            try:
                result = await provider.fetch(keyword, country)
            except Exception as e:
                # Adapters shouldn't raise per protocol, but be defensive.
                log.warning(
                    "trends_chain_provider_raised",
                    provider=name,
                    error=str(e)[:120],
                )
                attempt_errors.append(f"{name}:raised_{e.__class__.__name__}")
                continue

            if result.error is None:
                log.info(
                    "trends_chain_success",
                    provider=name,
                    volume_index=result.search_volume_index,
                )
                return result

            attempt_errors.append(f"{name}:{result.error}")
            last_result = result
            log.info(
                "trends_chain_provider_failed",
                provider=name,
                error=result.error,
            )

        # All adapters returned an error. Return the last one with the
        # aggregated trail so debugging is easier.
        log.warning("trends_chain_exhausted", attempts=attempt_errors)
        if last_result is None:
            return TrendsData(
                search_volume_index=0,
                error=f"all_providers_failed:{','.join(attempt_errors)}",
            )
        return last_result.model_copy(
            update={"error": f"all_providers_failed:{','.join(attempt_errors)}"}
        )
