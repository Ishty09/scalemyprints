"""
Markbase adapter — free public USPTO mirror.

Endpoint: https://api.markbase.co
- No API key required
- ~30 req/min free tier
- 14M+ USPTO records, daily synced
- JSON responses, ~10ms p50 latency

Used as a US trademark provider, typically chained as a fallback after
the licensed Marker API but before WIPO.

Implements TrademarkAPI protocol — drop-in compatible with the existing
chain runner.

Status code interpretation (USPTO TSDR convention):
  6XX → Live, application pending
  7XX → Dead (cancelled, abandoned)
  8XX → Live, registered
  9XX → Dead (expired)

Date format: Markbase returns dates as 8-digit strings "YYYYMMDD" or null.
"""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Any

import httpx

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.trademark.enums import (
    ACTIVE_STATUSES,
    FilingStatus,
    JurisdictionCode,
)
from scalemyprints.domain.trademark.models import TrademarkRecord
from scalemyprints.domain.trademark.ports import TrademarkSearchResult
from scalemyprints.infrastructure.trademark_apis.base import (
    HttpClientFactory,
    measure_duration,
    run_with_retry,
)
from scalemyprints.infrastructure.trademark_apis.normalizers import (
    normalize_date_string,
    normalize_filing_status,
)

logger = get_logger(__name__)

MARKBASE_DEFAULT_BASE_URL = "https://api.markbase.co"
MARKBASE_SEARCH_PATH = "/search"
MAX_RESULTS_PER_CLASS = 25  # Stay well under free-tier rate limits

USPTO_TSDR_URL_TEMPLATE = (
    "https://tsdr.uspto.gov/#caseNumber={sn}&caseType=DEFAULT&searchType=statusSearch"
)


class MarkbaseClient:
    """Markbase USPTO search adapter. Implements TrademarkAPI."""

    jurisdiction: JurisdictionCode = JurisdictionCode.US

    def __init__(
        self,
        *,
        base_url: str = MARKBASE_DEFAULT_BASE_URL,
        http_factory: HttpClientFactory | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            factory = http_factory or HttpClientFactory()
            self._client = factory.build(base_url=self._base_url)
            self._owns_client = True

    async def __aenter__(self) -> "MarkbaseClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # TrademarkAPI
    # ------------------------------------------------------------------

    async def search(
        self, phrase: str, nice_classes: list[int]
    ) -> TrademarkSearchResult:
        log = logger.bind(
            service="markbase",
            phrase=phrase,
            nice_classes=nice_classes,
        )

        async with measure_duration() as elapsed:
            try:
                results_per_class = await asyncio.gather(
                    *(self._search_one_class(phrase, nc) for nc in nice_classes),
                    return_exceptions=True,
                )

                combined: list[TrademarkRecord] = []
                error_messages: list[str] = []
                for nc, result in zip(nice_classes, results_per_class, strict=True):
                    if isinstance(result, BaseException):
                        error_messages.append(
                            f"class_{nc}:{result.__class__.__name__}"
                        )
                        log.warning(
                            "markbase_class_search_failed",
                            nice_class=nc,
                            error=str(result),
                        )
                    else:
                        combined.extend(result)

                deduped = _dedupe_records(combined)

                if error_messages and not combined:
                    return TrademarkSearchResult(
                        jurisdiction=self.jurisdiction,
                        records=[],
                        duration_ms=elapsed(),
                        error=f"all_failed: {'; '.join(error_messages)}",
                    )

                log.info(
                    "markbase_search_complete",
                    count=len(deduped),
                    duration_ms=elapsed(),
                )
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=deduped,
                    duration_ms=elapsed(),
                    error=None,
                )
            except Exception as e:  # noqa: BLE001
                log.exception("markbase_search_unexpected_error")
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=[],
                    duration_ms=elapsed(),
                    error=f"unexpected:{e.__class__.__name__}",
                )

    # ------------------------------------------------------------------
    # Per-class fan-out
    # ------------------------------------------------------------------

    async def _search_one_class(
        self, phrase: str, nice_class: int
    ) -> list[TrademarkRecord]:
        """Markbase filters by international_code as 3-digit zero-padded string."""
        params = {
            "q": phrase,
            "international_code": f"{nice_class:03d}",
            "limit": str(MAX_RESULTS_PER_CLASS),
        }

        async def _do_request() -> httpx.Response:
            response = await self._client.get(MARKBASE_SEARCH_PATH, params=params)
            response.raise_for_status()
            return response

        response = await run_with_retry(
            _do_request, service_name="markbase", max_attempts=3
        )

        try:
            payload = response.json()
        except ValueError:
            logger.warning(
                "markbase_non_json_response", status=response.status_code
            )
            return []

        hits = payload.get("hits") if isinstance(payload, dict) else None
        if not isinstance(hits, list):
            return []

        records: list[TrademarkRecord] = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            parsed = self._parse_hit(hit, nice_class)
            if parsed is not None:
                records.append(parsed)
        return records

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_hit(
        self, hit: dict[str, Any], fallback_class: int
    ) -> TrademarkRecord | None:
        """Convert a Markbase /search hit into a TrademarkRecord."""
        serial = hit.get("serial_number")
        if not serial:
            return None
        serial_str = str(serial).strip()
        if not serial_str:
            return None

        mark = (hit.get("word_mark") or "").strip() or "(no mark)"
        owner_raw = hit.get("owner_name")
        owner = owner_raw.strip() if isinstance(owner_raw, str) and owner_raw.strip() else None

        raw_status = _label_from_status_code(hit.get("status_code"))
        status = normalize_filing_status(raw_status)

        filing_date = _date_from_yyyymmdd(hit.get("filing_date"))
        registration_date = _date_from_yyyymmdd(hit.get("registration_date"))

        nice_classes = _parse_intl_codes(hit.get("international_codes"))
        if not nice_classes:
            nice_classes = [fallback_class]

        is_active = status in ACTIVE_STATUSES
        is_pending = status == FilingStatus.PENDING

        goods_raw = hit.get("goods_services")
        goods = goods_raw.strip() if isinstance(goods_raw, str) else None

        return TrademarkRecord(
            registration_number=serial_str,
            mark=mark,
            owner=owner,
            status=status,
            raw_status=raw_status,
            nice_class=nice_classes[0] if nice_classes else None,
            nice_classes=nice_classes,
            filing_date=filing_date,
            registration_date=registration_date,
            jurisdiction=self.jurisdiction,
            source_url=USPTO_TSDR_URL_TEMPLATE.format(sn=serial_str),
            goods_services=goods,
            is_active=is_active,
            is_pending=is_pending,
        )


