"""
Provider chain — runs an ordered list of TrademarkAPI providers with
circuit breakers, returning the first successful result.

Implements the same `TrademarkAPI` protocol as a single adapter, so the
domain `TrademarkSearchService` doesn't know or care that there's a chain.

Behavior:
- Try providers in order
- Skip providers whose breaker is OPEN
- On success → record_success, return result
- On failure (error in result OR exception) → record_failure, try next
- If all providers fail → return aggregated TrademarkSearchResult with
  `error` listing all attempts

Design notes:
- A "successful" result means `error is None` AND records is non-error.
  Empty records with `error=None` is still a success — the office just
  didn't have hits for that phrase.
- Failures from one provider don't poison records from another. We
  return the first clean result; no merging across providers (would
  require dedup logic that depends on jurisdiction-specific IDs).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.trademark.enums import JurisdictionCode
from scalemyprints.domain.trademark.ports import TrademarkAPI, TrademarkSearchResult
from scalemyprints.infrastructure.trademark_apis.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
)

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _ProviderEntry:
    """A provider in the chain, with its breaker."""

    name: str
    api: TrademarkAPI
    breaker: CircuitBreaker


class TrademarkProviderChain:
    """
    Chain of TrademarkAPI providers tried in order.

    All providers must target the **same** jurisdiction (we assert this
    at construction). The chain itself implements TrademarkAPI so it can
    be dropped into the existing dict[Jurisdiction, TrademarkAPI] map.
    """

    def __init__(
        self,
        *,
        jurisdiction: JurisdictionCode,
        providers: Sequence[tuple[str, TrademarkAPI]],
        breaker_config: CircuitBreakerConfig | None = None,
    ) -> None:
        if not providers:
            raise ValueError("chain requires at least one provider")
        cfg = breaker_config or CircuitBreakerConfig()

        entries: list[_ProviderEntry] = []
        for name, api in providers:
            if api.jurisdiction != jurisdiction:
                raise ValueError(
                    f"provider {name!r} targets {api.jurisdiction.value} "
                    f"but chain is for {jurisdiction.value}"
                )
            entries.append(
                _ProviderEntry(
                    name=name,
                    api=api,
                    breaker=CircuitBreaker(
                        name=f"{jurisdiction.value}:{name}",
                        config=cfg,
                    ),
                )
            )
        self._jurisdiction = jurisdiction
        self._entries = entries

    # TrademarkAPI protocol
    @property
    def jurisdiction(self) -> JurisdictionCode:  # type: ignore[override]
        return self._jurisdiction

    async def search(
        self, phrase: str, nice_classes: list[int]
    ) -> TrademarkSearchResult:
        """Try each provider in order until one succeeds."""
        log = logger.bind(
            jurisdiction=self._jurisdiction.value,
            phrase=phrase,
            chain_length=len(self._entries),
        )

        attempted: list[str] = []
        attempt_errors: list[str] = []
        total_duration_ms = 0

        for entry in self._entries:
            allowed = await entry.breaker.allow()
            if not allowed:
                attempted.append(f"{entry.name}:circuit_open")
                log.debug("chain_skip_open", provider=entry.name)
                continue

            attempted.append(entry.name)
            try:
                result = await entry.api.search(
                    phrase=phrase, nice_classes=nice_classes
                )
            except Exception as e:
                # Adapter shouldn't raise per protocol, but if it does, treat
                # as failure and continue.
                log.warning(
                    "chain_provider_raised",
                    provider=entry.name,
                    error=str(e),
                )
                await entry.breaker.record_failure()
                attempt_errors.append(f"{entry.name}:raised_{e.__class__.__name__}")
                continue

            total_duration_ms += result.duration_ms

            if result.error is None:
                # Success!
                await entry.breaker.record_success()
                log.info(
                    "chain_success",
                    provider=entry.name,
                    records=len(result.records),
                    attempts=len(attempted),
                )
                # Tag the result so observability can see which provider won
                return TrademarkSearchResult(
                    jurisdiction=self._jurisdiction,
                    records=result.records,
                    duration_ms=total_duration_ms,
                    error=None,
                )

            # Provider returned an error result — count as failure
            await entry.breaker.record_failure()
            attempt_errors.append(f"{entry.name}:{result.error}")
            log.warning(
                "chain_provider_failed",
                provider=entry.name,
                error=result.error,
            )

        # All providers failed (or all skipped because circuits open)
        log.error("chain_exhausted", attempted=attempted)
        return TrademarkSearchResult(
            jurisdiction=self._jurisdiction,
            records=[],
            duration_ms=total_duration_ms,
            error=f"all_providers_failed: {'; '.join(attempt_errors) or 'all_circuits_open'}",
        )

    # Optional async context-manager parity with single adapters — harmless to support.
    async def __aenter__(self) -> TrademarkProviderChain:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        # Individual adapters own their own clients and are closed by the
        # container. The chain is just a thin wrapper.
        return None
