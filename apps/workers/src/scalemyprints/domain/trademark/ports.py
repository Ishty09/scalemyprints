"""
Ports — protocols for external dependencies.

The domain defines these abstractions; the infrastructure layer provides
concrete implementations. This inversion of control keeps the domain
testable and allows swapping providers via configuration.

Implementations live in apps/workers/src/scalemyprints/infrastructure/
and are wired up in the dependency injection layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from scalemyprints.domain.trademark.enums import JurisdictionCode
from scalemyprints.domain.trademark.models import TrademarkRecord

# -----------------------------------------------------------------------------
# Search result value object — what TrademarkAPI returns per jurisdiction
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TrademarkSearchResult:
    """Result of searching a single jurisdiction."""

    jurisdiction: JurisdictionCode
    records: list[TrademarkRecord]
    duration_ms: int
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None


# -----------------------------------------------------------------------------
# Ports
# -----------------------------------------------------------------------------


class TrademarkAPI(Protocol):
    """
    Port for querying a trademark office.

    Each implementation (USPTO, EUIPO, IP Australia) conforms to this protocol
    and produces normalized TrademarkRecord objects regardless of the
    source API's quirks.
    """

    jurisdiction: JurisdictionCode

    async def search(
        self,
        phrase: str,
        nice_classes: list[int],
    ) -> TrademarkSearchResult:
        """
        Search the trademark office for the given phrase.

        Must handle:
        - Network errors → return TrademarkSearchResult with error set
        - Empty results → return TrademarkSearchResult with empty records
        - Rate limiting → apply backoff internally

        Must NOT raise unless catastrophically broken.
        """
        ...


class CacheStore(Protocol):
    """Port for caching expensive operations."""

    async def get(self, key: str) -> bytes | None:
        """Return cached value or None if missing/expired."""
        ...

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        """Cache a value with a TTL."""
        ...

    async def delete(self, key: str) -> None:
        """Remove a key from the cache."""
        ...


class CommonLawChecker(Protocol):
    """
    Port for estimating unregistered common-law use of a phrase.

    Implementation typically searches Etsy, Amazon, Google Shopping to
    estimate how densely the phrase appears in commerce.
    """

    async def estimate_density(self, phrase: str) -> float:
        """
        Return a density score 0.0-1.0.

        0.0 = never used commercially anywhere
        1.0 = extremely common use (thousands of listings)

        Must NOT raise; return 0.0 on any error (absence of signal).
        """
        ...