# -----------------------------------------------------------------------------
# Module-level pure helpers
# -----------------------------------------------------------------------------


def _label_from_status_code(code: Any) -> str | None:
    """
    USPTO numeric status code → human label.

    Markbase exposes the raw 3-digit USPTO TM status codes. We coerce the
    leading digit into one of the four buckets understood by our
    `normalize_filing_status` normalizer.
    """
    if code is None:
        return None
    s = str(code).strip()
    if not s:
        return None
    first = s[0]
    if first == "8":
        return "Live/Registered"
    if first == "6":
        return "Live/Pending"
    if first == "7":
        return "Dead/Cancelled"
    if first == "9":
        return "Dead/Expired"
    return f"Unknown ({s})"


def _parse_intl_codes(value: Any) -> list[int]:
    """Markbase international_codes → list[int]. Tolerates malformed entries."""
    if not isinstance(value, list):
        return []
    out: list[int] = []
    for item in value:
        if not isinstance(item, str):
            continue
        item = item.strip()
        if not item:
            continue
        try:
            out.append(int(item))
        except ValueError:
            continue
    return out


def _date_from_yyyymmdd(value: Any) -> Any:
    """Convert YYYYMMDD strings to ISO YYYY-MM-DD before delegating to the project normalizer."""
    if not isinstance(value, str):
        return normalize_date_string(value)
    s = value.strip()
    if not s:
        return normalize_date_string(s)
    if len(s) == 8 and s.isdigit():
        return normalize_date_string(f"{s[0:4]}-{s[4:6]}-{s[6:8]}")
    return normalize_date_string(s)


def _dedupe_records(records: list[TrademarkRecord]) -> list[TrademarkRecord]:
    """Dedupe by serial number; merge nice_classes lists when duplicated."""
    by_serial: dict[str, TrademarkRecord] = {}
    for record in records:
        existing = by_serial.get(record.registration_number)
        if existing is None:
            by_serial[record.registration_number] = record
            continue
        merged_classes = list(existing.nice_classes)
        for nc in record.nice_classes:
            if nc not in merged_classes:
                merged_classes.append(nc)
        by_serial[record.registration_number] = existing.model_copy(
            update={"nice_classes": merged_classes}
        )
    return list(by_serial.values())
