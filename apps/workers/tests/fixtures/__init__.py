"""
Reusable fixtures for trademark tests.

Use builder functions (not fixtures) so tests can customize attributes.
This is more flexible than fixed pytest fixtures for data objects.
"""

from __future__ import annotations

from scalemyprints.domain.trademark.enums import FilingStatus, JurisdictionCode
from scalemyprints.domain.trademark.models import TrademarkRecord
from scalemyprints.domain.trademark.ports import TrademarkSearchResult


def make_record(
    *,
    registration_number: str = "98123456",
    mark: str = "Example Mark",
    owner: str | None = "Acme Corp",
    status: FilingStatus = FilingStatus.REGISTERED,
    nice_class: int = 25,
    nice_classes: list[int] | None = None,
    jurisdiction: JurisdictionCode = JurisdictionCode.US,
    filing_date: str | None = "2020-01-15",
    registration_date: str | None = "2021-06-10",
    source_url: str | None = "https://tsdr.uspto.gov/",
    goods_services: str | None = "Clothing, namely t-shirts and hoodies.",
    raw_status: str | None = "LIVE",
) -> TrademarkRecord:
    """Create a TrademarkRecord with sensible defaults, override any field."""
    resolved_classes = nice_classes if nice_classes is not None else [nice_class]
    is_active = status in {FilingStatus.REGISTERED, FilingStatus.OPPOSED}
    is_pending = status == FilingStatus.PENDING

    return TrademarkRecord(
        registration_number=registration_number,
        mark=mark,
        owner=owner,
        status=status,
        raw_status=raw_status,
        nice_class=resolved_classes[0] if resolved_classes else None,
        nice_classes=resolved_classes,
        filing_date=filing_date,
        registration_date=registration_date if is_active else None,
        jurisdiction=jurisdiction,
        source_url=source_url,
        goods_services=goods_services,
        is_active=is_active,
        is_pending=is_pending,
    )


def make_search_result(
    *,
    jurisdiction: JurisdictionCode = JurisdictionCode.US,
    records: list[TrademarkRecord] | None = None,
    duration_ms: int = 250,
    error: str | None = None,
) -> TrademarkSearchResult:
    """Build a search result for tests."""
    return TrademarkSearchResult(
        jurisdiction=jurisdiction,
        records=records or [],
        duration_ms=duration_ms,
        error=error,
    )
